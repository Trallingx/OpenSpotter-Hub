"""
Config Manager
Centralized access to project configuration files with dotted-path lookup.
Loads machine_config.json, gui_config.json, grid.config.json, valve.config.json
from the workspace config folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    _instance: Optional["ConfigManager"] = None

    def __init__(self) -> None:
        root = Path(__file__).parent.parent
        self._config_dir = root / "config"
        self._cache: Dict[str, Any] = {}
        self.reload()

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance

    def _load_json(self, file_name: str) -> Dict[str, Any]:
        path = self._config_dir / file_name
        if not path.exists():
            return {}
        with open(path, "r") as f:
            return json.load(f)

    def reload(self) -> None:
        """Reload all known config files into cache."""
        machine = self._load_json("machine_config.json")
        gui = self._load_json("gui_config.json")
        grid_schema = self._load_json("grid.config.json")
        valve_schema = self._load_json("valve.config.json")

        # Flatten top-level machine config keys for dotted access
        self._cache = {
            "machine": machine.get("machine", {}),
            "gantry": machine.get("gantry", {}),
            "valves": machine.get("valves", []),
            "klipper": machine.get("klipper", {}),
            "grids": machine.get("grids", []),
            "gui": gui,
            "grid": grid_schema,
            "valve": valve_schema,
        }

    def get(self, dotted_path: str, default: Any = None) -> Any:
        """
        Retrieve a value using a dotted path across cached config.

        Examples:
        - get("gantry.max_x")
        - get("gui.canvas.spot_radius_px")
        - get("grid.fields")
        - get("valves") -> list of valve dicts
        """
        parts = dotted_path.split(".") if dotted_path else []
        cur: Any = self._cache
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    def set(self, dotted_path: str, value: Any) -> None:
        """Set a value in cache using dotted path (does not persist to disk)."""
        parts = dotted_path.split(".")
        cur = self._cache
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value

    def available_valves(self) -> list[dict]:
        """Return valves metadata list from machine config."""
        valves = self._cache.get("valves", [])
        return valves if isinstance(valves, list) else []

    def valve_count(self) -> int:
        return len(self.available_valves())

    def grid_fields(self) -> list[dict]:
        """Return grid field schema entries."""
        schema = self._cache.get("grid", {})
        return schema.get("fields", []) if isinstance(schema, dict) else []

    def valve_fields(self) -> list[dict]:
        """Return valve field schema entries."""
        schema = self._cache.get("valve", {})
        return schema.get("fields", []) if isinstance(schema, dict) else []

    def machine_grids(self) -> list[dict]:
        grids = self._cache.get("grids", [])
        return grids if isinstance(grids, list) else []

    def machine_config(self) -> Dict[str, Any]:
        """Return the raw machine config document."""
        return self._load_json("machine_config.json")

    def persist_machine_config(self, data: Dict[str, Any]) -> bool:
        """Persist a machine config dictionary back to machine_config.json."""
        try:
            path = self._config_dir / "machine_config.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            # Update cache
            self.reload()
            return True
        except Exception:
            return False
