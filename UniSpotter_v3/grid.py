from gui_v3 import *
from SpotterFunctions import *
from input_configs import GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS
import tkinter as tk
import logging


class Grid(object):
    def __init__(self, gui, frame_row, frame_col, config, background, config_dir):
        self.gui = gui
        self.config_dir = config_dir
        self.grid_entry = None
        self.input_frame = None
        self.grid_entry = []
        self.cleaning_entry = []
        self.washing_entry = []
        self.cleaning_widgets = []  # Store cleaning widgets for show/hide
        self.washing_widgets = []  # Store washing widgets for show/hide
        self.grid = None
        self.frame_row = frame_row
        self.frame_col = frame_col
        self.create_grid(config, background)

        

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
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def create_grid(self, config, background):
        # Create a scrollable frame within the tab
        main_container = tk.Frame(self.gui, bg='#1e1e2e')
        main_container.grid(row=0, column=0, sticky='nsew')
        main_container.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        self.gui.rowconfigure(0, weight=1)
        self.gui.columnconfigure(0, weight=1)

        # Create canvas for scrolling
        canvas = tk.Canvas(main_container, bg='#1e1e2e', highlightthickness=0)
        scrollbar = tk.Scrollbar(main_container, orient='vertical', command=canvas.yview, bg='#2a2a3e', troughcolor='#1e1e2e')
        scrollable_frame = tk.Frame(canvas, bg='#1e1e2e')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        self.master_input_frame = scrollable_frame
        self.master_input_frame.config(bg='#1e1e2e', border=0)

        self.grid_input_frame = tk.Frame(self.master_input_frame, bg='#2a2a3e', relief='flat', bd=1, highlightbackground='#444455', highlightthickness=1)
        self.grid_input_frame.pack(fill='x', padx=8, pady=8)
        
        Grid_label = tk.Label(self.grid_input_frame, text="Grid Configuration", bg='#2a2a3e', fg='#00d4ff', 
                             font=("Segoe UI", 11, "bold"))
        Grid_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        self.cleaning_input_frame = tk.Frame(self.master_input_frame, bg='#2a2a3e', relief='flat', bd=1, highlightbackground='#444455', highlightthickness=1)
        self.cleaning_input_frame.pack(fill='x', padx=8, pady=8)
        
        Cleaning_label = tk.Label(self.cleaning_input_frame, text="Cleaning Configuration", bg='#2a2a3e', fg='#00d4ff',
                                 font=("Segoe UI", 11, "bold"))
        Cleaning_label.grid(row=0, column=0, columnspan=3, pady=8, padx=8)

        config_path = os.path.join(self.config_dir, config)
        with open(config_path, "r") as f:
            grid_defaults = json.load(f)
        
        create_labels(
            GRID_FIELDS,
            grid_defaults,
            self.grid_entry,
            self.grid_input_frame,
            self.gui
            )

        # Add checkbox to enable/disable cleaning grid at row 1
        self.cleaning_enabled = tk.BooleanVar(value=False)
        cleaning_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Cleaning Grid",
            variable=self.cleaning_enabled,
            command=self._toggle_cleaning_inputs,
            bg='#2a2a3e', fg='#00ff88', selectcolor='#1e1e2e', font=("Segoe UI", 10),
            activebackground='#2a2a3e', activeforeground='#00ff88'
        )
        cleaning_checkbox.grid(row=1, column=0, columnspan=3, pady=8, padx=8, sticky="W")
        self.cleaning_widgets.append(cleaning_checkbox)

        create_labels(
            CLEANING_FIELDS,
            grid_defaults,
            self.cleaning_entry,
            self.cleaning_input_frame,
            self.gui,
            start_row=2,
            widgets_list=self.cleaning_widgets
        )
        
        # Add checkbox to enable/disable washing needle at row 10 (after cleaning inputs)
        self.washing_enabled = tk.BooleanVar(value=False)
        washing_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Washing Needle",
            variable=self.washing_enabled,
            command=self._toggle_washing_inputs,
            bg='#2a2a3e', fg='#00d4ff', selectcolor='#1e1e2e', font=("Segoe UI", 10),
            activebackground='#2a2a3e', activeforeground='#00d4ff'
        )
        washing_checkbox.grid(row=10, column=0, columnspan=3, pady=8, padx=8, sticky="W")
        self.washing_widgets.append(washing_checkbox)

        create_labels(
            WASHING_FIELDS,
            grid_defaults,
            self.washing_entry,
            self.cleaning_input_frame,
            self.gui,
            start_row=11,
            widgets_list=self.washing_widgets
            )
        # Initially hide washing inputs
        self._toggle_washing_inputs()
        
        # Initially hide cleaning inputs
        self._toggle_cleaning_inputs()


def create_labels(fields, defaults, entries, input_frame,
                gui=None, start_row=1, widgets_list=None):

    for i, field in enumerate(fields):
        label = tk.Label(
            input_frame,
            text=field.label,
            bg='#2a2a3e', fg='#ffffff',
            font=("Segoe UI", 9)
        )

        entry = tk.Entry(
            input_frame, bd=0, relief='flat',
            bg='#3a3a4e', fg='#00d4ff',
            font=("Segoe UI", 9, "bold"),
            insertbackground='#00d4ff'
        )

        unit = tk.Label(
            input_frame,
            text=field.unit,
            bg='#2a2a3e', fg='#888899',
            font=("Segoe UI", 8)
        )

        # Insert default value
        value = defaults.get(field.key, field.default)
        entry.insert(0, str(value))

        # Canvas update hook
        if gui and hasattr(gui, 'canvas_drawer'):
            entry.bind('<KeyRelease>', lambda e: gui.canvas_drawer._poll())

        row = start_row + i
        label.grid(row=row, column=0, sticky="WE", pady=4, padx=8)
        entry.grid(row=row, column=1, sticky="WE", padx=4, pady=4)
        unit.grid(row=row, column=2, sticky="W", pady=4, padx=4)

        entries.append(entry)

        if widgets_list is not None:
            widgets_list.extend([label, entry, unit])



