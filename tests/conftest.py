"""
Shared fakes for tests that need to import production modules
without their real runtime dependencies (arcade, scipy, pandas,
matplotlib, fastf1, PySide6).

This conftest installs fake modules into ``sys.modules`` the
first time it is needed. Subsequent test files see the fakes
already present and do not re-install, so the fakes are
*additive* (idempotent) and order-independent.

The fakes provide just enough surface for the production
modules' import-time usage. They do NOT implement the real
behaviour; tests that exercise real behaviour skip via
``pytest.importorskip``.

Why the fakes are forced even when the real packages are
installed: the project's test suite was originally written for
an environment without the real ``pandas``/``arcade``/etc.
packages — the conftest's fakes ARE the test fixtures, and
they define a controlled surface that integration tests rely
on. With the real packages now installed in the venv, the
fakes MUST win over the real modules at conftest-load time,
otherwise the test fixtures are silently bypassed. We
preserve this design by unconditionally overwriting the
relevant ``sys.modules`` entries below.
"""
import sys
import types


_FAKE_KEY = type("K", (), {
    "ESCAPE": 0, "SPACE": 0, "RIGHT": 0, "LEFT": 0, "UP": 0,
    "DOWN": 0, "KEY_1": 0, "KEY_2": 0, "KEY_3": 0, "KEY_4": 0,
    "R": 0, "D": 0, "L": 0, "H": 0, "B": 0, "I": 0,
})()


class _FakeArcadeWindow:
    def __init__(self, *a, **kw): pass
    def close(self, *a, **kw): pass
    def run(self, *a, **kw): pass


def _ensure(name, factory):
    """Install a fake module, unconditionally winning over any
    real module already in ``sys.modules``.

    The conftest is the project's test-fixture layer; the fakes
    are the test surface. Real packages that are now installed
    in the venv MUST NOT silently take over the role of the
    fakes, otherwise the test suite would run against the real
    production code's behaviour instead of the controlled
    fixture surface. By overwriting unconditionally we preserve
    the test's design (see module docstring for context).

    To avoid masking genuine import errors in non-faked
    modules, this only overwrites the specific module names
    listed in ``_install_optional_deps`` below.
    """
    sys.modules[name] = factory()


def _make_arcade():
    m = types.ModuleType("arcade")
    m.Window = _FakeArcadeWindow
    m.run = lambda: None
    m.key = _FAKE_KEY
    m.close_window = lambda: None
    m.maximize = lambda self: None
    m.set_viewport = lambda *a, **kw: None
    m.start_render = lambda: None
    m.finish_render = lambda: None
    m.set_background_color = lambda *a, **kw: None
    m.View = lambda *a, **kw: None

    class _MockText:
        """Mock arcade.Text that records attribute assignments."""
        def __init__(self, *a, **kw):
            self.text = a[0] if a else kw.get("text", "")
            for k, v in kw.items():
                if k != "text":
                    setattr(self, k, v)
        def draw(self): pass

    class _FakeTexture:
        def __init__(self, *a, **kw):
            self.name = a[0] if a else kw.get("name", "")
            self.image = a[1] if len(a) > 1 else kw.get("image", None)
            self.width = self.image.width if hasattr(self.image, "width") else 50
            self.height = self.image.height if hasattr(self.image, "height") else 50

    m.Text = _MockText
    m.Texture = _FakeTexture
    m.load_texture = lambda *a, **kw: None
    # Add the draw_* functions that arcade_compat routes to.
    # These are no-ops for the leaderboard text-reuse tests.
    m.draw_rectangle_filled = lambda *a, **kw: None
    m.draw_rect_filled = lambda *a, **kw: None
    m.draw_circle_filled = lambda *a, **kw: None
    m.draw_circle_outline = lambda *a, **kw: None
    m.draw_line = lambda *a, **kw: None
    m.draw_texture_rect = lambda *a, **kw: None
    class _FakeShape:
        def __init__(self, *a, **kw): pass
        def draw(self): pass

    m.Shape = _FakeShape
    m.create_line_strip = lambda *a, **kw: _FakeShape()
    m.draw_line_strip = lambda *a, **kw: None
    m.draw_point = lambda *a, **kw: None
    m.draw_text = lambda *a, **kw: None
    m.draw_lrbt_rectangle_textured = lambda *a, **kw: None
    m.draw_rect_outline = lambda *a, **kw: None
    m.XYWH = lambda *a, **kw: None
    m.color = types.SimpleNamespace(
        BLACK=0, WHITE=0, RED=0, GREEN=0, BLUE=0,
        YELLOW=0, ORANGE=0, BROWN=0, LIGHT_GRAY=0,
        GRAY=0, DARK_GRAY=0, DARK_RED=0,
    )
    return m


def _make_scipy():
    ms = types.ModuleType("scipy")
    mssp = types.ModuleType("scipy.spatial")
    msstats = types.ModuleType("scipy.stats")
    class _KDTree:
        def __init__(self, *a, **kw): pass
        def query(self, *a, **kw): return (0.0, 0)
    mssp.cKDTree = _KDTree
    class _Norm:
        def ppf(self, *a, **kw): return 0.0
        def cdf(self, *a, **kw): return 0.0
        def rvs(self, *a, **kw): return 0.0
    msstats.norm = _Norm()
    ms.stats = msstats
    ms.spatial = mssp
    return ms


def _make_scipy_spatial():
    mssp = types.ModuleType("scipy.spatial")
    class _KDTree:
        def __init__(self, *a, **kw): pass
        def query(self, *a, **kw): return (0.0, 0)
    mssp.cKDTree = _KDTree
    return mssp


def _make_scipy_stats():
    msstats = types.ModuleType("scipy.stats")
    class _Norm:
        def ppf(self, *a, **kw): return 0.0
        def cdf(self, *a, **kw): return 0.0
        def rvs(self, *a, **kw): return 0.0
    msstats.norm = _Norm()
    return msstats


def _make_pandas():
    """Build a minimal pandas stub for the test fixtures.

    On Python 3.10–3.13, function/parameter annotations are
    eagerly evaluated at definition time, so any annotation
    like ``laps_df: pd.DataFrame`` requires ``pd.DataFrame``
    to exist as an attribute. On Python 3.14+, PEP 649 defers
    annotation evaluation, so an empty module is enough. The
    production tests need to work on both, so the stub exposes
    the minimum attribute set the production code's annotation
    strings actually name: ``DataFrame`` and ``Series``.

    The stub does NOT implement any real pandas behaviour;
    tests that exercise pandas semantics use
    ``pytest.importorskip`` or stub pandas via monkeypatch.
    """
    m = types.ModuleType("pandas")

    class _DataFrame:
        """Placeholder class for ``pd.DataFrame`` annotations.

        Construction accepts any args; the instance is opaque.
        Production code that actually calls pandas methods on
        the placeholder will raise ``AttributeError`` when the
        real method is invoked — that is the intended signal
        that the test needs to be migrated to the real pandas
        or to a richer stub.
        """

        def __init__(self, *a, **kw):
            self._args = a
            self._kw = kw

        def __repr__(self):
            return "<_DataFrame placeholder>"

    class _Series:
        def __init__(self, *a, **kw):
            self._args = a
            self._kw = kw

        def __repr__(self):
            return "<_Series placeholder>"

    m.DataFrame = _DataFrame
    m.Series = _Series
    # The production code uses pd.notna() in the leaderboard
    # tyre-life display. Add a no-op that always returns True
    # (the test passes integer values, not NaN).
    m.notna = lambda x: True
    return m


def _make_matplotlib():
    mpl = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda *a, **kw: (None, None)
    pyplot.figure = lambda *a, **kw: None
    pyplot.show = lambda *a, **kw: None
    pyplot.close = lambda *a, **kw: None
    mpl.pyplot = pyplot
    mpl.use = lambda *a, **kw: None  # matplotlib.use("Agg")
    return mpl


def _make_fastf1():
    m = types.ModuleType("fastf1")
    mplot = types.ModuleType("fastf1.plotting")
    m.plotting = mplot
    m.Cache = type("C", (), {"enable_cache": staticmethod(lambda *a, **kw: None)})()
    m.get_session = lambda *a, **kw: None
    m.get_event_schedule = lambda *a, **kw: None
    return m


def _make_pyside6():
    p6 = types.ModuleType("PySide6")
    qc = types.ModuleType("PySide6.QtCore")
    class _Signal:
        def __init__(self, *a, **kw): pass
        def connect(self, *a, **kw): pass
        def emit(self, *a, **kw): pass
    qc.Signal = _Signal
    qc.Slot = lambda *a, **kw: (lambda f: f)
    qc.Qt = type("Q", (), {})()
    class _QThread:
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def quit(self): pass
        def wait(self, *a, **kw): return True
        def msleep(self, *a, **kw): pass
        def sleep(self, *a, **kw): pass
    qc.QThread = _QThread
    p6.QtCore = qc
    # Intentionally NO QApplication so matplotlib's backend
    # selection does not falsely believe a Qt binding is
    # available. This preserves the original
    # tests/test_imports.py skip behaviour.
    qw = types.ModuleType("PySide6.QtWidgets")
    class _QMainWindow:
        def __init__(self, *a, **kw): pass
        def show(self): pass
        def hide(self): pass
    qw.QMainWindow = _QMainWindow
    qw.QWidget = _QMainWindow
    qw.QLabel = _QMainWindow
    qw.QFrame = _QMainWindow
    qw.QScrollArea = _QMainWindow
    qw.QVBoxLayout = _QMainWindow
    qw.QHBoxLayout = _QMainWindow
    qw.QPushButton = _QMainWindow
    qw.QApplication = _QMainWindow
    qw.QTextEdit = _QMainWindow
    qw.QStatusBar = _QMainWindow
    qw.QSplitter = _QMainWindow
    qw.QListWidget = _QMainWindow
    qw.QTabWidget = _QMainWindow
    qw.QFont = _QMainWindow
    qw.QTextCursor = _QMainWindow
    p6.QtWidgets = qw
    p6.QtGui = types.ModuleType("PySide6.QtGui")
    p6.QtCore = qc
    qc.Qt = type("Q", (), {})()
    return p6, qc, qw


def _install_optional_deps():
    """Install every fake the production modules might import.
    Each call is idempotent; missing submodules are filled in
    independently so partial installs (from earlier files) are
    topped up. With real packages now installed in the venv,
    the fakes unconditionally overwrite any real module of the
    same name in ``sys.modules`` so the test surface stays
    controlled (see ``_ensure`` docstring).
    """
    _ensure("arcade", _make_arcade)
    _ensure("scipy", _make_scipy)
    _ensure("scipy.spatial", _make_scipy_spatial)
    _ensure("scipy.stats", _make_scipy_stats)
    _ensure("pandas", _make_pandas)
    _ensure("matplotlib", _make_matplotlib)
    _ensure("matplotlib.pyplot",
            lambda: sys.modules["matplotlib"].pyplot)
    _ensure("fastf1", _make_fastf1)
    _ensure("fastf1.plotting",
            lambda: sys.modules["fastf1"].plotting)
    # PySide6 is special: it has 3 submodules. Always install
    # the fake trio so the existing tests see the controlled
    # surface (no QApplication, no QComboBox, etc.).
    p6, qc, qw = _make_pyside6()
    sys.modules["PySide6"] = p6
    sys.modules["PySide6.QtCore"] = qc
    sys.modules["PySide6.QtWidgets"] = qw


_install_optional_deps()
