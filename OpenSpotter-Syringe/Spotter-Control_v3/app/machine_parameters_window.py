"""Persistent editor window for global machine parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .grid import create_labels
from .ui_theme import COLORS, FONTS, button_options


class MachineParametersWindow(tk.Toplevel):
    """Maximized, decorated parameter editor that is hidden instead of destroyed."""

    def __init__(
        self,
        parent,
        *,
        locked_var,
        on_toggle_lock,
        on_save,
    ):
        super().__init__(parent)
        self.withdraw()
        self.title("OpenSpotter | Machine Parameters")
        self.configure(bg=COLORS["bg_primary"])
        self.minsize(720, 500)
        self.overrideredirect(False)
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.bind("<Escape>", self.hide)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._populated = False

        panel = tk.Frame(
            self,
            bg=COLORS["bg_secondary"],
            relief="flat",
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        header = tk.Frame(panel, bg=COLORS["bg_secondary"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.columnconfigure(0, weight=1)

        title_frame = tk.Frame(header, bg=COLORS["bg_secondary"])
        title_frame.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_frame,
            text="GLOBAL MACHINE PARAMETERS",
            font=FONTS["header"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text=(
                "Machine geometry, container positions, motion, fluids, and "
                "runtime utility defaults"
            ),
            font=FONTS["caption"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg_secondary"],
        ).pack(anchor="w", pady=(2, 0))

        self.lock_button = tk.Button(
            header,
            text="LOCKED" if locked_var.get() else "EDITING",
            command=on_toggle_lock,
            **button_options("ghost"),
        )
        self.lock_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        parameter_container = tk.Frame(panel, bg=COLORS["bg_secondary"])
        parameter_container.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 8),
        )
        parameter_container.rowconfigure(0, weight=1)
        parameter_container.columnconfigure(0, weight=1)

        self.parameter_canvas = tk.Canvas(
            parameter_container,
            bg=COLORS["bg_secondary"],
            highlightthickness=0,
            bd=0,
        )
        scrollbar = ttk.Scrollbar(
            parameter_container,
            orient="vertical",
            command=self.parameter_canvas.yview,
        )
        self.input_frame = tk.Frame(
            self.parameter_canvas,
            bg=COLORS["bg_secondary"],
        )
        self._input_window = self.parameter_canvas.create_window(
            (0, 0),
            window=self.input_frame,
            anchor="nw",
        )
        self.input_frame.bind("<Configure>", self._sync_scrollregion)
        self.parameter_canvas.bind("<Configure>", self._resize_input_window)
        self.parameter_canvas.configure(yscrollcommand=scrollbar.set)
        self.parameter_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        footer = tk.Frame(panel, bg=COLORS["bg_secondary"])
        footer.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            text=(
                "Keep parameters locked during normal operation. Review travel "
                "limits before saving geometry changes."
            ),
            font=FONTS["caption"],
            fg=COLORS["warning"],
            bg=COLORS["bg_secondary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Button(
            footer,
            text="SAVE DEFAULTS",
            command=on_save,
            **button_options("secondary"),
        ).grid(row=0, column=1, sticky="e", padx=(12, 4))
        tk.Button(
            footer,
            text="CLOSE",
            command=self.hide,
            **button_options("primary"),
        ).grid(row=0, column=2, sticky="e", padx=(4, 0))

    def populate(self, fields, defaults, entries, *, gui=None):
        """Create the tabbed global inputs once while preserving ``entries``."""
        if self._populated:
            raise RuntimeError("Machine parameters have already been populated")
        create_labels(
            fields,
            defaults,
            entries,
            self.input_frame,
            gui=gui,
        )
        self._populated = True
        self.input_frame.update_idletasks()
        self._sync_scrollregion()

    def show(self):
        """Reveal the existing editor and restore its maximized window state."""
        self.deiconify()
        self._maximize()
        self.lift()
        try:
            self.focus_set()
        except tk.TclError:
            pass
        return self

    def hide(self, _event=None):
        """Keep widgets and values alive while removing the editor from view."""
        self.withdraw()
        return "break"

    def _maximize(self):
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass

        try:
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass

        self.geometry(
            f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
        )

    def _sync_scrollregion(self, _event=None):
        self.parameter_canvas.configure(
            scrollregion=self.parameter_canvas.bbox("all")
        )

    def _resize_input_window(self, event):
        self.parameter_canvas.itemconfigure(
            self._input_window,
            width=event.width,
        )
