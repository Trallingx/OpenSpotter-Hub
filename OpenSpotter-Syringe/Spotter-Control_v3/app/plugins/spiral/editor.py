"""Tk editor for the built-in spiral application-pattern plugin."""

import json
import os
import tkinter as tk
import tkinter.ttk as ttk
from collections.abc import Mapping

from ...core.configuration import entries_to_dict
from ...core.ui.forms import create_labels
from .fields import SPIRAL_FIELDS
from ...runtime_logging import get_logger, log_options
from ...ui_theme import COLORS, FONTS, entry_options


logger = get_logger("gui.spiral")


class SpiralGrid:
    """Edit one spiral recipe while retaining the legacy grid-like API."""

    def __init__(
        self,
        gui,
        config,
        background,
        config_dir,
        spiral_number=None,
        on_name_changed=None,
    ):
        self.gui = gui
        self.config_dir = config_dir
        self.spiral_number = spiral_number
        self.on_name_changed = on_name_changed
        self.spiral_name_var = tk.StringVar()
        self.spiral_color_var = tk.StringVar()
        self.default_color = background
        self.spiral_entry = []
        self.spiral_widgets = []
        self.frame = None
        self.create_spiral(config)

    def get_name(self):
        """Return the neutral display name used by generic workspace shells."""

        value = self.spiral_name_var.get().strip()
        if value:
            return value
        if self.spiral_number is not None:
            return f"Spiral {self.spiral_number}"
        return "Spiral"

    def set_name(self, name):
        self.spiral_name_var.set(str(name).strip())

    def get_color(self):
        """Return the configured preview color."""

        value = self.spiral_color_var.get().strip()
        return value if value else self.default_color

    def set_color(self, color):
        self.spiral_color_var.set(str(color).strip())

    def get_grid_name(self):
        """Compatibility alias for :meth:`get_name`."""

        return self.get_name()

    def set_grid_name(self, name):
        """Compatibility alias for :meth:`set_name`."""

        self.set_name(name)

    def get_grid_color(self):
        """Compatibility alias for :meth:`get_color`."""

        return self.get_color()

    def set_grid_color(self, color):
        """Compatibility alias for :meth:`set_color`."""

        self.set_color(color)

    def _handle_name_change(self, *_):
        if callable(self.on_name_changed):
            try:
                self.on_name_changed(self.get_name())
            except Exception:
                pass

    def _install_name_change_trace(self):
        """Bind display-name changes exactly once during editor construction."""

        return self.spiral_name_var.trace_add(
            "write",
            self._handle_name_change,
        )

    @staticmethod
    def _restore_entries(entries, fields, values):
        for entry_widget, field in zip(entries, fields):
            if field.key not in values:
                continue
            value = values[field.key]
            if isinstance(entry_widget, ttk.Combobox):
                if str(field.unit).strip().lower() == "bool":
                    enabled = (
                        value
                        if isinstance(value, bool)
                        else str(value).strip().lower()
                        in ("1", "true", "yes", "on")
                    )
                    entry_widget.set("True" if enabled else "False")
                else:
                    entry_widget.set(str(value))
                continue
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, str(value))

    def serialize(self):
        """Return the canonical profile payload for this spiral editor."""

        return {
            "spiral_name": self.get_name(),
            "spiral_color": self.get_color(),
            "spiral": entries_to_dict(
                self.spiral_entry,
                SPIRAL_FIELDS,
            ),
        }

    def defaults_dict(self):
        """Return flattened values suitable for indexed default persistence."""

        profile = self.serialize()
        defaults = dict(profile["spiral"])
        defaults.update(
            {
                "spiral_name": profile["spiral_name"],
                "spiral_color": profile["spiral_color"],
            }
        )
        return defaults

    def restore(self, payload):
        """Restore either a canonical profile entry or flattened defaults."""

        if not isinstance(payload, Mapping):
            raise TypeError("Spiral profile entry must be a mapping")
        spiral_values = payload.get("spiral", payload)
        if not isinstance(spiral_values, Mapping):
            raise TypeError("Spiral profile values must be a mapping")
        self._restore_entries(
            self.spiral_entry,
            SPIRAL_FIELDS,
            spiral_values,
        )
        name = payload.get("spiral_name", spiral_values.get("name"))
        color = payload.get("spiral_color", spiral_values.get("color"))
        if name is not None:
            self.set_name(name)
        if color is not None:
            self.set_color(color)

    def create_spiral(self, config):
        self.frame = tk.Frame(self.gui, bg=COLORS['bg_primary'])
        self.frame.grid(row=0, column=0, sticky='nsew')
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(0, weight=1)

        scroll_canvas = tk.Canvas(
            self.frame,
            bg=COLORS['bg_primary'],
            highlightthickness=0,
            bd=0,
        )
        scrollbar = ttk.Scrollbar(
            self.frame,
            orient='vertical',
            command=scroll_canvas.yview,
        )
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scroll_canvas.grid(row=0, column=0, sticky='nsew', padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky='ns', padx=(0, 8), pady=8)

        outer = tk.Frame(self.frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        outer.columnconfigure(1, weight=1)
        outer_window = scroll_canvas.create_window((0, 0), window=outer, anchor='nw')

        def _update_scrollregion(_event=None):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox('all'))

        def _sync_content_width(event):
            scroll_canvas.itemconfigure(outer_window, width=event.width)

        outer.bind('<Configure>', _update_scrollregion)
        scroll_canvas.bind('<Configure>', _sync_content_width)
        self.scroll_canvas = scroll_canvas

        header = tk.Label(outer, text='SPIRAL RECIPE', bg=COLORS['bg_secondary'], fg=COLORS['text_primary'], font=FONTS['label'])
        header.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        config_path = os.path.join(self.config_dir, config)
        with open(config_path, 'r', encoding="utf-8") as f:
            defaults = json.load(f)
        log_options(
            logger,
            "spiral.options_loaded",
            spiral_number=self.spiral_number,
            config_path=config_path,
            options=defaults,
        )

        default_name = defaults.get('spiral_name', f'Spiral {self.spiral_number}' if self.spiral_number is not None else 'Spiral')
        self.spiral_name_var.set(str(default_name))
        self._install_name_change_trace()

        name_label = tk.Label(outer, text='Spiral Name', bg=COLORS['bg_secondary'], fg=COLORS['text_primary'], font=FONTS['small'])
        name_entry = tk.Entry(outer, textvariable=self.spiral_name_var, **entry_options())
        name_label.grid(row=1, column=0, sticky='WE', pady=4, padx=8)
        name_entry.grid(row=1, column=1, sticky='WE', padx=4, pady=4)

        color_options = ['green', 'orange', 'blue', 'goldenrod', 'purple', 'brown', 'red', 'cyan', 'magenta', 'black']
        default_color = str(defaults.get('spiral_color', self.default_color))
        if default_color not in color_options:
            color_options.append(default_color)
        self.spiral_color_var.set(default_color)

        color_label = tk.Label(outer, text='Spiral Color', bg=COLORS['bg_secondary'], fg=COLORS['text_primary'], font=FONTS['small'])
        color_combo = ttk.Combobox(outer, values=color_options, textvariable=self.spiral_color_var, state='readonly', font=FONTS['small'])
        color_label.grid(row=2, column=0, sticky='WE', pady=4, padx=8)
        color_combo.grid(row=2, column=1, sticky='WE', padx=4, pady=4)

        def _notify_change(_event=None):
            try:
                if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                    self.gui.canvas_drawer.request_redraw()
            except Exception:
                pass

        color_combo.bind('<<ComboboxSelected>>', _notify_change)

        create_labels(
            SPIRAL_FIELDS,
            defaults,
            self.spiral_entry,
            outer,
            self.gui,
            start_row=3,
            widgets_list=self.spiral_widgets,
        )
        self._handle_name_change()

    def save_defaults_dict(self):
        spiral_dict = {}
        for entry_widget, field in zip(self.spiral_entry, SPIRAL_FIELDS):
            try:
                spiral_dict[field.key] = entry_widget.get()
            except Exception:
                spiral_dict[field.key] = field.default
        return spiral_dict
