import os
import traceback
import json

from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter.ttk import Notebook, Style, Label, Combobox
from PIL import ImageTk, Image


from .SpotterFunctions import entries_to_dict, read_entries, save_defaults, write_state
from .input_configs import CLEANING_FIELDS, GLOBAL_FIELDS, GRID_FIELDS, SPIRAL_FIELDS, WASHING_FIELDS, COLORS, FONTS
from .grid import Grid
from .spiral_grid import SpiralGrid
from .create_gcode import generate_anchor_calibration, save_file
from .canvas_drawer import CanvasDrawer
from .paths import GCODE_DIR, IMAGE_DIR

class DropletGui(tk.Tk):
    def __init__(self, config_dir):
        super(DropletGui, self).__init__()
        self.config_dir = config_dir
        self.global_input_frame = None
        self.canvas_frame = None
        self.canvas = None
        self.grid_tabs = None
        self.spiral_tabs = None
        self.grid_tab_dict = {}  # Map 1-based grid number to grid object
        self.spiral_tab_dict = {}  # Map 1-based spiral number to spiral object

        self.entry = []
        self.grid_count = 0
        self.spiral_count = 0

        # Setting up basic UI structure
        self.title('SDU-Spotter - Automated Liquid Dispenser')
        self.configure(bg=COLORS['bg_primary'])
        self._init_styles()
        # start window in windowed-fullscreen (maximized) on Windows
        try:
            self.state('zoomed')
        except Exception:
            pass

    def _init_styles(self):
        style = Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure(
            "Custom.TNotebook",
            background=COLORS['bg_tertiary'],
            borderwidth=0,
            padding=0
        )
        style.configure(
            "Custom.TNotebook.Tab",
            background=COLORS['bg_tertiary'],
            foreground=COLORS['text_primary'],
            padding=(10, 6),
        )
        style.map(
            "Custom.TNotebook.Tab",
            background=[("selected", '#4a4a5e')],
            foreground=[("selected", COLORS['text_primary'])]
        )

        # Configure root window to expand
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.main_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        self.main_frame.grid(sticky='nsew')
        self.main_frame.rowconfigure(0, weight=0)
        self.main_frame.rowconfigure(1, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=2)
        self.main_frame.columnconfigure(2, weight=1)

        # ========== TOP BAR: Mode selector and help ==========
        self.top_bar = tk.Frame(self.main_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.top_bar.grid(row=0, column=0, columnspan=3, sticky='ew', padx=5, pady=(5, 0))
        self.top_bar.columnconfigure(0, weight=0)
        self.top_bar.columnconfigure(1, weight=1)
        self.top_bar.columnconfigure(2, weight=0)

        top_label = tk.Label(self.top_bar, text='Workspace Mode', font=FONTS['header'], fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        top_label.grid(row=0, column=0, padx=10, pady=8, sticky='w')

        self.workspace_mode_var = tk.StringVar(value='grid')
        self.workspace_mode_combo = Combobox(self.top_bar, values=['grid', 'spiral'], textvariable=self.workspace_mode_var, state='readonly', font=FONTS['small'])
        self.workspace_mode_combo.grid(row=0, column=1, padx=10, pady=8, sticky='ew')
        self.workspace_mode_combo.bind('<<ComboboxSelected>>', lambda _e=None: self._switch_workspace_mode())

        help_button = tk.Button(self.top_bar, text='Help', command=self.show_help, bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['normal'], relief='flat', bd=0, padx=12, pady=6, cursor='hand2', activebackground='#00ffff', activeforeground=COLORS['bg_primary'])
        help_button.grid(row=0, column=2, padx=10, pady=8, sticky='e')

        # ========== LEFT FRAME: Grid Tabs ==========
        self.left_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.left_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        self.left_frame.rowconfigure(0, weight=0)
        self.left_frame.rowconfigure(1, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        self.left_label = tk.Label(self.left_frame, text="Grid Configuration", font=FONTS['header'], 
                             fg=COLORS['accent'], bg=COLORS['bg_primary'])
        self.left_label.grid(row=0, column=0, sticky='ew', pady=(0, 10))

        # Create tabbed interface for grids
        self.grid_tabs = Notebook(self.left_frame, style="Custom.TNotebook")
        self.grid_tabs.grid(row=1, column=0, sticky='nsew')

        self.spiral_tabs = Notebook(self.left_frame, style="Custom.TNotebook")
        self.spiral_tabs.grid(row=1, column=0, sticky='nsew')

        # ========== MIDDLE FRAME: Canvas and Inputs ==========
        self.middle_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.middle_frame.grid(row=1, column=1, sticky='nsew', padx=5, pady=5)
        self.middle_frame.rowconfigure(0, weight=3)
        self.middle_frame.rowconfigure(1, weight=1)
        self.middle_frame.rowconfigure(2, weight=1)
        self.middle_frame.columnconfigure(0, weight=1)

        # ---- Canvas at top ----
        self.canvas_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.canvas_frame.grid(row=0, column=0, sticky='nsew')
        self.canvas_frame.rowconfigure(1, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)
        
        canvas_label = tk.Label(self.canvas_frame, text="Canvas Area", font=FONTS['header'], 
                               fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        canvas_label.grid(row=0, column=0, sticky='ew', padx=10, pady=8)
        
        self.canvas = tk.Canvas(self.canvas_frame, width=800, height=500, bg=COLORS['bg_tertiary'], 
                               highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky='nsew', padx=8, pady=8)

        # ---- Canvas controls frame ----
        canvas_controls_frame = tk.Frame(self.canvas_frame, bg=COLORS['bg_secondary'])
        canvas_controls_frame.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 8))

        # Interaction hint
        hint = tk.Label(canvas_controls_frame, text='Scroll to zoom • Drag to pan', font=FONTS['small'],
                        fg=COLORS['text_secondary'], bg=COLORS['bg_secondary'])
        hint.pack(side='left', padx=(0, 5), pady=2)

        # ---- Build plate buttons frame (row 1) - moved below global config in right frame ----
        self.info_button_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.info_button_frame.grid(row=1, column=0, sticky='nsew', pady=(5, 0), padx=0)
        self.info_button_frame.columnconfigure(0, weight=1)

        info_label = tk.Label(self.info_button_frame, text="Build Plate Controls", font=FONTS['header'],
                             fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        info_label.pack(anchor='w', padx=10, pady=8)

        # Buttons frame
        self.button_frame = tk.Frame(self.info_button_frame, bg=COLORS['bg_secondary'])
        self.button_frame.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.create_buttons()
        self._switch_workspace_mode()

        # ---- Canvas input parameters (row 2) ----
        self.canvas_params_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.canvas_params_frame.grid(row=2, column=0, sticky='nsew', pady=(5, 0), padx=0)
        self.canvas_params_frame.columnconfigure(0, weight=1)

        params_label = tk.Label(self.canvas_params_frame, text="Canvas Parameters", font=FONTS['header'],
                               fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        params_label.pack(anchor='w', padx=10, pady=8)

        # Dispense -> diameter mapping entries
        map_frame = tk.Frame(self.canvas_params_frame, bg=COLORS['bg_secondary'])
        map_frame.pack(fill='x', padx=10, pady=(0, 8))

        lbl = tk.Label(map_frame, text='Dispense→Diameter mapping (volume ml → diameter mm)',
                      font=FONTS['normal'], fg=COLORS['text_primary'], bg=COLORS['bg_secondary'])
        lbl.pack(anchor='w', pady=(0, 6))

        rowf = tk.Frame(map_frame, bg=COLORS['bg_secondary'])
        rowf.pack(fill='x', pady=3)
        tk.Label(rowf, text='v1:', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_v1_entry = tk.Entry(rowf, width=8, font=FONTS['mono'], bg=COLORS['bg_tertiary'], 
                                     fg=COLORS['text_primary'], relief='flat', bd=1,
                                     insertbackground=COLORS['accent'])
        self.disp_v1_entry.insert(0, '0.04')
        self.disp_v1_entry.pack(side='left', padx=(2, 8))
        tk.Label(rowf, text='d1 (mm):', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_d1_entry = tk.Entry(rowf, width=8, font=FONTS['mono'], bg=COLORS['bg_tertiary'], 
                                     fg=COLORS['text_primary'], relief='flat', bd=1,
                                     insertbackground=COLORS['accent'])
        self.disp_d1_entry.insert(0, '0.6')
        self.disp_d1_entry.pack(side='left', padx=(2, 8))

        rowf2 = tk.Frame(map_frame, bg=COLORS['bg_secondary'])
        rowf2.pack(fill='x', pady=3)
        tk.Label(rowf2, text='v2:', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_v2_entry = tk.Entry(rowf2, width=8, font=FONTS['mono'], bg=COLORS['bg_tertiary'], 
                                     fg=COLORS['text_primary'], relief='flat', bd=1,
                                     insertbackground=COLORS['accent'])
        self.disp_v2_entry.insert(0, '0.08')
        self.disp_v2_entry.pack(side='left', padx=(2, 8))
        tk.Label(rowf2, text='d2 (mm):', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_d2_entry = tk.Entry(rowf2, width=8, font=FONTS['mono'], bg=COLORS['bg_tertiary'], 
                                     fg=COLORS['text_primary'], relief='flat', bd=1,
                                     insertbackground=COLORS['accent'])
        self.disp_d2_entry.insert(0, '1.2')
        self.disp_d2_entry.pack(side='left', padx=(2, 8))

        self._load_canvas_parameter_defaults()

        # ========== RIGHT FRAME: Global Configuration and Pictures ==========
        self.right_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.right_frame.grid(row=1, column=2, sticky='nsew', padx=5, pady=5)
        self.right_frame.rowconfigure(0, weight=1)
        self.right_frame.rowconfigure(1, weight=0)
        self.right_frame.columnconfigure(0, weight=1)

        # ---- Global input frame ----
        self.global_frame = tk.Frame(self.right_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.global_frame.grid(row=0, column=0, sticky='nsew')
        self.global_frame.columnconfigure(0, weight=1)
        self.global_frame.rowconfigure(1, weight=1)

        # Header frame with label and lock button
        global_header_frame = tk.Frame(self.global_frame, bg=COLORS['bg_secondary'])
        global_header_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=8)
        global_header_frame.columnconfigure(0, weight=1)
        global_header_frame.columnconfigure(1, weight=0)

        global_label = tk.Label(global_header_frame, text="Global Configuration", font=FONTS['header'],
                               fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        global_label.grid(row=0, column=0, sticky='w')

        # Lock/Unlock button
        self.global_locked = tk.BooleanVar(value=True)
        self.lock_button = tk.Button(
            global_header_frame,
            text="🔒",
            command=self._toggle_global_lock,
            bg=COLORS['bg_tertiary'], fg=COLORS['accent'], font=FONTS['normal'],
            relief='flat', bd=0, padx=8, pady=0, cursor='hand2',
            activebackground=COLORS['accent'], activeforeground=COLORS['bg_primary']
        )
        self.lock_button.grid(row=0, column=1, sticky='e', padx=(8, 0))

                # ---- Scrollable Global Input Frame ----
        global_container = tk.Frame(self.global_frame, bg=COLORS['bg_secondary'])
        global_container.grid(row=1, column=0, sticky='nsew', padx=8, pady=(0, 8))
        global_container.rowconfigure(0, weight=1)
        global_container.columnconfigure(0, weight=1)

        global_canvas = tk.Canvas(
            global_container,
            bg=COLORS['bg_secondary'],
            highlightthickness=0
        )

        global_scrollbar = tk.Scrollbar(
            global_container,
            orient='vertical',
            command=global_canvas.yview
        )

        self.global_input_frame = tk.Frame(
            global_canvas,
            bg=COLORS['bg_secondary']
        )

        self.global_input_frame.bind(
            "<Configure>",
            lambda e: global_canvas.configure(
                scrollregion=global_canvas.bbox("all")
            )
        )

        global_canvas.create_window(
            (0, 0),
            window=self.global_input_frame,
            anchor="nw"
        )

        global_canvas.configure(yscrollcommand=global_scrollbar.set)

        global_canvas.grid(row=0, column=0, sticky='nsew')
        global_scrollbar.grid(row=0, column=1, sticky='ns')


        # ---- Anchor calibration checkbox and button ----
        self.calibration_frame = tk.Frame(self.global_frame, bg=COLORS['bg_tertiary'], relief='flat', bd=0, highlightthickness=0)
        self.calibration_frame.grid(row=2, column=0, sticky='ew', padx=8, pady=8)
        self.calibration_frame.columnconfigure(0, weight=0)
        self.calibration_frame.columnconfigure(1, weight=1)

        self.anchor_calibration_enabled = tk.BooleanVar(value=False)
        calibration_checkbox = tk.Checkbutton(
            self.calibration_frame,
            text="Anchor Calibration",
            variable=self.anchor_calibration_enabled,
            command=self._toggle_calibration_button,
            bg=COLORS['bg_tertiary'], fg=COLORS['accent'], selectcolor=COLORS['bg_secondary'], font=FONTS['normal'],
            activebackground=COLORS['bg_tertiary'], activeforeground=COLORS['accent']
        )
        calibration_checkbox.grid(row=0, column=0, padx=0, pady=0, sticky="W")

        self.calibration_button = tk.Button(
            self.calibration_frame,
            text="Generate Anchor Calibration",
            command=lambda: self._run_action(self.generate_anchor_calibration, "Anchor Calibration"),
            bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['small'],
            relief='flat', bd=0, padx=10, pady=4, cursor='hand2',
            activebackground='#00ffff', activeforeground=COLORS['bg_primary'],
            state='disabled'
        )
        self.calibration_button.grid(row=0, column=1, padx=8, pady=0, sticky="E")
        
        # Initially hide the button
        self._toggle_calibration_button()

        # ---- Pictures frame (below global config) ----
        self.pictures_frame = tk.Frame(self.right_frame, bg=COLORS['bg_secondary'], relief='flat', bd=1, highlightbackground=COLORS['border'], highlightthickness=1)
        self.pictures_frame.grid(row=1, column=0, sticky='nsew', pady=(5, 0), padx=0)
        self.pictures_frame.columnconfigure(0, weight=1)
        self.pictures_frame.columnconfigure(1, weight=1)

        pictures_label = tk.Label(self.pictures_frame, text="Build Plate Images", font=FONTS['header'],
                                 fg=COLORS['accent'], bg=COLORS['bg_secondary'])
        pictures_label.grid(row=0, column=0, columnspan=2, sticky='ew', padx=10, pady=8)

        self.picture_frame = tk.Frame(self.pictures_frame, bg=COLORS['bg_secondary'])
        self.picture_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=8, pady=(0, 8))
        self.picture_frame.columnconfigure(0, weight=1)
        self.picture_frame.columnconfigure(1, weight=1)
        self.adding_pictures()

        # start canvas drawer
        try:
            self.canvas_drawer = CanvasDrawer(self)
            self.canvas_drawer.start()
        except Exception:
            pass

    def create_buttons(self):
        btn_frame = tk.Frame(self.button_frame, bg=COLORS['bg_secondary'])
        btn_frame.pack(fill='both', expand=True)

        self.add_object_button = tk.Button(btn_frame, text="add grid", command=lambda: self._run_action(self._add_active_object, "Add Object"),
                                bg=COLORS['success'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                activebackground='#00ff88', activeforeground=COLORS['bg_primary'])
        self.add_object_button.pack(side='top', padx=2, pady=2, fill='x')

        self.remove_object_button = tk.Button(btn_frame, text="remove grid", command=lambda: self._run_action(self._remove_active_object, "Remove Object"),
                                   bg=COLORS['error'], fg='white', font=FONTS['normal'],
                                   relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                   activebackground='#ff6b6b', activeforeground='white')
        self.remove_object_button.pack(side='top', padx=2, pady=2, fill='x')

        load_config_button = tk.Button(btn_frame, text="load config", command=lambda: self._run_action(self.load_generation_config, "Load Config"),
                                   bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                   relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                   activebackground='#00ffff', activeforeground=COLORS['bg_primary'])
        load_config_button.pack(side='top', padx=2, pady=2, fill='x')

        create_gcode_button = tk.Button(btn_frame, text="create G-code", command=lambda: self._run_action(self.save_file, "Create G-code"),
                                    bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                    relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                    activebackground='#00ffff', activeforeground=COLORS['bg_primary'])
        create_gcode_button.pack(side='top', padx=2, pady=2, fill='x')

        check_save_button = tk.Button(btn_frame, text="save defaults", command=lambda: self._run_action(self.check_saves, "Save Defaults"),
                                  bg=COLORS['alt_accent'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                  relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                  activebackground='#00ffaa', activeforeground=COLORS['bg_primary'])
        check_save_button.pack(side='top', padx=2, pady=2, fill='x')

    def _current_workspace_mode(self):
        try:
            return self.workspace_mode_var.get().strip().lower()
        except Exception:
            return 'grid'

    def _switch_workspace_mode(self):
        mode = self._current_workspace_mode()
        if mode == 'spiral':
            try:
                self.grid_tabs.grid_remove()
            except Exception:
                pass
            try:
                self.spiral_tabs.grid()
            except Exception:
                pass
            self.left_label.config(text='Spiral Configuration')
            self.add_object_button.config(text='add spiral')
            self.remove_object_button.config(text='remove spiral')
        else:
            try:
                self.spiral_tabs.grid_remove()
            except Exception:
                pass
            try:
                self.grid_tabs.grid()
            except Exception:
                pass
            self.left_label.config(text='Grid Configuration')
            self.add_object_button.config(text='add grid')
            self.remove_object_button.config(text='remove grid')

    def show_help(self):
        message = (
            'Grid mode manages row/column spotting tabs.\n\n'
            'Spiral mode manages spiral pattern tabs with drop or continuous extrusion.\n\n'
            'Use the dropdown at the top to switch between modes, then add or remove tabs for that mode.'
        )
        open_secondary_window(message, title='Help')

    def _add_active_object(self):
        if self._current_workspace_mode() == 'spiral':
            return self.instance_spiral()
        return self.instance_grid()

    def _remove_active_object(self):
        if self._current_workspace_mode() == 'spiral':
            return self.subtract_spiral()
        return self.subtract_grid()

    def _run_action(self, action, action_name="Action"):
        """Unified action runner for UI callbacks with consistent error popups."""
        try:
            return action()
        except ValueError as exc:
            open_secondary_window(f"{action_name} failed:\n{exc}", title="Input Error")
        except Exception as exc:
            # Keep traceback in console for debugging while showing a user-friendly popup.
            traceback.print_exc()
            open_secondary_window(f"{action_name} failed:\n{exc}", title="Unexpected Error")

    def _iter_grids(self):
        for grid_number in sorted(self.grid_tab_dict.keys()):
            yield grid_number, self.grid_tab_dict[grid_number]

    def _iter_spirals(self):
        for spiral_number in sorted(self.spiral_tab_dict.keys()):
            yield spiral_number, self.spiral_tab_dict[spiral_number]

    def _update_grid_tab_title(self, grid_number, title):
        tab_index = grid_number - 1
        if tab_index < 0 or tab_index >= len(self.grid_tabs.tabs()):
            return
        cleaned = str(title).strip() or f"Grid {grid_number}"
        self.grid_tabs.tab(tab_index, text=cleaned)

    def _get_max_grid_count(self):
        default_max = 6
        if not self.entry:
            return default_max
        try:
            global_dict = entries_to_dict(self.entry, GLOBAL_FIELDS)
            max_count = int(global_dict.get('max_grid_count', default_max))
        except Exception:
            max_count = default_max
        return max(1, max_count)


    def instance_grid(self):
        """Create a new grid in a new tab."""
        max_grid_count = self._get_max_grid_count()
        if self.grid_count >= max_grid_count:
            open_secondary_window(f"Cannot add more grids (maximum {max_grid_count})")
            return

        grid_number = self.grid_count + 1

        # Create new tab
        tab_frame = tk.Frame(self.grid_tabs)
        self.grid_tabs.add(tab_frame, text=f"Grid {grid_number}")
        
        # Create Grid object within the tab
        config_file = os.path.join(self.config_dir, f"config_grid_{grid_number}.json")
        if not os.path.exists(config_file):
            config_file = os.path.join(self.config_dir, "config_grid_1.json")
        grid_colors = ["lightgreen", "orange", "lightblue", "gold", "violet", "salmon"]
        
        grid_obj = Grid(
            tab_frame,
            0,
            0,
            config_file,
            grid_colors[(grid_number - 1) % len(grid_colors)],
            self.config_dir,
            grid_number=grid_number,
            on_name_changed=lambda name, gn=grid_number: self._update_grid_tab_title(gn, name),
        )
        
        self.grid_tab_dict[grid_number] = grid_obj
        self.grid_count = len(self.grid_tab_dict)
        self._update_grid_tab_title(grid_number, grid_obj.get_grid_name())

    def instance_spiral(self):
        """Create a new spiral object in a new tab."""
        max_spiral_count = self._get_max_grid_count()
        if self.spiral_count >= max_spiral_count:
            open_secondary_window(f"Cannot add more spirals (maximum {max_spiral_count})")
            return

        spiral_number = self.spiral_count + 1
        tab_frame = tk.Frame(self.spiral_tabs)
        self.spiral_tabs.add(tab_frame, text=f"Spiral {spiral_number}")

        config_file = os.path.join(self.config_dir, f"config_spiral_{spiral_number}.json")
        if not os.path.exists(config_file):
            config_file = os.path.join(self.config_dir, "config_spiral_1.json")
        spiral_colors = ["lightgreen", "orange", "lightblue", "gold", "violet", "salmon"]

        spiral_obj = SpiralGrid(
            tab_frame,
            config_file,
            spiral_colors[(spiral_number - 1) % len(spiral_colors)],
            self.config_dir,
            spiral_number=spiral_number,
            on_name_changed=lambda name, sn=spiral_number: self._update_spiral_tab_title(sn, name),
        )

        self.spiral_tab_dict[spiral_number] = spiral_obj
        self.spiral_count = len(self.spiral_tab_dict)
        self._update_spiral_tab_title(spiral_number, spiral_obj.get_grid_name())

    def subtract_spiral(self):
        """Remove the last spiral tab."""
        if self.spiral_count == 0:
            open_secondary_window("No spirals to remove")
            return

        last_spiral_number = self.spiral_count
        self.spiral_tabs.forget(last_spiral_number - 1)
        self.spiral_tab_dict.pop(last_spiral_number, None)
        self.spiral_count = len(self.spiral_tab_dict)
        try:
            if hasattr(self, 'canvas_drawer') and self.canvas_drawer:
                self.canvas_drawer.refresh()
        except Exception:
            pass

    def subtract_grid(self):
        """Remove the last grid tab."""
        if self.grid_count == 0:
            open_secondary_window("No grids to remove")
            return

        # Always remove the last grid to maintain consistent grid numbering
        last_grid_number = self.grid_count
        
        # Remove the last tab
        self.grid_tabs.forget(last_grid_number - 1)
        
        # Clean up grid references
        self.grid_tab_dict.pop(last_grid_number, None)
        self.grid_count = len(self.grid_tab_dict)
        try:
            if hasattr(self, 'canvas_drawer') and self.canvas_drawer:
                self.canvas_drawer.refresh()
        except Exception:
            pass

    def _update_spiral_tab_title(self, spiral_number, title):
        try:
            self.spiral_tabs.tab(spiral_number - 1, text=title)
        except Exception:
            pass

    def check_saves(self):
        # Save counts for both collections
        write_state({"grid_count": self.grid_count, "spiral_count": self.spiral_count}, self.config_dir)

        # Convert global entries to dict
        global_dict = entries_to_dict(self.entry, GLOBAL_FIELDS)
        global_dict.update(self._get_canvas_parameter_values())
        save_defaults(os.path.join(self.config_dir, "config_global.json"), global_dict)

        # Save each grid using dicts for grid, cleaning, washing
        for grid_number, grid_obj in self._iter_grids():
            cfg_path = os.path.join(self.config_dir, f"config_grid_{grid_number}.json")

            grid_dict = entries_to_dict(grid_obj.grid_entry, GRID_FIELDS)
            cleaning_dict = entries_to_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
            washing_dict = entries_to_dict(grid_obj.washing_entry, WASHING_FIELDS)
            grid_state_dict = {
                "grid_name": grid_obj.get_grid_name(),
                "grid_color": grid_obj.get_grid_color(),
                "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
                "washing_enabled": bool(grid_obj.washing_enabled.get()),
                "wash_after_loading": bool(grid_obj.wash_after_loading_enabled.get()),
                "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
                "final_rinse_add_cleaning_grid": bool(grid_obj.final_rinse_add_cleaning_grid.get()),
            }

            save_defaults(cfg_path, grid_dict, cleaning_dict, washing_dict, grid_state_dict)
            print(f"✅ Saved grid {grid_number} defaults to {cfg_path}")

        for spiral_number, spiral_obj in self._iter_spirals():
            cfg_path = os.path.join(self.config_dir, f"config_spiral_{spiral_number}.json")
            spiral_dict = spiral_obj.save_defaults_dict()
            spiral_state_dict = {
                "spiral_name": spiral_obj.get_grid_name(),
                "spiral_color": spiral_obj.get_grid_color(),
            }
            save_defaults(cfg_path, spiral_dict, spiral_state_dict)
            print(f"✅ Saved spiral {spiral_number} defaults to {cfg_path}")

    def _get_canvas_parameter_values(self):
        def _safe_float(entry_widget, fallback):
            try:
                return float(entry_widget.get())
            except Exception:
                return fallback

        return {
            "disp_v1": _safe_float(self.disp_v1_entry, 0.04),
            "disp_d1": _safe_float(self.disp_d1_entry, 0.6),
            "disp_v2": _safe_float(self.disp_v2_entry, 0.08),
            "disp_d2": _safe_float(self.disp_d2_entry, 1.2),
        }

    def _load_canvas_parameter_defaults(self):
        cfg_path = os.path.join(self.config_dir, "config_global.json")
        if not os.path.exists(cfg_path):
            return

        try:
            with open(cfg_path, "r") as f:
                data = json.load(f)
        except Exception:
            return

        if not isinstance(data, dict):
            return

        def _set_if_present(entry_widget, key):
            if key in data:
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, str(data[key]))

        _set_if_present(self.disp_v1_entry, "disp_v1")
        _set_if_present(self.disp_d1_entry, "disp_d1")
        _set_if_present(self.disp_v2_entry, "disp_v2")
        _set_if_present(self.disp_d2_entry, "disp_d2")



    def adding_pictures(self):
        image = Image.open(IMAGE_DIR / "BasePlate.png")
        resized_image = image.resize((200*2, 170*2))
        photo = ImageTk.PhotoImage(resized_image)

        label_picture = Label(self.picture_frame, image=photo)
        label_picture.image = photo
        label_picture.grid(row=0, column=0, padx=5, pady=5)

        try:
            image = Image.open(IMAGE_DIR / "spots.png")
            photo = ImageTk.PhotoImage(image)
            spots_picture = Label(self.picture_frame, image=photo)
            spots_picture.image = photo
            spots_picture.grid(row=0, column=1, padx=5, pady=5)
        except Exception:
            pass

    def save_file(self):
        save_file(self)

    def _toggle_calibration_button(self):
        """Show/hide and enable/disable the calibration button based on checkbox state."""
        if self.anchor_calibration_enabled.get():
            self.calibration_button.grid()  # Show button
            self.calibration_button.config(state='normal')
        else:
            self.calibration_button.grid_remove()  # Hide button

    def generate_anchor_calibration(self):
        """Generate anchor calibration G-code."""
        generate_anchor_calibration(self)

    def _toggle_global_lock(self):
        """Toggle global configuration lock with warning popup."""
        if self.global_locked.get():
            # Currently locked, trying to unlock
            result = messagebox.showwarning(
                "Warning",
                "double check for needle crashing",
                type=messagebox.OKCANCEL
            )
            if result == messagebox.OK:
                # User confirmed, unlock the fields
                self.global_locked.set(False)
                self._update_global_fields_state()
                self.lock_button.config(text="🔓")
        else:
            # Currently unlocked, lock it
            self.global_locked.set(True)
            self._update_global_fields_state()
            self.lock_button.config(text="🔒")

    def _update_global_fields_state(self):
        """Update the state of all global input fields based on lock state."""
        is_locked = self.global_locked.get()
        state = 'disabled' if is_locked else 'normal'
        
        # Disable/enable all entry fields in global_input_frame
        for widget in self.entry:
            if isinstance(widget, tk.Entry):
                widget.config(state=state)

    def check_inputs(self):
        global_entry = read_entries(self.entry)
        # Read global offsets (for positioning, not sizing)
        first_x_off = float(global_entry[2]) if len(global_entry) > 2 else 0.0
        first_y_off = float(global_entry[3]) if len(global_entry) > 3 else 0.0
        # absolute build plate origin (for rectangle positioning)
        x_abs = float(global_entry[0]) if len(global_entry) > 0 else 0.0
        y_abs = float(global_entry[1]) if len(global_entry) > 1 else 0.0

        # rectangle params (must match canvas_drawer)
        rect_w = 20.0
        rect_h = 40.0
        # inner acceptance rectangle dimensions (mm)
        inner_w = 19.0
        inner_h = 39.0
        # require minimum inset from left and bottom (mm)
        inset_lb = 0.5

        exceeded = []

        rect_x = x_abs + first_x_off
        rect_y = y_abs + first_y_off
        inner_vis_x = rect_x + (rect_w - inner_w) / 2.0
        inner_vis_y = rect_y + (rect_h - inner_h) / 2.0
        inner_origin_x = inner_vis_x + inset_lb
        inner_origin_y = inner_vis_y + inset_lb
        inner_max_x = inner_origin_x + inner_w
        inner_max_y = inner_origin_y + inner_h

        def exceeds_acceptance(start_x, start_y, width, height):
            end_x = start_x + width
            end_y = start_y + height
            return (
                start_x < inner_origin_x or
                start_y < inner_origin_y or
                end_x > inner_max_x or
                end_y > inner_max_y
            )

        # Helper to check a grid safely
        def check_grid_obj(grid_obj, grid_idx):
            try:
                vals = read_entries(grid_obj.grid_entry)
            except Exception:
                return
            # vals expected: rows, cols, x_step, y_step, ..., grid_offset_x, grid_offset_y
            try:
                rows = int(vals[0])
                cols = int(vals[1])
                x_step = float(vals[2])
                y_step = float(vals[3])
                grid_x_off = float(vals[9]) if len(vals) > 9 else 0.0
                grid_y_off = float(vals[10]) if len(vals) > 10 else 0.0
            except Exception:
                return

            # Compute grid physical span (independent per-grid): (n-1)*step between first and last
            grid_width = (cols - 1) * x_step if cols > 0 else 0.0
            grid_height = (rows - 1) * y_step if rows > 0 else 0.0

            # grid absolute start/end positions
            start_abs_x = rect_x + grid_x_off
            start_abs_y = rect_y + grid_y_off

            if exceeds_acceptance(start_abs_x, start_abs_y, grid_width, grid_height):
                exceeded.append(str(grid_idx))

            # Cleaning grid uses same first-spot anchor and may shift each cleaning cycle.
            if not getattr(grid_obj, 'cleaning_enabled', tk.BooleanVar()).get():
                return

            try:
                cleaning_dict = entries_to_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
                c_rows = int(cleaning_dict.get('rows_cleaning', 0))
                c_cols = int(cleaning_dict.get('cols_cleaning', 0))
                c_pitch_x = float(cleaning_dict.get('pitch_x_cleaning', 0.0))
                c_pitch_y = float(cleaning_dict.get('pitch_y_cleaning', 0.0))
                c_grid_x_off = float(cleaning_dict.get('grid_offset_x_cleaning', 0.0))
                c_grid_y_off = float(cleaning_dict.get('grid_offset_y_cleaning', 0.0))
                c_rel_x = float(cleaning_dict.get('x_relative_increase', 0.0))
                c_rel_y = float(cleaning_dict.get('y_relative_increase', 0.0))
            except Exception:
                return

            c_width = (c_cols - 1) * c_pitch_x if c_cols > 0 else 0.0
            c_height = (c_rows - 1) * c_pitch_y if c_rows > 0 else 0.0

            cycle_starts = [(rect_x + c_grid_x_off, rect_y + c_grid_y_off)]

            if getattr(grid_obj, 'washing_enabled', tk.BooleanVar()).get():
                try:
                    washing_vals = read_entries(grid_obj.washing_entry)
                    washing_after = int(washing_vals[5]) if len(washing_vals) > 5 else 0
                except Exception:
                    washing_after = 0

                if washing_after > 0:
                    total_spots = max(0, rows * cols)
                    washing_spot_counter = 0
                    cycle_index = 1
                    for _ in range(total_spots):
                        washing_spot_counter += 1
                        if washing_spot_counter % washing_after == 0:
                            cycle_starts.append((
                                rect_x + c_grid_x_off + cycle_index * c_rel_x,
                                rect_y + c_grid_y_off + cycle_index * c_rel_y,
                            ))
                            cycle_index += 1
                            washing_spot_counter = 0

            for start_cx, start_cy in cycle_starts:
                if exceeds_acceptance(start_cx, start_cy, c_width, c_height):
                    exceeded.append(f"{grid_idx} (cleaning)")
                    break

        # Check each existing grid independently
        for grid_number, grid_obj in self._iter_grids():
            check_grid_obj(grid_obj, grid_number)

        if exceeded:
            if len(exceeded) == 1:
                open_secondary_window(f"Grid {exceeded[0]} exceeds acceptance size of 19x39 mm")
            else:
                open_secondary_window(f"Grids {', '.join(exceeded)} exceed acceptance size of 19x39 mm")

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False

    def _coerce_value(self, raw, unit):
        if unit == "int":
            return int(float(raw))
        if unit in ("mm", "uL", "s", "mm/s"):
            return float(raw)
        return raw

    def _set_entry_value(self, entry_widget, value):
        original_state = str(entry_widget.cget('state'))
        if original_state == 'disabled':
            entry_widget.config(state='normal')
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, str(value))
        if original_state == 'disabled':
            entry_widget.config(state='disabled')

    def _set_field_entries(self, entry_widgets, fields, values_dict):
        for entry_widget, field in zip(entry_widgets, fields):
            if field.key in values_dict:
                self._set_entry_value(entry_widget, values_dict[field.key])

    def _reset_grids(self):
        # Remove all tabs and clear map so we can rebuild exact saved state.
        for tab_id in self.grid_tabs.tabs():
            self.grid_tabs.forget(tab_id)
        self.grid_tab_dict.clear()
        self.grid_count = 0

    def _reset_spirals(self):
        for tab_id in self.spiral_tabs.tabs():
            self.spiral_tabs.forget(tab_id)
        self.spiral_tab_dict.clear()
        self.spiral_count = 0

    def _parse_generation_settings_file(self, filepath):
        result = {
            "global_settings": {},
            "grid_settings": [],
            "spiral_settings": [],
        }

        global_field_map = {f.key: f for f in GLOBAL_FIELDS}
        grid_field_map = {f.key: f for f in GRID_FIELDS}
        cleaning_field_map = {f.key: f for f in CLEANING_FIELDS}
        washing_field_map = {f.key: f for f in WASHING_FIELDS}

        current_section = None
        current_subsection = None
        current_grid = None

        with open(filepath, "r") as f:
            for raw_line in f:
                line = raw_line.rstrip('\n')
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.startswith('[') and stripped.endswith(']'):
                    current_section = stripped[1:-1]
                    current_subsection = None
                    if current_section.startswith('grid_'):
                        current_grid = {
                            "grid": {},
                            "cleaning": {},
                            "washing": {},
                        }
                        result["grid_settings"].append(current_grid)
                    elif current_section.startswith('spiral_'):
                        current_grid = {
                            "spiral": {},
                        }
                        result["spiral_settings"].append(current_grid)
                    else:
                        current_grid = None
                    continue

                if current_section == "global_settings":
                    if '=' in stripped:
                        key, value = stripped.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        field = global_field_map.get(key)
                        if field:
                            try:
                                result["global_settings"][key] = self._coerce_value(value, field.unit)
                            except Exception:
                                result["global_settings"][key] = value
                    continue

                if not (current_section and current_section.startswith('grid_') and current_grid is not None):
                    if not (current_section and current_section.startswith('spiral_') and current_grid is not None):
                        continue

                if stripped in ("grid:", "cleaning:", "washing:", "spiral:"):
                    current_subsection = stripped[:-1]
                    continue

                if '=' not in stripped:
                    continue

                key, value = stripped.split('=', 1)
                key = key.strip()
                value = value.strip()

                if key in (
                    "spiral_name",
                    "spiral_color",
                    "grid_name",
                    "grid_color",
                    "cleaning_enabled",
                    "washing_enabled",
                    "wash_after_loading",
                    "final_rinse_enabled",
                    "final_rinse_add_cleaning_grid",
                ):
                    if key in ("grid_name", "grid_color", "spiral_name", "spiral_color"):
                        current_grid[key] = value
                    else:
                        current_grid[key] = self._parse_bool(value)
                    continue

                if current_section and current_section.startswith('spiral_'):
                    if current_subsection in (None, "spiral"):
                        current_grid.setdefault("spiral", {})[key] = value
                    continue

                if current_subsection == "grid":
                    field = grid_field_map.get(key)
                    if field:
                        try:
                            current_grid["grid"][key] = self._coerce_value(value, field.unit)
                        except Exception:
                            current_grid["grid"][key] = value
                elif current_subsection == "cleaning":
                    field = cleaning_field_map.get(key)
                    if field:
                        try:
                            current_grid["cleaning"][key] = self._coerce_value(value, field.unit)
                        except Exception:
                            current_grid["cleaning"][key] = value
                elif current_subsection == "washing":
                    field = washing_field_map.get(key)
                    if field:
                        try:
                            current_grid["washing"][key] = self._coerce_value(value, field.unit)
                        except Exception:
                            current_grid["washing"][key] = value

        return result

    def load_generation_config(self):
        filepath = filedialog.askopenfilename(
            title="Load generation settings",
            initialdir=str(GCODE_DIR),
            filetypes=[("Settings snapshot", "*_settings.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not filepath:
            return

        parsed = self._parse_generation_settings_file(filepath)

        global_settings = parsed.get("global_settings", {})
        if global_settings:
            self._set_field_entries(self.entry, GLOBAL_FIELDS, global_settings)

        grid_settings = parsed.get("grid_settings", [])
        spiral_settings = parsed.get("spiral_settings", [])
        self._reset_grids()
        for _ in range(len(grid_settings)):
            self.instance_grid()
        self._reset_spirals()
        for _ in range(len(spiral_settings)):
            self.instance_spiral()

        for idx, grid_state in enumerate(grid_settings, start=1):
            grid_obj = self.grid_tab_dict.get(idx)
            if grid_obj is None:
                continue

            self._set_field_entries(grid_obj.grid_entry, GRID_FIELDS, grid_state.get("grid", {}))
            self._set_field_entries(grid_obj.cleaning_entry, CLEANING_FIELDS, grid_state.get("cleaning", {}))
            self._set_field_entries(grid_obj.washing_entry, WASHING_FIELDS, grid_state.get("washing", {}))

            if "grid_name" in grid_state:
                grid_obj.set_grid_name(grid_state.get("grid_name", f"Grid {idx}"))
            if "grid_color" in grid_state:
                grid_obj.set_grid_color(grid_state.get("grid_color", "green"))
            self._update_grid_tab_title(idx, grid_obj.get_grid_name())

            grid_obj.cleaning_enabled.set(bool(grid_state.get("cleaning_enabled", False)))
            grid_obj.washing_enabled.set(bool(grid_state.get("washing_enabled", False)))
            grid_obj.wash_after_loading_enabled.set(bool(grid_state.get("wash_after_loading", False)))
            grid_obj.final_rinse_enabled.set(bool(grid_state.get("final_rinse_enabled", False)))
            grid_obj.final_rinse_add_cleaning_grid.set(bool(grid_state.get("final_rinse_add_cleaning_grid", False)))

            grid_obj._toggle_cleaning_inputs()
            grid_obj._toggle_washing_inputs()
            grid_obj._toggle_final_rinse_inputs()

        for idx, spiral_state in enumerate(spiral_settings, start=1):
            spiral_obj = self.spiral_tab_dict.get(idx)
            if spiral_obj is None:
                continue
            self._set_field_entries(spiral_obj.spiral_entry, SPIRAL_FIELDS, spiral_state.get("spiral", {}))
            if "spiral_name" in spiral_state:
                spiral_obj.set_grid_name(spiral_state.get("spiral_name", f"Spiral {idx}"))
            if "spiral_color" in spiral_state:
                spiral_obj.set_grid_color(spiral_state.get("spiral_color", "green"))

        # Respect current lock state after values are loaded.
        self._update_global_fields_state()
        try:
            if hasattr(self, 'canvas_drawer') and self.canvas_drawer:
                self.canvas_drawer.refresh()
        except Exception:
            pass

def open_secondary_window(text, title="Notice"):
    secondary_window = tk.Toplevel()
    secondary_window.title(title)
    secondary_window.config(width=400, height=200, bg=COLORS['bg_primary'])
    # Create a button to close (destroy) this window.
    button_close = tk.Button(
        secondary_window,
        text=f"{text}\n\nClose",
        command=secondary_window.destroy,
        bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['normal'],
        relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
        activebackground='#00ffff', activeforeground=COLORS['bg_primary']
    )
    button_close.place(x=75, y=75)
