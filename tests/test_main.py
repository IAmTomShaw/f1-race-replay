import pytest

main = pytest.importorskip("main")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], "R"),
        (["--sprint"], "S"),
        (["--qualifying"], "Q"),
        (["--sprint-qualifying"], "SQ"),
        (["--qualifying", "--sprint"], "SQ"),
        (["--sprint", "--qualifying"], "SQ"),
        (["--fp1"], "FP1"),
        (["--fp2"], "FP2"),
        (["--fp3"], "FP3"),
    ],
)
def test_get_session_type(args, expected):
    argv = ["main.py", "--viewer", "--year", "2025", "--round", "12", *args]
    assert main._get_session_type(argv) == expected
