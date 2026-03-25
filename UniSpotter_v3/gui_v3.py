import os
import traceback

from tkinter import messagebox
import tkinter as tk
from tkinter.ttk import Notebook, Style, Label
from PIL import ImageTk, Image


from SpotterFunctions import entries_to_dict, read_entries, save_defaults, write_state
from input_configs import CLEANING_FIELDS, GLOBAL_FIELDS, GRID_FIELDS, WASHING_FIELDS, COLORS, FONTS
from grid import Grid
from create_gcode import generate_anchor_calibration, save_file
from canvas_drawer import CanvasDrawer

class DropletGui(tk.Tk):
    def __init__(self, config_dir):
        super(DropletGui, self).__init__()
        self.config_dir = config_dir
        self.global_input_frame = None
        self.canvas_frame = None
        self.canvas = None
        self.grid_tabs = None
        self.grid_tab_dict = {}  # Map 1-based grid number to grid object

        self.entry = []
        self.grid_count = 0

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
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=2)
        self.main_frame.columnconfigure(2, weight=1)

        # ========== LEFT FRAME: Grid Tabs ==========
        self.left_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.left_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self.left_frame.rowconfigure(0, weight=0)
        self.left_frame.rowconfigure(1, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        left_label = tk.Label(self.left_frame, text="Grid Configuration", font=FONTS['header'], 
                             fg=COLORS['accent'], bg=COLORS['bg_primary'])
        left_label.grid(row=0, column=0, sticky='ew', pady=(0, 10))

        # Create tabbed interface for grids
        self.grid_tabs = Notebook(self.left_frame, style="Custom.TNotebook")
        self.grid_tabs.grid(row=1, column=0, sticky='nsew')

        # ========== MIDDLE FRAME: Canvas and Inputs ==========
        self.middle_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.middle_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
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

        # ========== RIGHT FRAME: Global Configuration and Pictures ==========
        self.right_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.right_frame.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)
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

        add_grid_button = tk.Button(btn_frame, text="add grid", command=lambda: self._run_action(self.instance_grid, "Add Grid"),
                                bg=COLORS['success'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                activebackground='#00ff88', activeforeground=COLORS['bg_primary'])
        add_grid_button.pack(side='top', padx=2, pady=2, fill='x')

        remove_grid_button = tk.Button(btn_frame, text="remove grid", command=lambda: self._run_action(self.subtract_grid, "Remove Grid"),
                                   bg=COLORS['error'], fg='white', font=FONTS['normal'],
                                   relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                   activebackground='#ff6b6b', activeforeground='white')
        remove_grid_button.pack(side='top', padx=2, pady=2, fill='x')

        check_input_button = tk.Button(btn_frame, text="check input", command=lambda: self._run_action(self.check_inputs, "Check Input"),
                                   bg=COLORS['accent'], fg=COLORS['bg_primary'], font=FONTS['normal'],
                                   relief='flat', bd=0, padx=12, pady=6, cursor='hand2',
                                   activebackground='#00ffff', activeforeground=COLORS['bg_primary'])
        check_input_button.pack(side='top', padx=2, pady=2, fill='x')

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
        )
        
        self.grid_tab_dict[grid_number] = grid_obj
        self.grid_count = len(self.grid_tab_dict)

    def subtract_grid(self):
        """Remove the last grid tab."""
        if self.grid_count == 0:
            open_secondary_window("No grids to remove")
            return
        
        if self.grid_count == 1:
            open_secondary_window("At least one grid is required")
            return

        # Always remove the last grid to maintain consistent grid numbering
        last_grid_number = self.grid_count
        
        # Remove the last tab
        self.grid_tabs.forget(last_grid_number - 1)
        
        # Clean up grid references
        self.grid_tab_dict.pop(last_grid_number, None)
        self.grid_count = len(self.grid_tab_dict)

    def check_saves(self):
        # Save grid count
        write_state(self.grid_count, self.config_dir)

        # Convert global entries to dict
        global_dict = entries_to_dict(self.entry, GLOBAL_FIELDS)
        save_defaults(os.path.join(self.config_dir, "config_global.json"), global_dict)

        # Save each grid using dicts for grid, cleaning, washing
        for grid_number, grid_obj in self._iter_grids():
            cfg_path = os.path.join(self.config_dir, f"config_grid_{grid_number}.json")

            grid_dict = entries_to_dict(grid_obj.grid_entry, GRID_FIELDS)
            cleaning_dict = entries_to_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
            washing_dict = entries_to_dict(grid_obj.washing_entry, WASHING_FIELDS)
            grid_state_dict = {
                "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
                "washing_enabled": bool(grid_obj.washing_enabled.get()),
                "wash_after_loading": bool(grid_obj.wash_after_loading_enabled.get()),
                "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
                "final_rinse_add_cleaning_grid": bool(grid_obj.final_rinse_add_cleaning_grid.get()),
            }

            save_defaults(cfg_path, grid_dict, cleaning_dict, washing_dict, grid_state_dict)
            print(f"✅ Saved grid {grid_number} defaults to {cfg_path}")



    def adding_pictures(self):
        image = Image.open(os.path.join(self.config_dir, "BasePlate.png"))
        resized_image = image.resize((200*2, 170*2))
        photo = ImageTk.PhotoImage(resized_image)

        label_picture = Label(self.picture_frame, image=photo)
        label_picture.image = photo
        label_picture.grid(row=0, column=0, padx=5, pady=5)

        try:
            image = Image.open(os.path.join(self.config_dir, "spots.png"))
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

            # compute absolute rectangle inner origin (visual center, logical inset applied below)
            rect_x = x_abs + first_x_off
            rect_y = y_abs + first_y_off
            inner_vis_x = rect_x + (rect_w - inner_w) / 2.0
            inner_vis_y = rect_y + (rect_h - inner_h) / 2.0
            inner_origin_x = inner_vis_x + inset_lb
            inner_origin_y = inner_vis_y + inset_lb

            # grid absolute start/end positions
            start_abs_x = rect_x + grid_x_off
            start_abs_y = rect_y + grid_y_off
            end_abs_x = start_abs_x + grid_width
            end_abs_y = start_abs_y + grid_height

            # if grid starts before inner origin or ends beyond inner origin + inner size -> exceeded
            if start_abs_x < inner_origin_x or start_abs_y < inner_origin_y or end_abs_x > (inner_origin_x + inner_w) or end_abs_y > (inner_origin_y + inner_h):
                exceeded.append(grid_idx)

        # Check each existing grid independently
        for grid_number, grid_obj in self._iter_grids():
            check_grid_obj(grid_obj, grid_number)

        if exceeded:
            if len(exceeded) == 1:
                open_secondary_window(f"Grid {exceeded[0]} exceeds acceptance size of 19x39 mm")
            else:
                open_secondary_window(f"Grids {', '.join(map(str, exceeded))} exceed acceptance size of 19x39 mm")

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
