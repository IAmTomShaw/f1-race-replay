from types import SimpleNamespace

from src.f1_data import get_circuit_rotation


def test_returns_the_circuit_rotation_when_info_is_available():
    session = SimpleNamespace(get_circuit_info=lambda: SimpleNamespace(rotation=93.0))
    assert get_circuit_rotation(session) == 93.0


def test_falls_back_to_no_rotation_when_fastf1_has_no_circuit_info():
    # FastF1 raises AttributeError ('NoneType' has no attribute 'add_marker_distance')
    # for circuits missing from its circuit-info database.
    def get_circuit_info():
        raise AttributeError("'NoneType' object has no attribute 'add_marker_distance'")

    assert get_circuit_rotation(SimpleNamespace(get_circuit_info=get_circuit_info)) == 0.0


def test_falls_back_to_no_rotation_when_circuit_info_is_none():
    assert get_circuit_rotation(SimpleNamespace(get_circuit_info=lambda: None)) == 0.0
