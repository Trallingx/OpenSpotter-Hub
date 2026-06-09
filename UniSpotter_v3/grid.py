import json
import os
from input_configs import GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS, COLORS, FONTS
import tkinter as tk
import tkinter.ttk as ttk


class Grid(object):
    def __init__(self, gui, frame_row, frame_col, config, background, config_dir, grid_number=None, on_name_changed=None):
        self.gui = gui
        self.config_dir = config_dir
        self.grid_number = grid_number
        self.on_name_changed = on_name_changed
        self.grid_name_var = tk.StringVar()
        self.grid_color_var = tk.StringVar()
        self.default_color = background
        self.grid_entry = None
        self.input_frame = None
        self.grid_entry = []
        self.cleaning_entry = []
        self.washing_entry = []
        self.cleaning_widgets = []  # Store cleaning widgets for show/hide
        self.washing_widgets = []  # Store washing widgets for show/hide
        self.wash_after_loading_widgets = []  # Store wash-after-loading widgets for show/hide
        self.final_rinse_widgets = []  # Store final rinse widgets for show/hide
        self.grid = None
        self.frame_row = frame_row
        self.frame_col = frame_col
        self.create_grid(config, background)

    def get_grid_name(self):
        value = self.grid_name_var.get().strip()
        if value:
            return value
        if self.grid_number is not None:
            return f"Grid {self.grid_number}"
        return "Grid"

    def set_grid_name(self, name):
        self.grid_name_var.set(str(name).strip())

    def get_grid_color(self):
        value = self.grid_color_var.get().strip()
        return value if value else self.default_color

    def set_grid_color(self, color):
        self.grid_color_var.set(str(color).strip())

    def _handle_grid_name_change(self, *_):
        if callable(self.on_name_changed):
            try:
                self.on_name_changed(self.get_grid_name())
            except Exception:
                pass

    def _toggle_cleaning_inputs(self):
        """Show/hide cleaning input widgets based on checkbox state."""
        is_enabled = self.cleaning_enabled.get()
        # Hide/show all cleaning input widgets except the checkbox itself
        for widget in self.cleaning_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def _toggle_washing_inputs(self):
        """Show/hide washing input widgets based on checkbox state."""
        is_enabled = self.washing_enabled.get()
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
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def _toggle_final_rinse_inputs(self):
        """Show/hide final rinse widgets based on checkbox state."""
        is_enabled = self.final_rinse_enabled.get()
        # Hide/show all final rinse widgets except the checkbox itself
        for widget in self.final_rinse_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def create_grid(self, config, background):
        # Create a scrollable frame within the tab
        main_container = tk.Frame(self.gui, bg=COLORS['bg_primary'])
        main_container.grid(row=0, column=0, sticky='nsew')
        main_container.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        self.gui.rowconfigure(0, weight=1)
        self.gui.columnconfigure(0, weight=1)

        # Create canvas for scrolling
        canvas = tk.Canvas(main_container, bg=COLORS['bg_primary'], highlightthickness=0)
        scrollbar = tk.Scrollbar(main_container, orient='vertical', command=canvas.yview, bg=COLORS['bg_secondary'], troughcolor=COLORS['bg_primary'])
        scrollable_frame = tk.Frame(canvas, bg=COLORS['bg_primary'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        self.master_input_frame = scrollable_frame
        self.master_input_frame.config(bg=COLORS['bg_primary'], border=0)
        
        # Store canvas reference for scroll wheel binding
        self.canvas = canvas

        self.grid_input_frame = tk.Frame(self.master_input_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.grid_input_frame.pack(fill='x', padx=8, pady=8)
        
        Grid_label = tk.Label(self.grid_input_frame, text="Grid Configuration", bg=COLORS['bg_secondary'], fg=COLORS['accent'], 
                             font=FONTS['header'])
        Grid_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        self.cleaning_input_frame = tk.Frame(self.master_input_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.cleaning_input_frame.pack(fill='x', padx=8, pady=8)
        
        Cleaning_label = tk.Label(self.cleaning_input_frame, text="Cleaning Configuration", bg=COLORS['bg_secondary'], fg=COLORS['accent'],
                                 font=FONTS['header'])
        Cleaning_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        config_path = os.path.join(self.config_dir, config)
        with open(config_path, "r") as f:
            grid_defaults = json.load(f)

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
            bd=0, relief='flat',
            bg=COLORS['bg_tertiary'], fg=COLORS['accent'],
            font=(FONTS['small'][0], FONTS['small'][1], 'bold'),
            insertbackground=COLORS['accent']
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
                    self.gui.canvas_drawer._poll()
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


def create_labels(fields, defaults, entries, input_frame,
                gui=None, start_row=1, widgets_list=None):

    tabs = [f.tab for f in fields if getattr(f, 'tab', '')]
    use_tabs = bool(tabs)
    tab_frames = {}
    row_map = {}

    parent_for_field = input_frame
    if use_tabs:
        notebook = ttk.Notebook(input_frame, style="Custom.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")
        input_frame.rowconfigure(0, weight=1)
        input_frame.columnconfigure(0, weight=1)
        seen = []
        for field in fields:
            tab_name = field.tab
            if tab_name in seen or not tab_name:
                continue
            seen.append(tab_name)
            frame = tk.Frame(notebook, bg=COLORS['bg_tertiary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
            for col in range(3):
                frame.columnconfigure(col, weight=1 if col == 1 else 0)
            # Keep the first rows unstretched so inputs stay at the top
            frame.rowconfigure(0, weight=0)
            notebook.add(frame, text=tab_name)
            tab_frames[tab_name] = frame
            row_map[tab_name] = start_row
    else:
        input_frame.columnconfigure(1, weight=1)

    for i, field in enumerate(fields):
        tab_name = getattr(field, 'tab', '')
        parent_for_field = tab_frames.get(tab_name, input_frame)
        if use_tabs and tab_name:
            row = row_map[tab_name]
            row_map[tab_name] += 1
        else:
            row = start_row + i

        label = tk.Label(
            parent_for_field,
            text=field.label,
            bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
            font=FONTS['small']
        )

        # Use specialized widgets for some field types (dropdowns for spiral options)
        if getattr(field, 'key', '') == 'spiral_mode':
            entry = ttk.Combobox(
                parent_for_field,
                values=['drop', 'continuous'],
                state='readonly',
                font=FONTS['small']
            )
        elif getattr(field, 'key', '') == 'interleave':
            # Represent boolean interleave as a dropdown with explicit choices
            entry = ttk.Combobox(
                parent_for_field,
                values=['False', 'True'],
                state='readonly',
                font=FONTS['small']
            )
        else:
            entry = tk.Entry(
                parent_for_field, bd=0, relief='flat',
                bg=COLORS['bg_tertiary'], fg=COLORS['accent'],
                font=(FONTS['small'][0], FONTS['small'][1], 'bold'),
                insertbackground=COLORS['accent']
            )

        unit = tk.Label(
            parent_for_field,
            text=field.unit,
            bg=COLORS['bg_secondary'], fg=COLORS['text_secondary'],
            font=(FONTS['small'][0], 8)
        )

        # Insert default value
        value = defaults.get(field.key, field.default)
        # For comboboxes, set the value via set; for Entry use insert
        try:
            if isinstance(entry, ttk.Combobox):
                # Normalize boolean defaults for the interleave combobox
                if getattr(field, 'key', '') == 'interleave':
                    entry.set('True' if bool(value) else 'False')
                else:
                    entry.set(str(value))
            else:
                entry.insert(0, str(value))
        except Exception:
            # Fallback to simple insert
            try:
                entry.insert(0, str(value))
            except Exception:
                pass

        # Canvas update hook: bind both key events for Entry and selection events for Combobox
        if gui and hasattr(gui, 'canvas_drawer'):
            if isinstance(entry, ttk.Combobox):
                entry.bind('<<ComboboxSelected>>', lambda e: gui.canvas_drawer._poll())
            else:
                entry.bind('<KeyRelease>', lambda e: gui.canvas_drawer._poll())

        label.grid(row=row, column=0, sticky="WE", pady=4, padx=8)
        entry.grid(row=row, column=1, sticky="WE", padx=4, pady=4)
        unit.grid(row=row, column=2, sticky="W", pady=4, padx=4)

        entries.append(entry)

        if widgets_list is not None:
            widgets_list.extend([label, entry, unit])



