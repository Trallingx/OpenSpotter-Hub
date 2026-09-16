"""
Config Loader
JSON configuration loading and saving utility.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigLoader:
    """
    Utility for loading and saving JSON configurations.
    Handles machine config and GUI config files.
    """

    @staticmethod
    def load_config(file_path: str) -> Dict[str, Any]:
        """
        Load configuration from JSON file.

        Args:
            file_path: Path to JSON config file

        Returns:
            Dictionary with configuration data

        Raises:
            FileNotFoundError: If file not found
            json.JSONDecodeError: If JSON is invalid
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def save_config(file_path: str, config: Dict[str, Any]) -> bool:
        """
        Save configuration to JSON file.

        Args:
            file_path: Path to save config
            config: Configuration dictionary

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save config: {e}")
            return False

    @staticmethod
    def get_default_machine_config() -> Dict[str, Any]:
        """Get default machine configuration."""
        return {
            "machine": {
                "name": "DOD Printer",
                "type": "inkjet",
            },
            "gantry": {
                "max_x": 200.0,
                "max_y": 200.0,
                "max_z": 10.0,
                "velocity": 50.0,
            },
            "valves": [
                {
                    "id": 0,
                    "pin": 12,
                    "name": "Valve 0",
                    "color": [255, 0, 0],
                    "on_ms": 5.0,
                    "off_ms": 0.0,
                    "cycles": 1,
                    "async": False,
                    "hold": False,
                },
                {
                    "id": 1,
                    "pin": 13,
                    "name": "Valve 1",
                    "color": [0, 255, 0],
                    "on_ms": 5.0,
                    "off_ms": 0.0,
                    "cycles": 1,
                    "async": False,
                    "hold": False,
                },
                {
                    "id": 2,
                    "pin": 14,
                    "name": "Valve 2",
                    "color": [0, 0, 255],
                    "on_ms": 5.0,
                    "off_ms": 0.0,
                    "cycles": 1,
                    "async": False,
                    "hold": False,
                },
                {
                    "id": 3,
                    "pin": 15,
                    "name": "Valve 3",
                    "color": [255, 255, 0],
                    "on_ms": 5.0,
                    "off_ms": 0.0,
                    "cycles": 1,
                    "async": False,
                    "hold": False,
                },
            ],
            "klipper": {
                "host": "localhost",
                "port": 7125,
                "dispatch_window_spots": 25,
                "dispatch_refill_threshold_spots": 13,
                "dispatch_batch_spots": 5,
                "start_gcode": "",
                "end_gcode": "",
            },
        }

    @staticmethod
    def get_default_gui_config() -> Dict[str, Any]:
        """Get default GUI configuration."""
        return {
            "theme": "obsidian",
            "window": {
                "width": 1400,
                "height": 900,
                "startup_maximized": False,
            },
            "canvas": {
                "background_color": "#1e1e2e",
                "grid_color": "#45475a",
                "spot_radius_px": 5,
                "line_width_px": 1,
            },
            "colors": {
                "primary": "#a6e3a1",
                "secondary": "#f38ba8",
                "accent": "#89b4fa",
                "background": "#1e1e2e",
                "surface": "#313244",
                "text": "#cdd6f4",
            },
            "panels": {
                "left_sidebar_width": 250,
                "bottom_panel_height": 150,
                "show_camera": True,
                "show_status": True,
            },
        }

    def __repr__(self):
        return "ConfigLoader()"
