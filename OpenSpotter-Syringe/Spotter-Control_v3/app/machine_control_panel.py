"""Right-side Moonraker machine controls and live virtual-SD G-code view."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple

from .ui_theme import COLORS, FONTS, button_options, entry_options


Callback = Callable[..., Any]


class MachineControlPanel(tk.Frame):
    """Presentation-only machine panel.

    The panel never performs network or file work.  A controller supplies
    callbacks and periodically pushes immutable state into the methods below.
    """

    def __init__(self, parent: Any) -> None:
        super().__init__(parent, bg=COLORS["bg_secondary"])
        self.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)

        self._callbacks = {}
        self._last_gcode_key = None
        self._last_console_key = None
        self.connection_var = tk.StringVar(master=self, value="DISCONNECTED")
        self.operation_var = tk.StringVar(master=self, value="Moonraker is not connected")
        self.job_var = tk.StringVar(master=self, value="No active virtual-SD job")
        self.prompt_var = tk.StringVar(master=self, value="Ready for operator input")
        self.position_var = tk.StringVar(master=self, value="X ---.---   Y ---.---   Z ---.---")
        self.homed_var = tk.StringVar(master=self, value="HOMED: ---")
        self.z_offset_var = tk.StringVar(master=self, value="LIVE Z  +0.000 mm")
        self.gcode_title_var = tk.StringVar(
            master=self,
            value="VIRTUAL-SD READ / QUEUED  /  NO JOB",
        )
        self.jog_step_var = tk.StringVar(master=self, value="1.0")
        self.jog_feed_var = tk.StringVar(master=self, value="600")
        self.z_step_var = tk.StringVar(master=self, value="0.010")

        self._build_header()
        self._build_job_controls()
        self._build_operation_status()
        self._build_workspace()
        self.set_control_state(
            connected=False,
            ready=False,
            print_state="standby",
            homed_axes="",
            offsets_enabled=False,
            operation_busy=False,
            runtime_started=False,
        )

    def bind_actions(
        self,
        *,
        start_job: Callback,
        pause_resume: Callback,
        cancel_job: Callback,
        emergency_stop: Callback,
        home: Callback,
        jog: Callback,
        adjust_z: Callback,
        reset_z: Callback,
        connection_settings: Callback,
        reconnect: Callback,
        parse_manual_gcode: Callback,
        send_manual_gcode: Callback,
    ) -> None:
        self._callbacks = {
            "start_job": start_job,
            "pause_resume": pause_resume,
            "cancel_job": cancel_job,
            "emergency_stop": emergency_stop,
            "home": home,
            "jog": jog,
            "adjust_z": adjust_z,
            "reset_z": reset_z,
            "connection_settings": connection_settings,
            "reconnect": reconnect,
            "parse_manual_gcode": parse_manual_gcode,
            "send_manual_gcode": send_manual_gcode,
        }

    def _invoke(self, name: str, *args: Any) -> Any:
        callback = self._callbacks.get(name)
        if callback is not None:
            return callback(*args)
        return None

    def _card(
        self,
        parent: Any,
        row: int,
        *,
        weight: int = 0,
        pady: Tuple[int, int] = (0, 6),
    ):
        card = tk.Frame(
            parent,
            bg=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
        )
        card.grid(row=row, column=0, sticky="nsew", padx=8, pady=pady)
        if weight:
            parent.rowconfigure(row, weight=weight)
        return card

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["bg_secondary"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(11, 7))
        header.columnconfigure(0, weight=1)

        title = tk.Frame(header, bg=COLORS["bg_secondary"])
        title.grid(row=0, column=0, rowspan=2, sticky="w")
        tk.Label(
            title,
            text="MACHINE CONTROL",
            font=FONTS["header"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).pack(anchor="w")
        tk.Label(
            title,
            text="MOONRAKER  /  VIRTUAL SD",
            font=FONTS["caption"],
            fg=COLORS["accent"],
            bg=COLORS["bg_secondary"],
        ).pack(anchor="w", pady=(1, 0))

        self.connection_label = tk.Label(
            header,
            textvariable=self.connection_var,
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_tertiary"],
            padx=8,
            pady=4,
        )
        self.connection_label.grid(row=0, column=1, sticky="e", padx=(6, 0))
        tk.Button(
            header,
            text="CONFIG",
            command=lambda: self._invoke("connection_settings"),
            **button_options("ghost"),
        ).grid(row=1, column=1, sticky="e", padx=(6, 0), pady=(4, 0))
        self.reconnect_button = tk.Button(
            header,
            text="RETRY",
            command=lambda: self._invoke("reconnect"),
            **button_options("ghost"),
        )
        self.reconnect_button.grid(
            row=1,
            column=2,
            sticky="e",
            padx=(4, 0),
            pady=(4, 0),
        )

    def _build_job_controls(self) -> None:
        card = self._card(self, 1)
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        tk.Label(
            card,
            text="JOB",
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
        tk.Label(
            card,
            textvariable=self.job_var,
            font=FONTS["mono_small"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
            anchor="w",
            justify="left",
            wraplength=340,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
        self.prompt_label = tk.Label(
            card,
            textvariable=self.prompt_var,
            font=FONTS["small"],
            fg=COLORS["warning"],
            bg=COLORS["bg_secondary"],
            anchor="w",
            justify="left",
            wraplength=340,
        )
        self.prompt_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=10,
            pady=(3, 7),
        )

        self.start_button = tk.Button(
            card,
            text="START CURRENT RECIPE",
            command=lambda: self._invoke("start_job"),
            **button_options("success"),
        )
        self.start_button.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 4),
        )
        self.pause_button = tk.Button(
            card,
            text="PAUSE",
            command=lambda: self._invoke("pause_resume"),
            **button_options("secondary"),
        )
        self.pause_button.grid(row=4, column=0, sticky="ew", padx=(8, 2), pady=(0, 4))
        self.cancel_button = tk.Button(
            card,
            text="STOP / CANCEL",
            command=lambda: self._invoke("cancel_job"),
            **button_options("danger"),
        )
        self.cancel_button.grid(row=4, column=1, sticky="ew", padx=(2, 8), pady=(0, 4))
        self.emergency_button = tk.Button(
            card,
            text="EMERGENCY STOP",
            command=lambda: self._invoke("emergency_stop"),
            **button_options("danger"),
        )
        self.emergency_button.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

    def _build_workspace(self) -> None:
        self.machine_tabs = ttk.Notebook(self, style="Custom.TNotebook")
        self.machine_tabs.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(0, 8),
        )

        self.motion_tab = tk.Frame(self.machine_tabs, bg=COLORS["bg_secondary"])
        self.motion_tab.rowconfigure(0, weight=1)
        self.motion_tab.columnconfigure(0, weight=1)
        self.live_z_tab = tk.Frame(self.machine_tabs, bg=COLORS["bg_secondary"])
        self.live_z_tab.rowconfigure(0, weight=1)
        self.live_z_tab.columnconfigure(0, weight=1)
        self.gcode_tab = tk.Frame(self.machine_tabs, bg=COLORS["bg_secondary"])
        self.gcode_tab.rowconfigure(0, weight=1)
        self.gcode_tab.columnconfigure(0, weight=1)
        self.machine_tabs.add(self.motion_tab, text="XYZ JOG")
        self.machine_tabs.add(self.live_z_tab, text="LIVE Z")
        self.machine_tabs.add(self.gcode_tab, text="LIVE G-CODE")

        motion_content = tk.Frame(self.motion_tab, bg=COLORS["bg_secondary"])
        motion_content.grid(row=0, column=0, sticky="nsew")
        motion_content.columnconfigure(0, weight=1)
        self._build_motion_controls(motion_content)
        live_z_content = tk.Frame(self.live_z_tab, bg=COLORS["bg_secondary"])
        live_z_content.grid(row=0, column=0, sticky="nsew")
        live_z_content.columnconfigure(0, weight=1)
        self._build_live_z_controls(live_z_content)
        self._build_gcode_view(self.gcode_tab)

    def _build_motion_controls(self, parent: Any) -> None:
        card = self._card(parent, 0, pady=(6, 6))
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)

        tk.Label(
            card,
            text="TOOLHEAD",
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 2))
        tk.Label(
            card,
            textvariable=self.position_var,
            font=FONTS["mono_small"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=10)
        tk.Label(
            card,
            textvariable=self.homed_var,
            font=FONTS["caption"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_secondary"],
        ).grid(row=2, column=0, sticky="w", padx=10, pady=(1, 5))
        self.home_button = tk.Button(
            card,
            text="SAFE HOME XYZ",
            command=lambda: self._invoke("home"),
            **button_options("secondary"),
        )
        self.home_button.grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="e",
            padx=8,
            pady=(1, 5),
        )

        settings = tk.Frame(card, bg=COLORS["bg_secondary"])
        settings.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 4))
        tk.Label(
            settings,
            text="STEP mm",
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
        ).pack(side="left")
        self.jog_step_combo = ttk.Combobox(
            settings,
            values=("0.01", "0.1", "1.0", "5.0"),
            textvariable=self.jog_step_var,
            state="readonly",
            width=6,
            font=FONTS["small"],
        )
        self.jog_step_combo.pack(side="left", padx=(4, 10))
        tk.Label(
            settings,
            text="FEED mm/min",
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
        ).pack(side="left")
        self.jog_feed_entry = tk.Entry(
            settings,
            textvariable=self.jog_feed_var,
            width=7,
            **entry_options(mono=True),
        )
        self.jog_feed_entry.pack(side="left", padx=(4, 0))

        self.jog_buttons = []
        for row, axis in enumerate(("X", "Y", "Z"), start=4):
            minus = tk.Button(
                card,
                text=f"{axis}  -",
                command=lambda selected=axis: self._jog(selected, -1.0),
                **button_options("ghost"),
            )
            minus.grid(row=row, column=0, sticky="ew", padx=(8, 2), pady=2)
            axis_label = tk.Label(
                card,
                text=axis,
                font=FONTS["label"],
                fg={
                    "X": COLORS["axis_x"],
                    "Y": COLORS["axis_y"],
                    "Z": COLORS["accent"],
                }[axis],
                bg=COLORS["bg_tertiary"],
                pady=7,
            )
            axis_label.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
            plus = tk.Button(
                card,
                text=f"{axis}  +",
                command=lambda selected=axis: self._jog(selected, 1.0),
                **button_options("ghost"),
            )
            plus.grid(row=row, column=2, sticky="ew", padx=(2, 8), pady=2)
            self.jog_buttons.extend((minus, plus))
        card.grid_rowconfigure(7, minsize=6)

    def _jog(self, axis: str, direction: float) -> None:
        try:
            distance = float(self.jog_step_var.get()) * float(direction)
            feed = float(self.jog_feed_var.get())
        except (TypeError, ValueError):
            self.set_operation("Jog step and feed must be valid numbers", level="error")
            return
        self._invoke("jog", axis, distance, feed)

    def _build_live_z_controls(self, parent: Any) -> None:
        card = self._card(parent, 0, pady=(6, 6))
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)

        tk.Label(
            card,
            text="LIVE NEEDLE Z",
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 2))
        tk.Label(
            card,
            textvariable=self.z_offset_var,
            font=FONTS["mono_small"],
            fg=COLORS["accent"],
            bg=COLORS["bg_secondary"],
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 5))
        self.z_step_combo = ttk.Combobox(
            card,
            values=("0.005", "0.010", "0.025", "0.050", "0.100"),
            textvariable=self.z_step_var,
            state="readonly",
            width=7,
            font=FONTS["small"],
        )
        self.z_step_combo.grid(row=1, column=1, columnspan=2, sticky="e", padx=8, pady=(0, 5))

        self.z_closer_button = tk.Button(
            card,
            text="CLOSER  (-)",
            command=lambda: self._adjust_z(-1.0),
            **button_options("secondary"),
        )
        self.z_closer_button.grid(row=2, column=0, sticky="ew", padx=(8, 2), pady=(0, 8))
        self.z_reset_button = tk.Button(
            card,
            text="RESET",
            command=lambda: self._invoke("reset_z"),
            **button_options("ghost"),
        )
        self.z_reset_button.grid(row=2, column=1, sticky="ew", padx=2, pady=(0, 8))
        self.z_away_button = tk.Button(
            card,
            text="AWAY  (+)",
            command=lambda: self._adjust_z(1.0),
            **button_options("secondary"),
        )
        self.z_away_button.grid(row=2, column=2, sticky="ew", padx=(2, 8), pady=(0, 8))

    def _adjust_z(self, direction: float) -> None:
        try:
            adjustment = float(self.z_step_var.get()) * float(direction)
        except (TypeError, ValueError):
            self.set_operation("Live Z step must be a valid number", level="error")
            return
        self._invoke("adjust_z", adjustment)

    def _build_operation_status(self) -> None:
        status = tk.Label(
            self,
            textvariable=self.operation_var,
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
            anchor="w",
            justify="left",
            wraplength=350,
        )
        status.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 5))
        self.operation_label = status

    def _build_gcode_view(self, parent: Any) -> None:
        self.gcode_modes = ttk.Notebook(parent, style="Custom.TNotebook")
        self.gcode_modes.grid(row=0, column=0, sticky="nsew")
        self.live_gcode_frame = tk.Frame(
            self.gcode_modes,
            bg=COLORS["bg_secondary"],
        )
        self.live_gcode_frame.rowconfigure(0, weight=1)
        self.live_gcode_frame.columnconfigure(0, weight=1)
        self.manual_gcode_frame = tk.Frame(
            self.gcode_modes,
            bg=COLORS["bg_secondary"],
        )
        self.manual_gcode_frame.rowconfigure(0, weight=1)
        self.manual_gcode_frame.columnconfigure(0, weight=1)
        self.gcode_modes.add(self.live_gcode_frame, text="LIVE VIEW")
        self.gcode_modes.add(self.manual_gcode_frame, text="MANUAL / CONSOLE")
        self._build_live_gcode_view(self.live_gcode_frame)
        self._build_manual_gcode_view(self.manual_gcode_frame)

    def _build_live_gcode_view(self, parent: Any) -> None:
        card = self._card(parent, 0, weight=1, pady=(6, 6))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)
        tk.Label(
            card,
            textvariable=self.gcode_title_var,
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 5))

        text_frame = tk.Frame(card, bg=COLORS["bg_secondary"])
        text_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.gcode_text = tk.Text(
            text_frame,
            height=9,
            width=34,
            wrap="none",
            state="disabled",
            bg=COLORS["canvas"],
            fg=COLORS["text_secondary"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            relief="flat",
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            font=FONTS["mono_small"],
            padx=5,
            pady=5,
        )
        scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.gcode_text.yview,
        )
        self.gcode_text.configure(yscrollcommand=scrollbar.set)
        self.gcode_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.gcode_text.tag_configure(
            "current",
            background=COLORS["selection"],
            foreground=COLORS["text_primary"],
        )
        self.gcode_text.tag_configure("read_before", foreground=COLORS["text_muted"])
        self.show_gcode_context(None, 0, ())

    def _build_manual_gcode_view(self, parent: Any) -> None:
        card = self._card(parent, 0, weight=1, pady=(6, 6))
        card.rowconfigure(1, weight=3)
        card.rowconfigure(5, weight=1)
        card.columnconfigure(0, weight=1)

        tk.Label(
            card,
            text="MANUAL G-CODE PARSER  /  IDLE MACHINE ONLY",
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        editor_frame = tk.Frame(card, bg=COLORS["bg_secondary"])
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=8)
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        self.manual_gcode_text = tk.Text(
            editor_frame,
            height=6,
            width=34,
            wrap="none",
            undo=True,
            maxundo=100,
            bg=COLORS["canvas"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            relief="flat",
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            font=FONTS["mono_small"],
            padx=5,
            pady=5,
        )
        manual_scrollbar = ttk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=self.manual_gcode_text.yview,
        )
        self.manual_gcode_text.configure(yscrollcommand=manual_scrollbar.set)
        self.manual_gcode_text.grid(row=0, column=0, sticky="nsew")
        manual_scrollbar.grid(row=0, column=1, sticky="ns")
        self.manual_gcode_text.insert(
            "1.0",
            "; Manual motion: G90/G91, then G0/G1 with XYZ and explicit F.\n"
            "; Read-only queries such as M114 are also allowed.\n",
        )
        self.manual_gcode_text.bind(
            "<Control-Return>",
            lambda _event: (self._send_manual_gcode(), "break")[1],
        )

        actions = tk.Frame(card, bg=COLORS["bg_secondary"])
        actions.grid(row=2, column=0, sticky="ew", padx=8, pady=(5, 3))
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        self.manual_parse_button = tk.Button(
            actions,
            text="PARSE",
            command=self._parse_manual_gcode,
            **button_options("ghost"),
        )
        self.manual_parse_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 2),
        )
        tk.Button(
            actions,
            text="CLEAR",
            command=lambda: self.manual_gcode_text.delete("1.0", "end"),
            **button_options("ghost"),
        ).grid(row=0, column=1, sticky="ew", padx=2)
        self.manual_send_button = tk.Button(
            actions,
            text="SEND",
            command=self._send_manual_gcode,
            **button_options("secondary"),
        )
        self.manual_send_button.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(2, 0),
        )

        self.manual_parse_var = tk.StringVar(
            master=self,
            value="Press PARSE to inspect commands without sending them.",
        )
        self.manual_parse_label = tk.Label(
            card,
            textvariable=self.manual_parse_var,
            font=FONTS["caption"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_secondary"],
            anchor="w",
            justify="left",
            wraplength=315,
        )
        self.manual_parse_label.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=9,
            pady=(0, 4),
        )

        tk.Label(
            card,
            text="KLIPPER RESPONSE CONSOLE",
            font=FONTS["caption"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=9, pady=(1, 2))
        console_frame = tk.Frame(card, bg=COLORS["bg_secondary"])
        console_frame.grid(
            row=5,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(0, 8),
        )
        console_frame.rowconfigure(0, weight=1)
        console_frame.columnconfigure(0, weight=1)
        self.manual_console_text = tk.Text(
            console_frame,
            height=4,
            width=34,
            wrap="word",
            state="disabled",
            bg=COLORS["canvas"],
            fg=COLORS["text_secondary"],
            insertbackground=COLORS["accent"],
            relief="flat",
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            font=FONTS["mono_small"],
            padx=5,
            pady=4,
        )
        console_scrollbar = ttk.Scrollbar(
            console_frame,
            orient="vertical",
            command=self.manual_console_text.yview,
        )
        self.manual_console_text.configure(yscrollcommand=console_scrollbar.set)
        self.manual_console_text.grid(row=0, column=0, sticky="nsew")
        console_scrollbar.grid(row=0, column=1, sticky="ns")
        self.manual_console_text.tag_configure("error", foreground=COLORS["error"])
        self.show_console(())

    def _manual_script(self) -> str:
        return self.manual_gcode_text.get("1.0", "end-1c")

    def _parse_manual_gcode(self) -> None:
        self._invoke("parse_manual_gcode", self._manual_script())

    def _send_manual_gcode(self) -> None:
        self._invoke("send_manual_gcode", self._manual_script())

    def set_connection(self, state: str, detail: str = "") -> None:
        normalized = str(state or "disconnected").strip().lower()
        labels = {
            "connected": ("CONNECTED", COLORS["success"]),
            "connecting": ("CONNECTING", COLORS["warning"]),
            "reconnecting": ("RECONNECTING", COLORS["warning"]),
            "starting": ("STARTING", COLORS["warning"]),
            "stopped": ("STOPPED", COLORS["text_muted"]),
            "disconnected": ("DISCONNECTED", COLORS["error"]),
        }
        text, color = labels.get(
            normalized,
            (normalized.upper() or "UNKNOWN", COLORS["text_secondary"]),
        )
        self.connection_var.set(text)
        self.connection_label.configure(fg=color)
        if detail:
            self.set_operation(detail, level="error" if normalized == "disconnected" else "info")

    def set_operation(self, text: str, *, level: str = "info") -> None:
        colors = {
            "info": COLORS["text_secondary"],
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["error"],
        }
        self.operation_var.set(str(text))
        self.operation_label.configure(fg=colors.get(level, COLORS["text_secondary"]))

    def set_job(
        self,
        *,
        state: str,
        filename: str = "",
        progress: float = 0.0,
        prompt: int = 0,
        display_message: str = "",
    ) -> None:
        normalized = str(state or "standby").lower()
        percent = max(0.0, min(float(progress or 0.0), 1.0)) * 100.0
        if filename:
            self.job_var.set(f"{normalized.upper():<9} {percent:6.2f}%\n{filename}")
        else:
            self.job_var.set(f"{normalized.upper():<9} {percent:6.2f}%")

        prompts = {
            20: "ACTION REQUIRED: calibrate the needle, then press RESUME",
            40: "ACTION REQUIRED: open the requested container, then press RESUME",
        }
        prompt_text = prompts.get(int(prompt or 0))
        if prompt_text:
            self.prompt_var.set(prompt_text)
            self.prompt_label.configure(fg=COLORS["warning"])
        elif display_message:
            self.prompt_var.set(str(display_message))
            self.prompt_label.configure(fg=COLORS["text_secondary"])
        elif normalized in {"printing", "paused"}:
            self.prompt_var.set("Virtual-SD execution is being monitored live")
            self.prompt_label.configure(fg=COLORS["text_secondary"])
        else:
            self.prompt_var.set("Ready for operator input")
            self.prompt_label.configure(fg=COLORS["text_muted"])

    def set_position(
        self,
        position: Optional[Sequence[Any]],
        homed_axes: str,
    ) -> None:
        if position is not None and len(position) >= 3:
            try:
                self.position_var.set(
                    "X {0:8.3f}   Y {1:8.3f}   Z {2:8.3f}".format(
                        float(position[0]),
                        float(position[1]),
                        float(position[2]),
                    )
                )
            except (TypeError, ValueError):
                self.position_var.set("X ---.---   Y ---.---   Z ---.---")
        else:
            self.position_var.set("X ---.---   Y ---.---   Z ---.---")
        axes = "".join(axis for axis in "xyz" if axis in str(homed_axes).lower())
        self.homed_var.set(f"HOMED: {axes.upper() if axes else '---'}")

    def set_live_z(self, value: Any) -> None:
        try:
            self.z_offset_var.set(f"LIVE Z  {float(value):+0.3f} mm")
        except (TypeError, ValueError):
            self.z_offset_var.set("LIVE Z  ---.--- mm")

    def set_manual_parse(
        self,
        summary: str,
        warnings: Sequence[str],
        *,
        valid: bool,
    ) -> None:
        warning_values = tuple(str(value) for value in warnings)
        detail = str(summary)
        if warning_values:
            detail += "\n" + warning_values[0]
            if len(warning_values) > 1:
                detail += f" (+{len(warning_values) - 1} more warning(s))"
        self.manual_parse_var.set(detail)
        self.manual_parse_label.configure(
            fg=(
                COLORS["warning"]
                if warning_values
                else (COLORS["success"] if valid else COLORS["error"])
            )
        )

    def show_console(self, entries: Sequence[Any]) -> None:
        values = tuple(
            (
                int(getattr(entry, "sequence", 0)),
                float(getattr(entry, "created_at", 0.0)),
                str(getattr(entry, "text", "")),
                str(getattr(entry, "level", "info")),
            )
            for entry in tuple(entries)[-12:]
        )
        if values == self._last_console_key:
            return
        self._last_console_key = values
        self.manual_console_text.configure(state="normal")
        self.manual_console_text.delete("1.0", "end")
        if not values:
            self.manual_console_text.insert(
                "end",
                "Klipper responses will appear here after a command is sent.",
            )
        else:
            for _sequence, _created_at, text, level in values:
                self.manual_console_text.insert(
                    "end",
                    f"{text}\n",
                    "error" if level == "error" else "",
                )
            self.manual_console_text.see("end")
        self.manual_console_text.configure(state="disabled")

    def show_gcode_context(
        self,
        artifact: Any,
        current_line: int,
        rows: Iterable[Tuple[int, str]],
    ) -> None:
        row_values = tuple(rows)
        artifact_path = str(getattr(artifact, "path", "")) if artifact else ""
        key = (artifact_path, int(current_line), row_values)
        if key == self._last_gcode_key:
            return
        self._last_gcode_key = key

        line_count = int(getattr(artifact, "line_count", 0) or 0)
        if artifact:
            self.gcode_title_var.set(
                "VIRTUAL-SD READ / QUEUED  /  "
                f"LINE {int(current_line) + 1:,} OF {line_count:,}"
            )
        else:
            self.gcode_title_var.set("VIRTUAL-SD READ / QUEUED  /  NO JOB")

        self.gcode_text.configure(state="normal")
        self.gcode_text.delete("1.0", "end")
        if not row_values:
            self.gcode_text.insert(
                "end",
                (
                    "Generated virtual-SD read-ahead context will appear here. "
                    "The cursor does not prove physical motion has completed."
                ),
            )
        else:
            for index, line in row_values:
                tag = (
                    "current"
                    if index == current_line
                    else ("read_before" if index < current_line else "")
                )
                prefix = ">" if index == current_line else " "
                self.gcode_text.insert(
                    "end",
                    f"{prefix}{index + 1:6d}  {line}\n",
                    tag,
                )
        self.gcode_text.configure(state="disabled")

    def set_control_state(
        self,
        *,
        connected: bool,
        ready: bool,
        print_state: str,
        virtual_sd_active: bool = False,
        homed_axes: str,
        offsets_enabled: bool,
        bed_mesh_active: bool = False,
        operation_busy: bool,
        runtime_started: bool,
        gcode_commands: Iterable[str] = (),
        remote_controls_ready: bool = False,
    ) -> None:
        normalized = str(print_state or "standby").lower()
        commands = {
            str(command).strip().upper()
            for command in gcode_commands
            if str(command).strip()
        }
        active = normalized in {"printing", "paused"}
        job_active = active or bool(virtual_sd_active)
        idle = (
            normalized not in {"printing", "paused"}
            and not bool(virtual_sd_active)
            and not operation_busy
        )
        can_start = connected and ready and idle and bool(remote_controls_ready)
        can_pause_resume = (
            connected
            and ready
            and active
            and bool(virtual_sd_active)
            and not operation_busy
        )
        can_cancel = connected and job_active and not operation_busy
        can_motion = (
            connected
            and ready
            and idle
            and set("xyz") <= set(str(homed_axes).lower())
            and not bool(offsets_enabled)
            and not bool(bed_mesh_active)
            and bool(remote_controls_ready)
            and "OPENSPOTTER_JOG" in commands
        )
        can_home = (
            connected
            and ready
            and idle
            and bool(remote_controls_ready)
            and "OPENSPOTTER_HOME" in commands
        )
        can_live_z = (
            connected
            and ready
            and active
            and bool(virtual_sd_active)
            and "z" in set(str(homed_axes).lower())
            and bool(offsets_enabled)
            and not operation_busy
            and bool(remote_controls_ready)
        )

        self.start_button.configure(state="normal" if can_start else "disabled")
        self.pause_button.configure(
            state="normal" if can_pause_resume else "disabled",
            text="RESUME" if normalized == "paused" else "PAUSE",
        )
        self.cancel_button.configure(state="normal" if can_cancel else "disabled")
        self.home_button.configure(state="normal" if can_home else "disabled")
        for button in self.jog_buttons:
            button.configure(state="normal" if can_motion else "disabled")
        self.jog_step_combo.configure(state="readonly" if can_motion else "disabled")
        self.jog_feed_entry.configure(state="normal" if can_motion else "disabled")
        for widget in (
            self.z_closer_button,
            self.z_reset_button,
            self.z_away_button,
        ):
            widget.configure(state="normal" if can_live_z else "disabled")
        self.z_step_combo.configure(state="readonly" if can_live_z else "disabled")
        self.manual_send_button.configure(
            state="normal" if connected and ready and idle else "disabled"
        )
        self.emergency_button.configure(
            state="normal" if runtime_started else "disabled"
        )


__all__ = ["MachineControlPanel"]
