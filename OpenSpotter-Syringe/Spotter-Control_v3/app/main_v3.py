"""Desktop application startup and persisted workspace restoration."""

from .core.configuration import read_defaults
from .gui_v3 import DropletGui
from .input_configs import GLOBAL_FIELDS
from .paths import CONFIG_DIR, LOG_DIR, ensure_runtime_dirs
from .runtime_logging import configure_logging, get_logger, log_options


logger = get_logger("startup")


def main() -> None:
    """Prepare writable state, restore recipes, and run the Tk event loop."""

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
        global_defaults = read_defaults(config_path)
        log_options(
            logger,
            "startup.global_options_loaded",
            config_path=config_path,
            global_options=global_defaults,
        )

        gui.machine_parameters_window.populate(
            GLOBAL_FIELDS,
            global_defaults,
            gui.entry,
            gui=gui,
        )
        # ``max_grid_count`` is the legacy persisted key; the value now caps
        # every registered pattern workspace.
        max_pattern_count = max(
            1,
            int(global_defaults.get("max_grid_count", 6)),
        )

        # Restore every registered pattern workspace from the versioned state.
        states_path = CONFIG_DIR / "config_states.json"
        states_data = read_defaults(states_path)
        saved_patterns = states_data.get("patterns", {})
        if not isinstance(saved_patterns, dict):
            saved_patterns = {}
        requested_counts = {}
        active_counts = {}
        for plugin in gui.pattern_plugins:
            plugin_id = plugin.manifest.id
            requested = int(
                saved_patterns.get(
                    plugin_id,
                    states_data.get(plugin.workspace.state_count_key, 0),
                )
            )
            active = max(0, min(requested, max_pattern_count))
            requested_counts[plugin_id] = requested
            active_counts[plugin_id] = active
        log_options(
            logger,
            "startup.pattern_state_restored",
            state_path=states_path,
            requested_pattern_counts=requested_counts,
            active_pattern_counts=active_counts,
            max_pattern_count=max_pattern_count,
        )

        for plugin_id, count in active_counts.items():
            for _ in range(count):
                gui.instance_pattern(plugin_id)

        gui._switch_workspace_mode()

        # Set global fields to locked state by default.
        gui._update_global_fields_state()
        gui.initialize_machine_control()
        log_options(
            logger,
            "application.ready",
            workspace_mode=gui._current_workspace_mode(),
            global_parameters_locked=bool(gui.global_locked.get()),
            pattern_counts={
                plugin_id: len(workspace.instances)
                for plugin_id, workspace in gui.pattern_workspaces.items()
            },
        )
        gui.mainloop()
        logger.info("application.stopped")
    except Exception:
        logger.exception("application.startup_or_runtime_failed")
        raise


if __name__ == "__main__":
    main()
