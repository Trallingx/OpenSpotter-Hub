"""Persistent editor window for Moonraker network connection settings."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from .machine.config import MoonrakerConfig
from .machine.connection_settings import (
    DEFAULT_CONNECTION_SETTINGS_PATH,
    ConnectionSettingsError,
    MoonrakerConnectionSettings,
    load_connection_settings,
    save_connection_settings,
)
from .runtime_logging import get_logger
from .ui_theme import COLORS, FONTS, button_options, entry_options


logger = get_logger("machine.connection_window")


class MoonrakerConnectionWindow(tk.Toplevel):
    """Decorated connection editor that is hidden instead of destroyed."""

    def __init__(
        self,
        parent,
        *,
        path: Path = DEFAULT_CONNECTION_SETTINGS_PATH,
        on_saved: Optional[Callable[[MoonrakerConfig], None]] = None,
    ):
        super().__init__(parent)
        self.withdraw()
        self.title("OpenSpotter | Moonraker Connection")
        self.configure(bg=COLORS["bg_primary"])
        self.geometry("620x430")
        self.minsize(540, 390)
        self.resizable(True, False)
        self.overrideredirect(False)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.bind("<Escape>", self.hide)
        self.bind("<Control-s>", self.save)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.path = Path(path)
        self.on_saved = on_saved
        self._settings = MoonrakerConnectionSettings()

        self.scheme_var = tk.StringVar(master=self, value="http")
        self.host_var = tk.StringVar(master=self, value="localhost")
        self.port_var = tk.StringVar(master=self, value="7125")
        self.route_prefix_var = tk.StringVar(master=self, value="")
        self.api_key_var = tk.StringVar(master=self, value="")
        self.status_var = tk.StringVar(master=self, value="")

        panel = tk.Frame(
            self,
            bg=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        panel.columnconfigure(1, weight=1)

        tk.Label(
            panel,
            text="MOONRAKER CONNECTION",
            font=FONTS["header"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=16,
            pady=(16, 2),
        )
        tk.Label(
            panel,
            text=(
                "Network access is kept separate from machine geometry and "
                "generation parameters."
            ),
            font=FONTS["caption"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_secondary"],
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=16,
            pady=(0, 16),
        )

        self.scheme_input = ttk.Combobox(
            panel,
            textvariable=self.scheme_var,
            values=("http", "https"),
            state="readonly",
            width=10,
        )
        self.host_input = tk.Entry(
            panel,
            textvariable=self.host_var,
            **entry_options(),
        )
        self.port_input = tk.Entry(
            panel,
            textvariable=self.port_var,
            width=12,
            **entry_options(mono=True),
        )
        self.route_prefix_input = tk.Entry(
            panel,
            textvariable=self.route_prefix_var,
            **entry_options(mono=True),
        )
        self.api_key_input = tk.Entry(
            panel,
            textvariable=self.api_key_var,
            show="*",
            **entry_options(mono=True),
        )

        rows = (
            ("Protocol", self.scheme_input),
            ("Host or IP", self.host_input),
            ("Port", self.port_input),
            ("Route prefix", self.route_prefix_input),
            ("API key (optional)", self.api_key_input),
        )
        for row_index, (label, widget) in enumerate(rows, start=2):
            tk.Label(
                panel,
                text=label,
                font=FONTS["label"],
                fg=COLORS["text_secondary"],
                bg=COLORS["bg_secondary"],
                anchor="w",
            ).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(16, 12),
                pady=6,
            )
            widget.grid(
                row=row_index,
                column=1,
                sticky="ew",
                padx=(0, 16),
                pady=6,
            )

        tk.Label(
            panel,
            text=(
                "Use a host name or IP without a protocol. Proxy paths such "
                "as /moonraker belong in Route prefix. API keys stay masked "
                "and are saved only in the local connection file."
            ),
            font=FONTS["caption"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_secondary"],
            justify="left",
            wraplength=540,
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(10, 4),
        )
        tk.Label(
            panel,
            textvariable=self.status_var,
            font=FONTS["caption"],
            fg=COLORS["warning"],
            bg=COLORS["bg_secondary"],
            anchor="w",
        ).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(4, 8),
        )

        actions = tk.Frame(panel, bg=COLORS["bg_secondary"])
        actions.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="e",
            padx=16,
            pady=(0, 16),
        )
        tk.Button(
            actions,
            text="RELOAD",
            command=self.reload,
            **button_options("ghost"),
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            actions,
            text="CLOSE",
            command=self.hide,
            **button_options("secondary"),
        ).pack(side="left", padx=6)
        tk.Button(
            actions,
            text="SAVE",
            command=self.save,
            **button_options("primary"),
        ).pack(side="left", padx=(6, 0))

        self.reload()

    def collect_settings(self) -> MoonrakerConnectionSettings:
        """Validate and normalize the currently displayed values."""
        return MoonrakerConnectionSettings(
            host=self.host_var.get(),
            port=self.port_var.get(),
            scheme=self.scheme_var.get(),
            route_prefix=self.route_prefix_var.get(),
            api_key=self.api_key_var.get() or None,
        )

    def get_config(self, **runtime_options) -> MoonrakerConfig:
        """Return a runtime config for the currently displayed values."""
        return self.collect_settings().to_moonraker_config(**runtime_options)

    def reload(self):
        """Restore values from disk, or safe defaults if no file exists."""
        try:
            settings = load_connection_settings(self.path)
        except ConnectionSettingsError:
            settings = MoonrakerConnectionSettings()
            self.status_var.set(
                "Saved settings could not be loaded; safe defaults are shown."
            )
        else:
            self.status_var.set("")
        self._settings = settings
        self._apply_settings(settings)
        return settings

    def save(self, _event=None):
        """Validate, persist, and publish the new runtime config."""
        try:
            settings = self.collect_settings()
            save_connection_settings(settings, self.path)
        except (ConnectionSettingsError, OSError) as exc:
            self.status_var.set(str(exc))
            return None

        self._settings = settings
        config = settings.to_moonraker_config()
        self.status_var.set(
            "Connection settings saved. Reconnect to apply changes."
        )
        if self.on_saved is not None:
            try:
                self.on_saved(config)
            except Exception:
                logger.exception(
                    "moonraker.saved_settings_callback_failed"
                )
                self.status_var.set(
                    "Settings were saved, but reconnecting failed. "
                    "Use RECONNECT after reviewing the runtime log."
                )
        return config

    def show(self):
        """Reveal the existing editor without rebuilding its fields."""
        self.deiconify()
        self.lift()
        try:
            self.focus_set()
            self.host_input.focus_set()
        except tk.TclError:
            pass
        return self

    def hide(self, _event=None):
        """Keep the editor and unsaved values alive while hiding it."""
        self.withdraw()
        return "break"

    def _apply_settings(self, settings: MoonrakerConnectionSettings) -> None:
        self.scheme_var.set(settings.scheme)
        self.host_var.set(settings.host)
        self.port_var.set(str(settings.port))
        self.route_prefix_var.set(settings.route_prefix)
        self.api_key_var.set(settings.api_key or "")
