"""Leaderboard ordering helpers (no arcade / FastF1 imports, so easy to test)."""


def official_finishing_order(results):
    """Return driver codes in official classified order from session.results.

    FastF1 already sorts results by Position, which includes penalties, lapped
    cars and retirements. We sort again by Position defensively and keep any
    rows with a missing Position at the back, in their original order.
    Returns [] if results are unavailable.
    """
    if results is None:
        return []
    try:
        if results.empty or "Abbreviation" not in results.columns:
            return []
        rows = []
        for i, (_, row) in enumerate(results.iterrows()):
            code = row.get("Abbreviation")
            if not code or str(code) == "nan":
                continue
            try:
                pos = float(row.get("Position"))
                if pos != pos:  # NaN
                    raise ValueError
            except (TypeError, ValueError):
                pos = float("inf")
            rows.append((pos, i, str(code)))
        rows.sort()
        return [code for _, _, code in rows]
    except Exception:
        return []


def order_leaderboard_codes(live_order, official_order, race_finished):
    """Pick the order to display.

    During the race: live order, untouched.
    After the finish: official order, with any live driver missing from the
    classification appended so nobody ever disappears from the board.
    """
    if not race_finished or not official_order:
        return list(live_order)
    live_set = set(live_order)
    ordered = [c for c in official_order if c in live_set]
    seen = set(ordered)
    ordered.extend(c for c in live_order if c not in seen)
    return ordered
