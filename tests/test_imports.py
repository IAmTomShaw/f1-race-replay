import importlib

import pytest


MODULES = [
    "src.bayesian_tyre_model",
    "src.cli.race_selection",
    "src.f1_data",
    "src.gui.insights_menu",
    "src.gui.pit_wall_dashboard",
    "src.gui.pit_wall_window",
    "src.gui.pit_wall_window_template",
    "src.gui.race_selection",
    "src.gui.settings_dialog",
    "src.insights.driver_telemetry_window",
    "src.insights.example_pit_wall_window",
    "src.insights.gap_evolution_window",
    "src.insights.race_control_feed_window",
    "src.insights.telemetry_stream_viewer",
    "src.insights.track_position_window",
    "src.insights.tyre_strategy_window",
    "src.interfaces.qualifying",
    "src.interfaces.race_replay",
    "src.lib.season",
    "src.lib.settings",
    "src.lib.time",
    "src.lib.tyres",
    "src.run_session",
    "src.services.stream",
    "src.tyre_degradation_integration",
    "src.ui_components",
]

OPTIONAL_DEPENDENCIES = {
    "arcade",
    "fastf1",
    "matplotlib",
    "numpy",
    "pandas",
    "pyglet",
    "PySide6",
    "pyside6",
    "questionary",
    "rich",
}


@pytest.mark.parametrize("module_name", MODULES)
def test_project_modules_are_importable(module_name):
    try:
        importlib.import_module(module_name)
    except (ModuleNotFoundError, ImportError) as exc:
        err_msg = str(exc)
        for dep in OPTIONAL_DEPENDENCIES:
            if dep.lower() in err_msg.lower() or (hasattr(exc, "name") and exc.name and dep.lower() in exc.name.lower()):
                pytest.skip(f"optional dependency not installed: {dep}")

        raise
