import json

from .gui_v3 import DropletGui
from .SpotterFunctions import read_defaults
from .grid import create_labels
from .input_configs import GLOBAL_FIELDS
from .paths import CONFIG_DIR, LOG_DIR, ensure_runtime_dirs
from .runtime_logging import configure_logging, get_logger, log_options


logger = get_logger("startup")


def main():
    ensure_runtime_dirs()
    log_path = configure_logging(LOG_DIR)
    log_options(
        logger,
        "application.starting",
        config_dir=CONFIG_DIR,
        log_path=log_path,
    )
    try:
        gui = DropletGui(str(CONFIG_DIR))

        # Load global defaults and create global inputs first.
        config_path = CONFIG_DIR / "config_global.json"
        with open(config_path, "r", encoding="utf-8") as config_file:
            global_defaults = json.load(config_file)
        log_options(
            logger,
            "startup.global_options_loaded",
            config_path=config_path,
            global_options=global_defaults,
        )

        create_labels(GLOBAL_FIELDS, global_defaults, gui.entry, gui.global_input_frame)
        max_grid_count = max(1, int(global_defaults.get("max_grid_count", 6)))

        # Read grid state from JSON and create grids accordingly.
        states_path = CONFIG_DIR / "config_states.json"
        states_data = read_defaults(states_path)
        requested_grid_count = int(states_data.get("grid_count", 0))
        requested_spiral_count = int(states_data.get("spiral_count", 0))
        grid_count = max(0, min(requested_grid_count, max_grid_count))
        spiral_count = max(0, min(requested_spiral_count, max_grid_count))
        log_options(
            logger,
            "startup.pattern_state_restored",
            state_path=states_path,
            requested_grid_count=requested_grid_count,
            requested_spiral_count=requested_spiral_count,
            active_grid_count=grid_count,
            active_spiral_count=spiral_count,
            max_pattern_count=max_grid_count,
        )

        for _ in range(grid_count):
            gui.instance_grid()

        for _ in range(spiral_count):
            gui.instance_spiral()

        gui._switch_workspace_mode()

        # Set global fields to locked state by default.
        gui._update_global_fields_state()
        log_options(
            logger,
            "application.ready",
            workspace_mode=gui._current_workspace_mode(),
            global_parameters_locked=bool(gui.global_locked.get()),
            grid_count=gui.grid_count,
            spiral_count=gui.spiral_count,
        )
        gui.mainloop()
        logger.info("application.stopped")
    except Exception:
        logger.exception("application.startup_or_runtime_failed")
        raise


if __name__ == "__main__":
    main()
