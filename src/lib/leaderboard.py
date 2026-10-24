"""Leaderboard ordering helpers.

These are deliberately free of any GUI (arcade) or FastF1 imports so the
ordering policy can be unit tested headlessly and reused wherever a leaderboard
order is needed.

During a race the leaderboard is ordered by a live on-track progress proxy,
which is a fine approximation of position while cars are running. Once the race
is over that proxy is wrong: post-race penalties, lapped cars and retirements
change the classified result without changing on-track progress. At that point
the official classification from ``session.results`` should be used instead.
See issue #309.
"""

from __future__ import annotations


def official_finishing_order(results):
    """Return driver abbreviations in official classified finishing order.

    ``results`` is a FastF1 ``session.results`` DataFrame (or anything with the
    same shape). Rows are ordered by the official ``Position`` column, which
    already reflects post-race penalties, lapped cars and retirements (retired
    drivers are classified at the back). Rows without a usable abbreviation are
    skipped, and each code appears at most once.

    Returns an empty list when no usable results are available, so callers can
    treat "no official order" as "keep the live order".
    """
    if results is None:
        return []
    try:
        if results.empty:
            return []
    except AttributeError:
        return []

    ordered = results
    if "Position" in getattr(results, "columns", []):
        # NaN positions (unclassified) sort to the end rather than the front.
        ordered = results.sort_values("Position", na_position="last")

    order = []
    for _, row in ordered.iterrows():
        code = str(row.get("Abbreviation", "") or "").strip()
        if code and code not in order:
            order.append(code)
    return order


def order_leaderboard_codes(progress_ranked_codes, official_finish_order, race_finished):
    """Return the leaderboard code order to display for the current frame.

    While the race is running (``race_finished`` is false) the live
    ``progress_ranked_codes`` order, already sorted by on-track progress, is
    returned unchanged. Once the race has finished the official classified
    order is used instead so the final leaderboard matches the real result.

    Codes present in the live order but missing from the official order are kept
    and appended in their live order, so a driver is never dropped from the
    board. Official codes that are not in the live order are ignored.
    """
    live = list(progress_ranked_codes)
    if not race_finished or not official_finish_order:
        return live

    live_set = set(live)
    ordered = [code for code in official_finish_order if code in live_set]
    ordered_set = set(ordered)
    ordered.extend(code for code in live if code not in ordered_set)
    return ordered
