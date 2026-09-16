"""Tk editor for the built-in grid application-pattern plugin."""

import json
import os
import tkinter as tk
import tkinter.ttk as ttk
from collections.abc import Mapping

from ...core.configuration import entries_to_dict
from ...core.ui.forms import create_labels
from .fields import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS
from ...runtime_logging import get_logger, log_options
from ...ui_theme import COLORS, FONTS, entry_options


logger = get_logger("gui.grid")


class Grid:
    """Edit one grid recipe and its optional maintenance-cycle settings."""

    def __init__(
        self,
        gui,
        frame_row=None,
        frame_col=None,
        config=None,
        background="green",
        config_dir="",
        grid_number=None,
        on_name_changed=None,
    ):
        # frame_row/frame_col are accepted for compatibility with the original
        # constructor. Layout has always been owned by the containing tab.
        self.gui = gui
        self.config_dir = config_dir
        self.grid_number = grid_number
        self.on_name_changed = on_name_changed
        self.grid_name_var = tk.StringVar()
        self.grid_color_var = tk.StringVar()
        self.default_color = background
        self.grid_entry = []
        self.cleaning_entry = []
        self.washing_entry = []
        self.cleaning_widgets = []  # Store cleaning widgets for show/hide
        self.washing_widgets = []  # Store washing widgets for show/hide
        self.wash_after_loading_widgets = []  # Store wash-after-loading widgets for show/hide
        self.final_rinse_widgets = []  # Store final rinse widgets for show/hide
        if config is None:
            raise ValueError("Grid editor requires a configuration file")
        self.create_grid(config)

    def get_name(self):
        """Return the neutral display name used by generic workspace shells."""

        value = self.grid_name_var.get().strip()
        if value:
            return value
        if self.grid_number is not None:
            return f"Grid {self.grid_number}"
        return "Grid"

    def set_name(self, name):
        self.grid_name_var.set(str(name).strip())

    def get_color(self):
        """Return the configured preview color."""

        value = self.grid_color_var.get().strip()
        return value if value else self.default_color

    def set_color(self, color):
        self.grid_color_var.set(str(color).strip())

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

    @staticmethod
    def _restore_entries(entries, fields, values):
        for entry_widget, field in zip(entries, fields):
            if field.key not in values:
                continue
            value = values[field.key]
            if isinstance(entry_widget, ttk.Combobox):
                if str(field.unit).strip().lower() == "bool":
                    entry_widget.set("True" if bool(value) else "False")
                else:
                    entry_widget.set(str(value))
                continue
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, str(value))

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def serialize(self):
        """Return the canonical profile payload for this grid editor."""

        return {
            "grid_name": self.get_name(),
            "grid_color": self.get_color(),
            "grid": entries_to_dict(self.grid_entry, GRID_FIELDS),
            "cleaning": entries_to_dict(
                self.cleaning_entry,
                CLEANING_FIELDS,
            ),
            "washing": entries_to_dict(
                self.washing_entry,
                WASHING_FIELDS,
            ),
            "cleaning_enabled": bool(self.cleaning_enabled.get()),
            "washing_enabled": bool(self.washing_enabled.get()),
            "wash_after_loading": bool(
                self.wash_after_loading_enabled.get()
            ),
            "final_rinse_enabled": bool(self.final_rinse_enabled.get()),
            "final_rinse_add_cleaning_grid": bool(
                self.final_rinse_add_cleaning_grid.get()
            ),
        }

    def defaults_dict(self):
        """Return the historical flattened per-grid defaults payload."""

        profile = self.serialize()
        defaults = {}
        defaults.update(profile["grid"])
        defaults.update(profile["cleaning"])
        defaults.update(profile["washing"])
        defaults.update(
            {
                "grid_name": profile["grid_name"],
                "grid_color": profile["grid_color"],
                "cleaning_enabled": profile["cleaning_enabled"],
                "washing_enabled": profile["washing_enabled"],
                "wash_after_loading": profile["wash_after_loading"],
                "final_rinse_enabled": profile["final_rinse_enabled"],
                "final_rinse_add_cleaning_grid": profile[
                    "final_rinse_add_cleaning_grid"
                ],
            }
        )
        return defaults

    def save_defaults_dict(self):
        """Compatibility-friendly alias for flattened default persistence."""

        return self.defaults_dict()

    def restore(self, payload):
        """Restore either a canonical profile entry or flattened defaults."""

        if not isinstance(payload, Mapping):
            raise TypeError("Grid profile entry must be a mapping")
        grid_values = payload.get("grid", payload)
        cleaning_values = payload.get("cleaning", payload)
        washing_values = payload.get("washing", payload)
        for label, values in (
            ("grid", grid_values),
            ("cleaning", cleaning_values),
            ("washing", washing_values),
        ):
            if not isinstance(values, Mapping):
                raise TypeError(
                    "Grid profile {!r} values must be a mapping".format(label)
                )

        self._restore_entries(self.grid_entry, GRID_FIELDS, grid_values)
        self._restore_entries(
            self.cleaning_entry,
            CLEANING_FIELDS,
            cleaning_values,
        )
        self._restore_entries(
            self.washing_entry,
            WASHING_FIELDS,
            washing_values,
        )

        name = payload.get("grid_name", grid_values.get("name"))
        color = payload.get("grid_color", grid_values.get("color"))
        if name is not None:
            self.set_name(name)
        if color is not None:
            self.set_color(color)

        flag_sources = (
            ("cleaning_enabled", self.cleaning_enabled),
            ("washing_enabled", self.washing_enabled),
            ("wash_after_loading", self.wash_after_loading_enabled),
            ("final_rinse_enabled", self.final_rinse_enabled),
            (
                "final_rinse_add_cleaning_grid",
                self.final_rinse_add_cleaning_grid,
            ),
        )
        for key, variable in flag_sources:
            if key in payload:
                variable.set(self._as_bool(payload[key]))

        self._toggle_cleaning_inputs()
        self._toggle_washing_inputs()
        self._toggle_final_rinse_inputs()

    def _handle_grid_name_change(self, *_):
        if callable(self.on_name_changed):
            try:
                self.on_name_changed(self.get_name())
            except Exception:
                pass

    def _toggle_cleaning_inputs(self):
        """Show/hide cleaning input widgets based on checkbox state."""
        is_enabled = self.cleaning_enabled.get()
        log_options(
            logger,
            "grid.cleaning_option_changed",
            grid_number=getattr(self, "grid_number", None),
            enabled=bool(is_enabled),
        )
        # Hide/show all cleaning input widgets except the checkbox itself
        for widget in self.cleaning_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer.request_redraw()
        except Exception:
            pass

    def _toggle_washing_inputs(self):
        """Show/hide washing input widgets based on checkbox state."""
        is_enabled = self.washing_enabled.get()
        log_options(
            logger,
            "grid.washing_option_changed",
            grid_number=getattr(self, "grid_number", None),
            enabled=bool(is_enabled),
            wash_after_loading=bool(self.wash_after_loading_enabled.get()),
        )
        # Hide/show all washing input widgets except the checkbox itself
        for widget in self.washing_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()

        # Keep wash-after-loading visible only when washing is enabled.
        for widget in self.wash_after_loading_widgets:
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer.request_redraw()
        except Exception:
            pass

    def _toggle_final_rinse_inputs(self):
        """Show/hide final rinse widgets based on checkbox state."""
        is_enabled = self.final_rinse_enabled.get()
        log_options(
            logger,
            "grid.final_rinse_option_changed",
            grid_number=getattr(self, "grid_number", None),
            enabled=bool(is_enabled),
            add_cleaning_grid=bool(self.final_rinse_add_cleaning_grid.get()),
        )
        # Hide/show all final rinse widgets except the checkbox itself
        for widget in self.final_rinse_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer.request_redraw()
        except Exception:
            pass

    def create_grid(self, config):
        # Create a scrollable frame within the tab
        main_container = tk.Frame(self.gui, bg=COLORS['bg_primary'])
        main_container.grid(row=0, column=0, sticky='nsew')
        main_container.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        self.gui.rowconfigure(0, weight=1)
        self.gui.columnconfigure(0, weight=1)

        # Create canvas for scrolling
        canvas = tk.Canvas(main_container, bg=COLORS['bg_primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            main_container,
            orient='vertical',
            command=canvas.yview,
        )
        scrollable_frame = tk.Frame(canvas, bg=COLORS['bg_primary'])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        scrollable_window = canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.bind(
            '<Configure>',
            lambda event: canvas.itemconfigure(scrollable_window, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        self.master_input_frame = scrollable_frame
        self.master_input_frame.config(bg=COLORS['bg_primary'], border=0)

        # Store canvas reference for scroll wheel binding
        self.canvas = canvas

        self.grid_input_frame = tk.Frame(self.master_input_frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        self.grid_input_frame.pack(fill='x', padx=8, pady=8)

        Grid_label = tk.Label(self.grid_input_frame, text="GRID RECIPE", bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
                             font=FONTS['label'])
        Grid_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        self.cleaning_input_frame = tk.Frame(self.master_input_frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        self.cleaning_input_frame.pack(fill='x', padx=8, pady=8)

        Cleaning_label = tk.Label(self.cleaning_input_frame, text="MAINTENANCE CYCLE", bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
                                 font=FONTS['label'])
        Cleaning_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        config_path = os.path.join(self.config_dir, config)
        with open(config_path, "r", encoding="utf-8") as f:
            grid_defaults = json.load(f)
        log_options(
            logger,
            "grid.options_loaded",
            grid_number=self.grid_number,
            config_path=config_path,
            options=grid_defaults,
        )

        def _to_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return default

        default_grid_name = grid_defaults.get(
            "grid_name",
            f"Grid {self.grid_number}" if self.grid_number is not None else "Grid"
        )
        self.grid_name_var.set(str(default_grid_name))
        self.grid_name_var.trace_add("write", self._handle_grid_name_change)

        grid_name_label = tk.Label(
            self.grid_input_frame,
            text="Grid Name",
            bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
            font=FONTS['small']
        )
        grid_name_entry = tk.Entry(
            self.grid_input_frame,
            textvariable=self.grid_name_var,
            **entry_options(),
        )
        grid_name_label.grid(row=1, column=0, sticky="WE", pady=4, padx=8)
        grid_name_entry.grid(row=1, column=1, sticky="WE", padx=4, pady=4)

        color_options = ["green", "orange", "blue", "goldenrod", "purple", "brown", "red", "cyan", "magenta", "black"]
        default_grid_color = str(grid_defaults.get("grid_color", self.default_color))
        if default_grid_color not in color_options:
            color_options.append(default_grid_color)
        self.grid_color_var.set(default_grid_color)

        grid_color_label = tk.Label(
            self.grid_input_frame,
            text="Grid Color",
            bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
            font=FONTS['small']
        )
        grid_color_combo = ttk.Combobox(
            self.grid_input_frame,
            values=color_options,
            textvariable=self.grid_color_var,
            state="readonly",
            font=FONTS['small']
        )
        grid_color_label.grid(row=2, column=0, sticky="WE", pady=4, padx=8)
        grid_color_combo.grid(row=2, column=1, sticky="WE", padx=4, pady=4)

        def _notify_color_change(_event=None):
            try:
                if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                    self.gui.canvas_drawer.request_redraw()
            except Exception:
                pass

        grid_color_combo.bind("<<ComboboxSelected>>", _notify_color_change)

        create_labels(
            GRID_FIELDS,
            grid_defaults,
            self.grid_entry,
            self.grid_input_frame,
            self.gui,
            start_row=3,
            )

        self._handle_grid_name_change()


        # Add checkbox to enable/disable cleaning grid at row 1
        self.cleaning_enabled = tk.BooleanVar(
            value=_to_bool(grid_defaults.get("cleaning_enabled", False))
        )
        cleaning_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Cleaning Grid",
            variable=self.cleaning_enabled,
            command=self._toggle_cleaning_inputs,
            bg=COLORS['bg_secondary'], fg=COLORS['alt_accent'], selectcolor=COLORS['bg_primary'], font=FONTS['normal'],
            activebackground=COLORS['bg_secondary'], activeforeground=COLORS['alt_accent']
        )
        cleaning_checkbox.grid(row=1, column=0, columnspan=3, pady=8, padx=8, sticky="W")
        self.cleaning_widgets.append(cleaning_checkbox)

        cleaning_start_row = 2
        create_labels(
            CLEANING_FIELDS,
            grid_defaults,
            self.cleaning_entry,
            self.cleaning_input_frame,
            self.gui,
            start_row=cleaning_start_row,
            widgets_list=self.cleaning_widgets
        )

        # Align final-rinse toggle with the final_rinse_cycles field (last cleaning row).
        final_rinse_row = cleaning_start_row + len(CLEANING_FIELDS) - 1
        self.final_rinse_enabled = tk.BooleanVar(
            value=_to_bool(grid_defaults.get("final_rinse_enabled", False))
        )
        final_rinse_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Final Rinse",
            variable=self.final_rinse_enabled,
            command=self._toggle_final_rinse_inputs,
            bg=COLORS['bg_secondary'], fg=COLORS['alt_accent'], selectcolor=COLORS['bg_primary'], font=FONTS['normal'],
            activebackground=COLORS['bg_secondary'], activeforeground=COLORS['alt_accent']
        )
        final_rinse_checkbox.grid(row=final_rinse_row, column=0, pady=8, padx=8, sticky="W")
        self.final_rinse_widgets.append(final_rinse_checkbox)

        # Reflow the final_rinse_cycles widgets one row below the checkbox.
        final_rinse_label, final_rinse_entry, final_rinse_unit = self.cleaning_widgets[-3:]
        final_rinse_label.grid_configure(row=final_rinse_row + 1, column=0, sticky="W", padx=4)
        final_rinse_entry.grid_configure(row=final_rinse_row + 1, column=1, sticky="WE", padx=4)
        final_rinse_unit.grid_configure(row=final_rinse_row + 1, column=2, sticky="W", padx=4)
        self.final_rinse_widgets.extend([final_rinse_label, final_rinse_entry, final_rinse_unit])

        # Add "Add Cleaning Grid" checkbox below final rinse (only shows when final_rinse_enabled is checked)
        self.final_rinse_add_cleaning_grid = tk.BooleanVar(
            value=_to_bool(grid_defaults.get("final_rinse_add_cleaning_grid", False))
        )
        add_cleaning_grid_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Add Cleaning Grid",
            variable=self.final_rinse_add_cleaning_grid,
            bg=COLORS['bg_secondary'], fg=COLORS['alt_accent'], selectcolor=COLORS['bg_primary'], font=FONTS['normal'],
            activebackground=COLORS['bg_secondary'], activeforeground=COLORS['alt_accent']
        )
        add_cleaning_grid_checkbox.grid(row=final_rinse_row + 2, column=0, pady=8, padx=8, sticky="W")
        self.final_rinse_widgets.append(add_cleaning_grid_checkbox)

        washing_start_row = cleaning_start_row + len(CLEANING_FIELDS) + 3
        # Add checkbox to enable/disable washing needle after cleaning inputs
        self.washing_enabled = tk.BooleanVar(
            value=_to_bool(grid_defaults.get("washing_enabled", False))
        )
        washing_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Washing Needle",
            variable=self.washing_enabled,
            command=self._toggle_washing_inputs,
            bg=COLORS['bg_secondary'], fg=COLORS['accent'], selectcolor=COLORS['bg_primary'], font=FONTS['normal'],
            activebackground=COLORS['bg_secondary'], activeforeground=COLORS['accent']
        )
        washing_checkbox.grid(row=washing_start_row, column=0, columnspan=3, pady=8, padx=8, sticky="W")
        self.washing_widgets.append(washing_checkbox)

        create_labels(
            WASHING_FIELDS,
            grid_defaults,
            self.washing_entry,
            self.cleaning_input_frame,
            self.gui,
            start_row=washing_start_row + 1,
            widgets_list=self.washing_widgets
            )

        wash_after_loading_row = washing_start_row + 1 + len(WASHING_FIELDS)
        self.wash_after_loading_enabled = tk.BooleanVar(
            value=_to_bool(grid_defaults.get("wash_after_loading", False))
        )
        wash_after_loading_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Wash After Loading",
            variable=self.wash_after_loading_enabled,
            bg=COLORS['bg_secondary'], fg=COLORS['accent'], selectcolor=COLORS['bg_primary'], font=FONTS['normal'],
            activebackground=COLORS['bg_secondary'], activeforeground=COLORS['accent']
        )
        wash_after_loading_checkbox.grid(row=wash_after_loading_row, column=0, columnspan=3, pady=8, padx=8, sticky="W")
        self.wash_after_loading_widgets.append(wash_after_loading_checkbox)

        # Initially hide washing inputs
        self._toggle_washing_inputs()

        # Initially hide final rinse inputs
        self._toggle_final_rinse_inputs()

        # Initially hide cleaning inputs
        self._toggle_cleaning_inputs()
