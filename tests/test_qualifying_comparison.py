from types import SimpleNamespace

from src.interfaces.qualifying import QualifyingReplay


def _seg(tag):
    return {"frames": [{"t": 0.0, "telemetry": {"tag": tag}}], "sector_times": {"s1": 1.0}}


def _viewer(loaded_code="LEC", loaded_segment="Q3"):
    # VER pole (Q1-Q3), LEC and HAM reach Q3, NOR is out in Q1.
    data = {
        "results": [{"code": c} for c in ("VER", "LEC", "HAM", "NOR")],
        "telemetry": {
            "VER": {"Q1": _seg("VER-Q1"), "Q2": _seg("VER-Q2"), "Q3": _seg("VER-Q3")},
            "LEC": {"Q1": _seg("LEC-Q1"), "Q2": _seg("LEC-Q2"), "Q3": _seg("LEC-Q3")},
            "HAM": {"Q1": _seg("HAM-Q1"), "Q2": _seg("HAM-Q2"), "Q3": _seg("HAM-Q3")},
            "NOR": {"Q1": _seg("NOR-Q1"), "Q2": {"frames": []}, "Q3": {"frames": []}},
        },
    }
    return SimpleNamespace(
        data=data,
        show_comparison_telemetry=True,
        comparison_driver_code=None,
        loaded_driver_code=loaded_code,
        loaded_driver_segment=loaded_segment,
        _resolve_comparison=lambda: None,  # replaced below
    )


def _bind(v):
    v._resolve_comparison = lambda: QualifyingReplay._resolve_comparison(v)
    return v


def test_default_is_pole_q3():
    v = _bind(_viewer())
    code, segment, frames, sectors = v._resolve_comparison()
    assert (code, segment) == ("VER", "Q3")
    assert frames[0]["telemetry"]["tag"] == "VER-Q3"
    assert sectors == {"s1": 1.0}


def test_default_hidden_when_loaded_lap_is_pole_q3():
    v = _bind(_viewer(loaded_code="VER", loaded_segment="Q3"))
    assert v._resolve_comparison() is None


def test_toggle_off_hides_comparison():
    v = _bind(_viewer())
    v.show_comparison_telemetry = False
    assert v._resolve_comparison() is None


def test_tab_moves_to_next_driver_and_skips_loaded_lap():
    v = _bind(_viewer(loaded_code="LEC", loaded_segment="Q3"))
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.comparison_driver_code == "LEC"  # VER -> LEC; same driver but only Q3 equals loaded, fallback Q2
    code, segment, *_ = v._resolve_comparison()
    assert (code, segment) == ("LEC", "Q2")


def test_cycle_uses_loaded_segment_and_falls_back_for_early_exit():
    v = _bind(_viewer(loaded_code="HAM", loaded_segment="Q3"))
    v.comparison_driver_code = "HAM"
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.comparison_driver_code == "NOR"
    code, segment, *_ = v._resolve_comparison()
    assert (code, segment) == ("NOR", "Q1")  # no Q3/Q2 lap, falls back to Q1


def test_shift_tab_goes_backwards_and_wraps():
    v = _bind(_viewer(loaded_code="HAM", loaded_segment="Q3"))
    QualifyingReplay._cycle_comparison_driver(v, -1)  # from pole backwards wraps to the last driver
    assert v.comparison_driver_code == "NOR"
    QualifyingReplay._cycle_comparison_driver(v, -1)
    assert v.comparison_driver_code == "HAM"


def test_cycle_reenables_comparison():
    v = _bind(_viewer())
    v.show_comparison_telemetry = False
    QualifyingReplay._cycle_comparison_driver(v, 1)
    assert v.show_comparison_telemetry is True
