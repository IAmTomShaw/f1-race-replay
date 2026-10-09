import pytest

pytest.importorskip("fastf1")

from src.f1_data import get_circuit_rotation


class FakeCircuitInfo:
    rotation = 44.0


class FakeSession:
    def __init__(self, circuit_info=None, error=None):
        self._circuit_info = circuit_info
        self._error = error

    def get_circuit_info(self):
        if self._error is not None:
            raise self._error
        return self._circuit_info


def test_get_circuit_rotation_returns_fastf1_rotation():
    session = FakeSession(circuit_info=FakeCircuitInfo())

    assert get_circuit_rotation(session) == 44.0


def test_get_circuit_rotation_falls_back_when_fastf1_raises():
    # FastF1 raises this from inside get_circuit_info() for an unknown circuit
    error = AttributeError("'NoneType' object has no attribute 'add_marker_distance'")
    session = FakeSession(error=error)

    assert get_circuit_rotation(session) == 0.0


def test_get_circuit_rotation_falls_back_when_circuit_info_is_missing():
    session = FakeSession(circuit_info=None)

    assert get_circuit_rotation(session) == 0.0
