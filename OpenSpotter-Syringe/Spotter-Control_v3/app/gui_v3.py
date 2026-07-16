import os
import traceback
import json
import math
from pathlib import Path

from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter.ttk import Notebook, Style, Combobox


from .SpotterFunctions import entries_to_dict, save_defaults, write_state
from .input_configs import CLEANING_FIELDS, GLOBAL_FIELDS, GRID_FIELDS, SPIRAL_FIELDS, WASHING_FIELDS
from .ui_theme import COLORS, FONTS, button_options, configure_ttk_styles, entry_options
from .grid import Grid
from .spiral_grid import SpiralGrid
from .gcode_generation import save_file
from .canvas_drawer import CanvasDrawer
from .machine_parameters_window import MachineParametersWindow
from .paths import GCODE_DIR, VISUAL_OBJECT_CONFIG, WORKFLOW_CONFIG
from .runtime_logging import get_logger, log_options
from .visual_objects import VisualObjectStore


logger = get_logger("gui")


class DropletGui(tk.Tk):
    def __init__(self, config_dir):
        super(DropletGui, self).__init__()
        self.config_dir = config_dir
        self._last_logged_workspace_mode = None
        self.visual_object_store = VisualObjectStore(
            os.path.join(self.config_dir, VISUAL_OBJECT_CONFIG.name)
        )
        self.visual_objects = []
        self._visual_object_editor = None
        self._visual_object_load_error = None
        try:
            self.visual_objects = self.visual_object_store.load()["objects"]
        except Exception as exc:
            self._visual_object_load_error = str(exc)
            logger.exception(
                "visual_objects.load_failed | path=%s",
                self.visual_object_store.path,
            )
        else:
            log_options(
                logger,
                "visual_objects.loaded",
                path=self.visual_object_store.path,
                object_count=len(self.visual_objects),
                objects=self.visual_objects,
            )
        self.global_input_frame = None
        self.machine_parameters_window = None
        self.machine_control_panel = None
        self.machine_controller = None
        self.moonraker_connection_window = None
        self._closing = False
        self.canvas_frame = None
        self.canvas = None
        self.grid_tabs = None
        self.spiral_tabs = None
        self.grid_tab_dict = {}  # Map 1-based grid number to grid object
        self.spiral_tab_dict = {}  # Map 1-based spiral number to spiral object

        self.entry = []
        self.global_locked = tk.BooleanVar(master=self, value=True)
        self.grid_count = 0
        self.spiral_count = 0

        # Setting up basic UI structure
        self.title('OpenSpotter Control | Syringe Platform')
        self.configure(bg=COLORS['bg_primary'])
        self.option_add('*TCombobox*Listbox.background', COLORS['bg_tertiary'])
        self.option_add('*TCombobox*Listbox.foreground', COLORS['text_primary'])
        self.option_add('*TCombobox*Listbox.selectBackground', COLORS['selection'])
        self.option_add('*TCombobox*Listbox.selectForeground', COLORS['text_primary'])
        self._init_styles()
        if self._visual_object_load_error:
            self.after_idle(
                lambda: messagebox.showerror(
                    "Visual object configuration",
                    (
                        "The visual object file could not be loaded, so the canvas "
                        "will start without custom objects.\n\n"
                        f"{self._visual_object_load_error}"
                    ),
                    parent=self,
                )
            )
        # start window in windowed-fullscreen (maximized) on Windows
        try:
            self.state('zoomed')
        except Exception:
            logger.debug("window.maximize_not_supported", exc_info=True)
        log_options(
            logger,
            "gui.initialized",
            config_dir=self.config_dir,
            visual_object_count=len(self.visual_objects),
        )

    def _init_styles(self):
        style = Style(self)
        configure_ttk_styles(style)

        # Configure root window to expand
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.main_frame = tk.Frame(self, bg=COLORS['bg_primary'])
        self.main_frame.grid(sticky='nsew', padx=10, pady=10)
        self.main_frame.rowconfigure(0, weight=0)
        self.main_frame.rowconfigure(1, weight=1)
        self.main_frame.columnconfigure(0, weight=3, minsize=260)
        self.main_frame.columnconfigure(1, weight=5, minsize=480)
        self.main_frame.columnconfigure(2, weight=4, minsize=330)

        # ========== TOP BAR: identity, mode selector, and help ==========
        self.top_bar = tk.Frame(
            self.main_frame,
            bg=COLORS['bg_secondary'],
            relief='flat',
            bd=0,
            highlightbackground=COLORS['border'],
            highlightthickness=1,
        )
        self.top_bar.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 8))
        self.top_bar.columnconfigure(1, weight=1)

        brand = tk.Frame(self.top_bar, bg=COLORS['bg_secondary'])
        brand.grid(row=0, column=0, padx=(14, 20), pady=10, sticky='w')
        tk.Label(
            brand,
            text='OPENSPOTTER',
            font=FONTS['title'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
        ).pack(anchor='w')
        tk.Label(
            brand,
            text='SYRINGE CONTROL  /  TCP WORKSPACE',
            font=FONTS['caption'],
            fg=COLORS['accent'],
            bg=COLORS['bg_secondary'],
        ).pack(anchor='w', pady=(1, 0))

        mode_control = tk.Frame(self.top_bar, bg=COLORS['bg_secondary'])
        mode_control.grid(row=0, column=2, padx=8, pady=10, sticky='e')
        tk.Label(
            mode_control,
            text='PATTERN MODE',
            font=FONTS['caption'],
            fg=COLORS['text_muted'],
            bg=COLORS['bg_secondary'],
        ).pack(anchor='w', pady=(0, 3))

        self.workspace_mode_var = tk.StringVar(value='grid')
        self.workspace_mode_combo = Combobox(
            mode_control,
            values=['grid', 'spiral'],
            textvariable=self.workspace_mode_var,
            state='readonly',
            font=FONTS['small'],
            width=16,
        )
        self.workspace_mode_combo.pack(fill='x')
        self.workspace_mode_combo.bind('<<ComboboxSelected>>', lambda _e=None: self._switch_workspace_mode())

        self.machine_parameters_button = tk.Button(
            self.top_bar,
            text='MACHINE PARAMETERS',
            command=self.show_machine_parameters,
            **button_options('secondary'),
        )
        self.machine_parameters_button.grid(
            row=0,
            column=3,
            padx=(4, 4),
            pady=10,
            sticky='e',
        )

        help_button = tk.Button(
            self.top_bar,
            text='HELP',
            command=self.show_help,
            **button_options('ghost'),
        )
        help_button.grid(row=0, column=4, padx=(4, 12), pady=10, sticky='e')

        # ========== LEFT FRAME: Grid Tabs ==========
        self.left_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.left_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 4))
        self.left_frame.rowconfigure(0, weight=0)
        self.left_frame.rowconfigure(1, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        self.left_label = tk.Label(
            self.left_frame,
            text="GRID PARAMETERS",
            font=FONTS['label'],
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_primary'],
            anchor='w',
        )
        self.left_label.grid(row=0, column=0, sticky='ew', padx=2, pady=(2, 7))

        # Create tabbed interface for grids
        self.grid_tabs = Notebook(self.left_frame, style="Custom.TNotebook")
        self.grid_tabs.grid(row=1, column=0, sticky='nsew')

        self.spiral_tabs = Notebook(self.left_frame, style="Custom.TNotebook")
        self.spiral_tabs.grid(row=1, column=0, sticky='nsew')

        # ========== MIDDLE FRAME: Canvas and Inputs ==========
        self.middle_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.middle_frame.grid(row=1, column=1, sticky='nsew', padx=4)
        self.middle_frame.rowconfigure(0, weight=1)
        self.middle_frame.rowconfigure(1, weight=0)
        self.middle_frame.rowconfigure(2, weight=0)
        self.middle_frame.columnconfigure(0, weight=1)

        # ---- Canvas at top ----
        self.canvas_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        self.canvas_frame.grid(row=0, column=0, sticky='nsew')
        self.canvas_frame.rowconfigure(1, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)
        
        canvas_header = tk.Frame(self.canvas_frame, bg=COLORS['bg_secondary'])
        canvas_header.grid(row=0, column=0, sticky='ew', padx=12, pady=(9, 6))
        canvas_header.columnconfigure(0, weight=1)
        tk.Label(
            canvas_header,
            text="TCP COORDINATE PREVIEW",
            font=FONTS['label'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
            anchor='w',
        ).grid(row=0, column=0, sticky='w')
        tk.Label(
            canvas_header,
            text="LIVE GEOMETRY  /  mm",
            font=FONTS['caption'],
            fg=COLORS['text_muted'],
            bg=COLORS['bg_secondary'],
            anchor='e',
        ).grid(row=0, column=1, sticky='e')
        
        self.canvas = tk.Canvas(
            self.canvas_frame,
            width=560,
            height=410,
            bg=COLORS['canvas'],
            highlightbackground=COLORS['border'],
            highlightthickness=1,
            bd=0,
        )
        self.canvas.grid(row=1, column=0, sticky='nsew', padx=10, pady=(0, 7))

        # ---- Canvas controls frame ----
        canvas_controls_frame = tk.Frame(self.canvas_frame, bg=COLORS['bg_secondary'])
        canvas_controls_frame.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 8))

        # Interaction hint
        hint = tk.Label(canvas_controls_frame, text='TCP + X0/Y0  |  AMBER X REQUESTED HEAD  |  +X RIGHT / +Y DOWN  |  WHEEL ZOOM  |  DRAG PAN', font=FONTS['caption'],
                        fg=COLORS['text_muted'], bg=COLORS['bg_secondary'])
        hint.pack(side='left', padx=(0, 5), pady=2)

        visual_objects_button = tk.Button(
            canvas_controls_frame,
            text="VISUAL OBJECTS",
            command=lambda: self._run_action(
                self.open_visual_object_editor,
                "Open Visual Objects",
            ),
            **button_options('secondary'),
        )
        visual_objects_button.pack(side='right', padx=(5, 0), pady=2)

        fit_canvas_button = tk.Button(
            canvas_controls_frame,
            text="FIT VIEW",
            command=self.fit_canvas_to_content,
            **button_options('ghost'),
        )
        fit_canvas_button.pack(side='right', padx=(5, 0), pady=2)

        # ---- Build plate buttons frame (row 1) - moved below global config in right frame ----
        self.info_button_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        self.info_button_frame.grid(row=1, column=0, sticky='nsew', pady=(5, 0), padx=0)
        self.info_button_frame.columnconfigure(0, weight=1)

        info_label = tk.Label(self.info_button_frame, text="EXPERIMENT CONTROLS", font=FONTS['label'],
                             fg=COLORS['text_primary'], bg=COLORS['bg_secondary'])
        info_label.pack(anchor='w', padx=12, pady=(10, 6))

        # Buttons frame
        self.button_frame = tk.Frame(self.info_button_frame, bg=COLORS['bg_secondary'])
        self.button_frame.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.create_buttons()
        self._switch_workspace_mode()

        # ---- Canvas input parameters (row 2) ----
        self.canvas_params_frame = tk.Frame(self.middle_frame, bg=COLORS['bg_secondary'], relief='flat', bd=0, highlightbackground=COLORS['border'], highlightthickness=1)
        self.canvas_params_frame.grid(row=2, column=0, sticky='nsew', pady=(5, 0), padx=0)
        self.canvas_params_frame.columnconfigure(0, weight=1)

        params_label = tk.Label(self.canvas_params_frame, text="VISUAL CALIBRATION", font=FONTS['label'],
                               fg=COLORS['text_primary'], bg=COLORS['bg_secondary'])
        params_label.pack(anchor='w', padx=12, pady=(10, 6))

        # Dispense -> diameter mapping entries
        map_frame = tk.Frame(self.canvas_params_frame, bg=COLORS['bg_secondary'])
        map_frame.pack(fill='x', padx=10, pady=(0, 8))

        lbl = tk.Label(map_frame, text='VOLUME-TO-DIAMETER MODEL',
                      font=FONTS['caption'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary'])
        lbl.pack(anchor='w', pady=(0, 6))

        rowf = tk.Frame(map_frame, bg=COLORS['bg_secondary'])
        rowf.pack(fill='x', pady=3)
        tk.Label(rowf, text='v1:', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_v1_entry = tk.Entry(rowf, width=8, **entry_options(mono=True))
        self.disp_v1_entry.insert(0, '0.04')
        self.disp_v1_entry.pack(side='left', padx=(2, 8))
        tk.Label(rowf, text='d1 (mm):', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_d1_entry = tk.Entry(rowf, width=8, **entry_options(mono=True))
        self.disp_d1_entry.insert(0, '0.6')
        self.disp_d1_entry.pack(side='left', padx=(2, 8))

        rowf2 = tk.Frame(map_frame, bg=COLORS['bg_secondary'])
        rowf2.pack(fill='x', pady=3)
        tk.Label(rowf2, text='v2:', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_v2_entry = tk.Entry(rowf2, width=8, **entry_options(mono=True))
        self.disp_v2_entry.insert(0, '0.08')
        self.disp_v2_entry.pack(side='left', padx=(2, 8))
        tk.Label(rowf2, text='d2 (mm):', font=FONTS['small'], fg=COLORS['text_secondary'], bg=COLORS['bg_secondary']).pack(side='left')
        self.disp_d2_entry = tk.Entry(rowf2, width=8, **entry_options(mono=True))
        self.disp_d2_entry.insert(0, '1.2')
        self.disp_d2_entry.pack(side='left', padx=(2, 8))

        self._load_canvas_parameter_defaults()

        # ========== RIGHT FRAME: Machine control host ==========
        self.right_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.right_frame.grid(row=1, column=2, sticky='nsew', padx=(4, 0))
        self.right_frame.rowconfigure(0, weight=1)
        self.right_frame.columnconfigure(0, weight=1)

        self.machine_panel_host = tk.Frame(
            self.right_frame,
            bg=COLORS['bg_secondary'],
            relief='flat',
            bd=0,
            highlightbackground=COLORS['border'],
            highlightthickness=1,
        )
        self.machine_panel_host.grid(row=0, column=0, sticky='nsew')
        self.machine_panel_host.rowconfigure(0, weight=1)
        self.machine_panel_host.columnconfigure(0, weight=1)

        self.machine_parameters_window = MachineParametersWindow(
            self,
            locked_var=self.global_locked,
            on_toggle_lock=self._toggle_global_lock,
            on_save=lambda: self._run_action(
                self.check_saves,
                "Save Defaults",
            ),
        )
        # Compatibility for generation/profile code that expects this attribute.
        self.global_input_frame = self.machine_parameters_window.input_frame
        self.lock_button = self.machine_parameters_window.lock_button

        # start canvas drawer
        try:
            self.canvas_drawer = CanvasDrawer(self)
            self.canvas_drawer.start()
        except Exception:
            logger.exception("canvas.initialization_failed")

    def create_buttons(self):
        btn_frame = tk.Frame(self.button_frame, bg=COLORS['bg_secondary'])
        btn_frame.pack(fill='both', expand=True)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.add_object_button = tk.Button(btn_frame, text="ADD GRID", command=lambda: self._run_action(self._add_active_object, "Add Object"),
                                **button_options('secondary'))
        self.add_object_button.grid(row=0, column=0, padx=2, pady=2, sticky='ew')

        self.remove_object_button = tk.Button(btn_frame, text="REMOVE GRID", command=lambda: self._run_action(self._remove_active_object, "Remove Object"),
                                   **button_options('ghost'))
        self.remove_object_button.grid(row=0, column=1, padx=2, pady=2, sticky='ew')

        load_config_button = tk.Button(btn_frame, text="LOAD PROFILE", command=lambda: self._run_action(self.load_generation_config, "Load Config"),
                                   **button_options('secondary'))
        load_config_button.grid(row=1, column=0, padx=2, pady=2, sticky='ew')

        workflow_button = tk.Button(
            btn_frame,
            text="EDIT G-CODE WORKFLOW",
            command=lambda: self._run_action(
                self.open_gcode_workflow_editor,
                "Open G-code Workflow",
            ),
            **button_options('secondary'),
        )
        workflow_button.grid(row=1, column=1, padx=2, pady=2, sticky='ew')

        create_gcode_button = tk.Button(btn_frame, text="GENERATE G-CODE", command=lambda: self._run_action(self.save_file, "Create G-code"),
                                    **button_options('primary'))
        create_gcode_button.grid(row=2, column=0, padx=2, pady=2, sticky='ew')

        check_save_button = tk.Button(btn_frame, text="SAVE DEFAULTS", command=lambda: self._run_action(self.check_saves, "Save Defaults"),
                                  **button_options('secondary'))
        check_save_button.grid(row=2, column=1, padx=2, pady=2, sticky='ew')

    def open_gcode_workflow_editor(self):
        """Open the optional workflow editor without coupling it to GUI startup."""
        from .gcode_editor import open_workflow_editor

        workflow_path = os.path.join(self.config_dir, WORKFLOW_CONFIG.name)
        log_options(logger, "workflow.editor_opened", workflow_path=workflow_path)
        return open_workflow_editor(
            self,
            workflow_path,
            on_saved=self._workflow_saved,
            variable_provider=self._workflow_variable_provider,
        )

    def open_visual_object_editor(self):
        """Open the machine-layout editor and its optional program links."""
        from .visual_object_editor import open_visual_object_editor

        log_options(
            logger,
            "visual_objects.editor_opened",
            object_count=len(self.visual_objects),
        )
        return open_visual_object_editor(
            self,
            self.visual_objects,
            self._save_visual_objects,
            variable_provider=self._visual_binding_variable_provider,
            variable_setter=self._set_visual_binding_variable,
        )

    def _save_visual_objects(self, objects):
        """Persist a validated visual layout and refit the canvas immediately."""
        saved = self.visual_object_store.save(objects)
        self.visual_objects = saved["objects"]
        log_options(
            logger,
            "visual_objects.saved",
            path=getattr(self.visual_object_store, "path", None),
            object_count=len(self.visual_objects),
            objects=self.visual_objects,
        )
        canvas_drawer = getattr(self, 'canvas_drawer', None)
        if canvas_drawer is not None:
            try:
                canvas_drawer.reset_view()
            except Exception:
                logger.exception("canvas.reset_after_visual_save_failed")
                traceback.print_exc()

    def fit_canvas_to_content(self):
        """Reset pan and zoom so the TCP sensor and current content are visible."""
        canvas_drawer = getattr(self, 'canvas_drawer', None)
        if canvas_drawer is not None:
            canvas_drawer.reset_view()

    def _workflow_saved(self, _workflow=None):
        """Refresh previews whose geometry depends on workflow variables."""
        log_options(
            logger,
            "workflow.saved",
            workflow_path=os.path.join(self.config_dir, WORKFLOW_CONFIG.name),
            workflow=_workflow,
        )
        canvas_drawer = getattr(self, 'canvas_drawer', None)
        if canvas_drawer is None:
            return
        canvas_drawer.invalidate()

    def _workflow_variable_provider(self):
        """Return current GUI field values for workflow preview and insertion."""
        variables = {}

        def register_value(name, value, value_type, unit, source, description):
            variables[name] = {
                "value": value,
                "type": value_type,
                "unit": unit,
                "scope": name.split('.', 1)[0],
                "source": source,
                "description": description,
            }

        def selected_object(notebook, object_map):
            if not object_map:
                return None, None
            try:
                selected_number = notebook.index(notebook.select()) + 1
            except (tk.TclError, ValueError):
                selected_number = min(object_map)
            return selected_number, object_map.get(selected_number)

        def value_and_type(entry_widget, field):
            raw_value = field.default if entry_widget is None else entry_widget.get()
            unit = str(field.unit).strip().lower()
            try:
                if unit == 'int':
                    return int(float(raw_value)), 'int'
                if unit == 'bool':
                    return self._parse_bool(raw_value), 'bool'
                if unit == 'str':
                    return str(raw_value), 'str'
                return float(raw_value), 'float'
            except (TypeError, ValueError):
                return str(raw_value), 'str'

        def register_fields(namespace, fields, entries, source):
            entry_list = entries or []
            for index, field in enumerate(fields):
                entry_widget = entry_list[index] if index < len(entry_list) else None
                value, value_type = value_and_type(entry_widget, field)
                variables[f"{namespace}.{field.key}"] = {
                    "value": value,
                    "type": value_type,
                    "unit": field.unit,
                    "scope": namespace,
                    "source": source,
                    "description": field.label,
                }

        register_fields('global', GLOBAL_FIELDS, self.entry, 'Global runtime inputs')

        global_values = {
            field.key: variables[f"global.{field.key}"]["value"]
            for field in GLOBAL_FIELDS
        }
        try:
            acceptance_left = (
                float(global_values['x_cord_of_y_line'])
                + (
                    float(global_values['base_square_x'])
                    - float(global_values['acceptance_square_x'])
                ) / 2.0
            )
            acceptance_bottom = (
                float(global_values['y_cord_of_x_line'])
                + (
                    float(global_values['base_square_y'])
                    - float(global_values['acceptance_square_y'])
                ) / 2.0
            )
            acceptance_values = {
                'x_left': acceptance_left,
                'x_right': acceptance_left + float(global_values['acceptance_square_x']),
                'y_bottom': acceptance_bottom,
                'y_top': acceptance_bottom + float(global_values['acceptance_square_y']),
            }
            for key, value in acceptance_values.items():
                register_value(
                    f'acceptance.{key}',
                    value,
                    'float',
                    'mm',
                    'Computed runtime value',
                    f'Current acceptance-square {key.replace("_", " ")}.',
                )
        except (KeyError, TypeError, ValueError):
            pass

        grid_number, grid_obj = selected_object(self.grid_tabs, self.grid_tab_dict)
        grid_source = f"Grid {grid_number} runtime inputs" if grid_obj else 'Grid field default'
        register_fields('grid', GRID_FIELDS, getattr(grid_obj, 'grid_entry', None), grid_source)
        register_value(
            'grid.name',
            grid_obj.get_grid_name() if grid_obj and hasattr(grid_obj, 'get_grid_name') else 'Grid',
            'str',
            '',
            grid_source,
            'Current grid display name.',
        )
        register_value(
            'grid.color',
            grid_obj.get_grid_color() if grid_obj and hasattr(grid_obj, 'get_grid_color') else 'green',
            'str',
            '',
            grid_source,
            'Current grid display color.',
        )
        register_fields(
            'cleaning',
            CLEANING_FIELDS,
            getattr(grid_obj, 'cleaning_entry', None),
            grid_source,
        )
        register_fields(
            'washing',
            WASHING_FIELDS,
            getattr(grid_obj, 'washing_entry', None),
            grid_source,
        )

        spiral_number, spiral_obj = selected_object(self.spiral_tabs, self.spiral_tab_dict)
        spiral_source = (
            f"Spiral {spiral_number} runtime inputs" if spiral_obj else 'Spiral field default'
        )
        register_fields(
            'spiral',
            SPIRAL_FIELDS,
            getattr(spiral_obj, 'spiral_entry', None),
            spiral_source,
        )
        register_value(
            'spiral.name',
            spiral_obj.get_grid_name() if spiral_obj and hasattr(spiral_obj, 'get_grid_name') else 'Spiral',
            'str',
            '',
            spiral_source,
            'Current spiral display name.',
        )
        register_value(
            'spiral.color',
            spiral_obj.get_grid_color() if spiral_obj and hasattr(spiral_obj, 'get_grid_color') else 'orange',
            'str',
            '',
            spiral_source,
            'Current spiral display color.',
        )

        loading_namespace = 'spiral' if self._current_workspace_mode() == 'spiral' else 'grid'
        active_number = spiral_number if loading_namespace == 'spiral' else grid_number
        register_value(
            'runtime.job.kind',
            loading_namespace,
            'str',
            '',
            'Runtime workspace',
            'Pattern type used for workflow conditions.',
        )
        register_value(
            'runtime.job.pattern_index',
            int(active_number or 0),
            'int',
            '',
            'Runtime workspace',
            'One-based active pattern index.',
        )
        try:
            container_id = int(variables[f'{loading_namespace}.loading_from']['value'])
            for key, unit in (('id', ''), ('x', 'mm'), ('y', 'mm'), ('z', 'mm')):
                if key == 'id':
                    value = container_id
                    value_type = 'int'
                else:
                    value = global_values[f'container{container_id}_{key}']
                    value_type = 'float'
                register_value(
                    f'container.{key}',
                    value,
                    value_type,
                    unit,
                    'Selected loading container',
                    f'Current loading container {key.upper() if key != "id" else "number"}.',
                )
        except (KeyError, TypeError, ValueError):
            pass
        return variables

    @staticmethod
    def _visual_binding_field_type(field):
        """Return the numeric type accepted by a bindable program field."""
        unit = str(field.unit).strip().lower()
        if unit in ("bool", "str") or isinstance(field.default, (bool, str)):
            return None
        if unit == "int" or (
            isinstance(field.default, int) and not isinstance(field.default, bool)
        ):
            return "int"
        return "float"

    def _visual_binding_targets(self):
        """Map stable visual-binding names to their live input widgets."""
        targets = {}

        def register(namespace, fields, entries, source):
            for field, entry_widget in zip(fields, entries or []):
                value_type = self._visual_binding_field_type(field)
                if value_type is None:
                    continue
                targets[f"{namespace}.{field.key}"] = {
                    "widget": entry_widget,
                    "field": field,
                    "type": value_type,
                    "unit": field.unit,
                    "source": source,
                    "description": field.label,
                }

        register(
            "global",
            GLOBAL_FIELDS,
            self.entry,
            "Global machine parameters",
        )
        for grid_number, grid_obj in self._iter_grids():
            register(
                f"grid.{grid_number}",
                GRID_FIELDS,
                getattr(grid_obj, "grid_entry", None),
                f"Grid {grid_number}",
            )
            register(
                f"cleaning.{grid_number}",
                CLEANING_FIELDS,
                getattr(grid_obj, "cleaning_entry", None),
                f"Grid {grid_number} cleaning",
            )
            register(
                f"washing.{grid_number}",
                WASHING_FIELDS,
                getattr(grid_obj, "washing_entry", None),
                f"Grid {grid_number} washing",
            )
        for spiral_number, spiral_obj in self._iter_spirals():
            register(
                f"spiral.{spiral_number}",
                SPIRAL_FIELDS,
                getattr(spiral_obj, "spiral_entry", None),
                f"Spiral {spiral_number}",
            )
        return targets

    def _visual_binding_variable_provider(self):
        """Return live numeric program inputs available to visual geometry."""
        variables = {}
        for name, target in self._visual_binding_targets().items():
            widget = target["widget"]
            try:
                raw_value = widget.get()
            except Exception:
                continue

            valid = True
            try:
                numeric_value = float(raw_value)
                if not math.isfinite(numeric_value):
                    raise ValueError("value must be finite")
                if target["type"] == "int":
                    if not numeric_value.is_integer():
                        raise ValueError("value must be a whole number")
                    value = int(numeric_value)
                else:
                    value = numeric_value
            except (TypeError, ValueError):
                value = raw_value
                valid = False

            try:
                state = str(widget.cget("state"))
            except Exception:
                state = "normal"
            variables[name] = {
                "value": value,
                "type": target["type"],
                "unit": target["unit"],
                "scope": name.split(".", 1)[0],
                "source": target["source"],
                "description": target["description"],
                "valid": valid,
                "writable": state not in ("disabled", "readonly"),
            }
        return variables

    def _set_visual_binding_variable(self, name, value):
        """Write a linked visual value back to an unlocked program input."""
        target = self._visual_binding_targets().get(str(name))
        if target is None:
            raise ValueError(f"Linked program variable '{name}' is not available")

        widget = target["widget"]
        try:
            state = str(widget.cget("state"))
        except Exception:
            state = "normal"
        if state in ("disabled", "readonly"):
            if str(name).startswith("global."):
                raise ValueError(
                    f"'{name}' is locked. Unlock GLOBAL MACHINE PARAMETERS "
                    "before changing it from Visual Objects."
                )
            raise ValueError(f"Linked program variable '{name}' is read-only")

        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'{name}' must be a number") from exc
        if not math.isfinite(numeric_value):
            raise ValueError(f"'{name}' must be a finite number")
        if target["type"] == "int":
            if not numeric_value.is_integer():
                raise ValueError(f"'{name}' must be a whole number")
            canonical_value = int(numeric_value)
        else:
            canonical_value = numeric_value

        self._set_entry_value(widget, canonical_value, target["field"])
        log_options(
            logger,
            "visual_binding.program_value_changed",
            variable=name,
            value=canonical_value,
            source=target.get("source"),
        )
        canvas_drawer = getattr(self, "canvas_drawer", None)
        if canvas_drawer is not None:
            try:
                canvas_drawer.request_redraw()
            except Exception:
                logger.exception("canvas.redraw_after_binding_change_failed")
                traceback.print_exc()
        return canonical_value

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
            self.left_label.config(text='SPIRAL PARAMETERS')
            self.add_object_button.config(text='ADD SPIRAL')
            self.remove_object_button.config(text='REMOVE SPIRAL')
        else:
            try:
                self.spiral_tabs.grid_remove()
            except Exception:
                pass
            try:
                self.grid_tabs.grid()
            except Exception:
                pass
            self.left_label.config(text='GRID PARAMETERS')
            self.add_object_button.config(text='ADD GRID')
            self.remove_object_button.config(text='REMOVE GRID')
        if mode != self._last_logged_workspace_mode:
            log_options(
                logger,
                "workspace.mode_changed",
                mode=mode,
                grid_count=self.grid_count,
                spiral_count=self.spiral_count,
            )
            self._last_logged_workspace_mode = mode

    def show_help(self):
        message = (
            'Grid mode manages row/column spotting tabs.\n\n'
            'Spiral mode manages spiral pattern tabs with drop or continuous extrusion.\n\n'
            'Use the dropdown at the top to switch between modes, then add or remove tabs for that mode.\n\n'
            'Machine Control connects to Moonraker, generates an immutable snapshot of the current mode, '
            'uploads the exact G-code artifact, and starts it through virtual SD. Pause/Resume and Stop '
            'control that virtual-SD job. Emergency Stop and manual M112 use Moonraker’s independent '
            'HTTP emergency-stop endpoint. Guarded controls require the current OPENSPOTTER_CONTRACT_V3 '
            'firmware macros and stay disabled when they are missing or stale.\n\n'
            'XYZ jog requires Klippy ready/idle, inactive virtual SD, homed XYZ, needle offsets and '
            'bed mesh off, and a feed of at least 30 mm/min. Safe Home uses the reviewed sensorless '
            'settle, release, and physical-clearance sequence. Live Z is '
            'available only during an active job with needle offsets enabled. The G-code cursor is '
            'Moonraker’s virtual-SD read/queued position; it does not prove that physical motion is complete.\n\n'
            'Manual / Console parses a small allowlist: diagnostic queries plus bounded G90/G91 and '
            'G0/G1 XYZ/F tests with explicit mode/feed and a 60-second cap. Unknown or unsafe commands '
            'are blocked. A partial error, timeout, disconnect, or emergency stop interlocks normal '
            'controls until the printer is inspected and monitoring reconnects.\n\n'
            'The canvas uses the CAPTRON TCP beam crossing as X0/Y0, with +X right and +Y down. '
            'When Moonraker supplies fresh homed XY telemetry, an amber X marks Klipper’s live '
            'requested toolhead trajectory in raw carriage coordinates. It is not encoder feedback '
            'or the logical needle-tip target when TCP offsets are active. '
            'Use Visual Objects to edit rectangles, circles, and imported images. '
            'X, Y, width, and height may be linked to program inputs; changing a '
            'linked value writes back only when that input is unlocked.'
        )
        open_secondary_window(message, title='Help')

    def show_machine_parameters(self):
        """Reveal the persistent global machine-parameter editor."""
        return self.machine_parameters_window.show()

    def initialize_machine_control(self):
        """Create and start the Moonraker panel after startup fields are loaded."""
        if self.machine_controller is not None:
            return self.machine_controller

        from .machine.connection_settings import load_connection_settings
        from .machine_control_panel import MachineControlPanel
        from .machine_controller import MachineControlController
        from .moonraker_connection_window import MoonrakerConnectionWindow

        settings_path = Path(self.config_dir) / "config_moonraker.json"

        def load_runtime_config():
            return load_connection_settings(settings_path).to_moonraker_config()

        canvas_drawer = getattr(self, "canvas_drawer", None)
        position_sink = getattr(
            canvas_drawer,
            "set_toolhead_position",
            None,
        )
        panel = MachineControlPanel(self.machine_panel_host)
        controller = MachineControlController(
            self,
            panel,
            load_runtime_config,
            position_sink=position_sink if callable(position_sink) else None,
        )
        settings_window = MoonrakerConnectionWindow(
            self,
            path=settings_path,
            on_saved=controller.apply_config,
        )
        controller.set_settings_window(settings_window)

        self.machine_control_panel = panel
        self.machine_controller = controller
        self.moonraker_connection_window = settings_window
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        controller.start()
        return controller

    def close_application(self):
        """Stop local monitoring cleanly; an active Klipper job is not cancelled."""
        if self._closing:
            return
        controller = self.machine_controller
        if controller is not None:
            view = controller.current_view()
            if controller.has_unresolved_operation:
                confirmed = messagebox.askyesno(
                    "Close during machine operation",
                    (
                        "A machine operation is still in flight or its outcome "
                        "is unresolved.\n\nClosing stops local monitoring only "
                        "and does not prove that Klipper did not accept motion. "
                        "Keep this window open and inspect live state whenever "
                        "possible.\n\nClose anyway?"
                    ),
                    parent=self,
                )
                if not confirmed:
                    return
            elif (
                view.print_state in {"printing", "paused"}
                or view.virtual_sd_active
            ):
                confirmed = messagebox.askyesno(
                    "Close OpenSpotter Control",
                    (
                        "A virtual-SD job is still active.\n\n"
                        "Closing this application stops local monitoring only; "
                        "Klipper will continue the job. Close anyway?"
                    ),
                    parent=self,
                )
                if not confirmed:
                    return
        self._closing = True
        try:
            if controller is not None:
                controller.shutdown()
        finally:
            self.destroy()

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
        log_options(logger, "ui.action_started", action=action_name)
        try:
            result = action()
            log_options(
                logger,
                "ui.action_finished",
                action=action_name,
                result=result,
            )
            return result
        except ValueError as exc:
            logger.warning(
                "ui.action_input_error | action=%s | error=%s",
                action_name,
                exc,
                exc_info=True,
            )
            open_secondary_window(f"{action_name} failed:\n{exc}", title="Input Error")
        except Exception as exc:
            logger.exception("ui.action_failed | action=%s", action_name)
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
            log_options(
                logger,
                "grid.add_blocked",
                active_count=self.grid_count,
                maximum=max_grid_count,
            )
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
        log_options(
            logger,
            "grid.added",
            grid_number=grid_number,
            config_path=config_file,
            active_count=self.grid_count,
            maximum=max_grid_count,
        )

    def instance_spiral(self):
        """Create a new spiral object in a new tab."""
        max_spiral_count = self._get_max_grid_count()
        if self.spiral_count >= max_spiral_count:
            log_options(
                logger,
                "spiral.add_blocked",
                active_count=self.spiral_count,
                maximum=max_spiral_count,
            )
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
        log_options(
            logger,
            "spiral.added",
            spiral_number=spiral_number,
            config_path=config_file,
            active_count=self.spiral_count,
            maximum=max_spiral_count,
        )

    def subtract_spiral(self):
        """Remove the last spiral tab."""
        if self.spiral_count == 0:
            logger.info("spiral.remove_blocked | reason=no_spirals")
            open_secondary_window("No spirals to remove")
            return

        last_spiral_number = self.spiral_count
        self.spiral_tabs.forget(last_spiral_number - 1)
        self.spiral_tab_dict.pop(last_spiral_number, None)
        self.spiral_count = len(self.spiral_tab_dict)
        log_options(
            logger,
            "spiral.removed",
            spiral_number=last_spiral_number,
            active_count=self.spiral_count,
        )
        try:
            if hasattr(self, 'canvas_drawer') and self.canvas_drawer:
                self.canvas_drawer.refresh()
        except Exception:
            pass

    def subtract_grid(self):
        """Remove the last grid tab."""
        if self.grid_count == 0:
            logger.info("grid.remove_blocked | reason=no_grids")
            open_secondary_window("No grids to remove")
            return

        # Always remove the last grid to maintain consistent grid numbering
        last_grid_number = self.grid_count
        
        # Remove the last tab
        self.grid_tabs.forget(last_grid_number - 1)
        
        # Clean up grid references
        self.grid_tab_dict.pop(last_grid_number, None)
        self.grid_count = len(self.grid_tab_dict)
        log_options(
            logger,
            "grid.removed",
            grid_number=last_grid_number,
            active_count=self.grid_count,
        )
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
        log_options(
            logger,
            "defaults.save_started",
            grid_count=self.grid_count,
            spiral_count=self.spiral_count,
        )
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

        for spiral_number, spiral_obj in self._iter_spirals():
            cfg_path = os.path.join(self.config_dir, f"config_spiral_{spiral_number}.json")
            spiral_dict = spiral_obj.save_defaults_dict()
            spiral_state_dict = {
                "spiral_name": spiral_obj.get_grid_name(),
                "spiral_color": spiral_obj.get_grid_color(),
            }
            save_defaults(cfg_path, spiral_dict, spiral_state_dict)
        logger.info("defaults.save_completed")

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
            with open(cfg_path, "r", encoding="utf-8") as f:
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

    def save_file(self):
        return save_file(self)

    def _toggle_global_lock(self):
        """Toggle global configuration lock with warning popup."""
        if self.global_locked.get():
            # Currently locked, trying to unlock
            result = messagebox.showwarning(
                "Unlock machine parameters",
                "Editing machine geometry can create unsafe travel. Verify all values before generating or running G-code.",
                type=messagebox.OKCANCEL,
                parent=self.machine_parameters_window,
            )
            if result == messagebox.OK:
                # User confirmed, unlock the fields
                self.global_locked.set(False)
                self._update_global_fields_state()
                self.lock_button.config(text="EDITING")
                log_options(logger, "global_parameters.lock_changed", locked=False)
            else:
                logger.info("global_parameters.unlock_cancelled")
        else:
            # Currently unlocked, lock it
            self.global_locked.set(True)
            self._update_global_fields_state()
            self.lock_button.config(text="LOCKED")
            log_options(logger, "global_parameters.lock_changed", locked=True)

    def _update_global_fields_state(self):
        """Update the state of all global input fields based on lock state."""
        is_locked = self.global_locked.get()
        state = 'disabled' if is_locked else 'normal'
        
        # Disable/enable all entry fields in global_input_frame
        for widget in self.entry:
            if isinstance(widget, tk.Entry):
                widget.config(state=state)

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False

    def _set_entry_value(self, entry_widget, value, field=None):
        if isinstance(entry_widget, Combobox):
            if field is not None and str(field.unit).lower() == 'bool':
                entry_widget.set('True' if self._parse_bool(value) else 'False')
            else:
                entry_widget.set(str(value))
            return
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
                self._set_entry_value(entry_widget, values_dict[field.key], field)

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

    def _parse_generation_json_file(self, filepath):
        """Load and structurally validate a canonical settings profile."""
        with open(filepath, "r", encoding="utf-8") as profile_file:
            profile = json.load(profile_file)

        if not isinstance(profile, dict):
            raise ValueError("Settings profile must contain a JSON object")

        expected_sections = {
            "global_settings": (dict, "JSON object"),
            "grid_settings": (list, "JSON array"),
            "spiral_settings": (list, "JSON array"),
        }
        for section_name, (expected_type, type_label) in expected_sections.items():
            if section_name not in profile:
                raise ValueError(f"Settings profile is missing '{section_name}'")
            section = profile[section_name]
            if not isinstance(section, expected_type):
                raise ValueError(f"'{section_name}' must be a {type_label}")

        for index, grid_state in enumerate(profile.get("grid_settings", []), start=1):
            if not isinstance(grid_state, dict):
                raise ValueError(f"Grid {index} settings must be a JSON object")
            for subsection in ("grid", "cleaning", "washing"):
                values = grid_state.get(subsection, {})
                if not isinstance(values, dict):
                    raise ValueError(
                        f"Grid {index} '{subsection}' settings must be a JSON object"
                    )
            for flag in (
                "cleaning_enabled",
                "washing_enabled",
                "wash_after_loading",
                "final_rinse_enabled",
                "final_rinse_add_cleaning_grid",
            ):
                if flag in grid_state and not isinstance(grid_state[flag], bool):
                    raise ValueError(f"Grid {index} '{flag}' setting must be true or false")

        for index, spiral_state in enumerate(profile.get("spiral_settings", []), start=1):
            if not isinstance(spiral_state, dict):
                raise ValueError(f"Spiral {index} settings must be a JSON object")
            if not isinstance(spiral_state.get("spiral", {}), dict):
                raise ValueError(f"Spiral {index} 'spiral' settings must be a JSON object")

        if "workflow" in profile and not isinstance(profile["workflow"], dict):
            raise ValueError("'workflow' must be a JSON object")

        return profile

    def load_generation_config(self):
        filepath = filedialog.askopenfilename(
            title="Load generation settings",
            initialdir=str(GCODE_DIR),
            filetypes=[
                ("Settings profile", "*_settings.json"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not filepath:
            logger.info("profile.load_cancelled | reason=no_input_path")
            return

        log_options(logger, "profile.load_started", path=filepath)
        parsed = self._parse_generation_json_file(filepath)
        log_options(logger, "profile.validated", path=filepath, profile=parsed)

        workflow_store = None
        validated_workflow = None
        if "workflow" in parsed:
            from .gcode_workflow import WorkflowStore

            workflow_path = os.path.join(self.config_dir, WORKFLOW_CONFIG.name)
            workflow_store = WorkflowStore(workflow_path)
            validated_workflow = workflow_store.validate(parsed["workflow"])
            replace_workflow = messagebox.askyesno(
                "Replace executable G-code workflow",
                (
                    "This profile contains an embedded G-code workflow. Loading "
                    "it will replace the active executable machine-command "
                    "templates, not only the visible recipe values.\n\n"
                    "Replace the active workflow with the profile workflow?"
                ),
                parent=self,
            )
            if not replace_workflow:
                logger.info(
                    "profile.load_cancelled | reason=embedded_workflow_rejected"
                )
                return

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
        if workflow_store is not None:
            workflow_store.save(validated_workflow)
            self._workflow_saved(validated_workflow)
        else:
            try:
                if hasattr(self, 'canvas_drawer') and self.canvas_drawer:
                    self.canvas_drawer.refresh()
            except Exception:
                logger.exception("canvas.refresh_after_profile_load_failed")
        log_options(
            logger,
            "profile.load_completed",
            path=filepath,
            grid_count=self.grid_count,
            spiral_count=self.spiral_count,
            workflow_replaced=workflow_store is not None,
            global_parameters_locked=bool(self.global_locked.get()),
        )

def open_secondary_window(text, title="Notice", parent=None):
    parent = parent or tk._default_root
    secondary_window = tk.Toplevel(parent)
    secondary_window.title(title)
    secondary_window.configure(bg=COLORS['bg_primary'])
    secondary_window.minsize(420, 180)
    secondary_window.columnconfigure(0, weight=1)
    secondary_window.rowconfigure(0, weight=1)
    if parent is not None:
        secondary_window.transient(parent)

    panel = tk.Frame(
        secondary_window,
        bg=COLORS['bg_secondary'],
        highlightbackground=COLORS['border'],
        highlightthickness=1,
        bd=0,
    )
    panel.grid(row=0, column=0, sticky='nsew', padx=12, pady=12)
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(0, weight=1)
    tk.Label(
        panel,
        text=text,
        justify='left',
        anchor='nw',
        wraplength=520,
        bg=COLORS['bg_secondary'],
        fg=COLORS['text_primary'],
        font=FONTS['normal'],
        padx=16,
        pady=16,
    ).grid(row=0, column=0, sticky='nsew')
    button_close = tk.Button(
        panel,
        text="CLOSE",
        command=secondary_window.destroy,
        **button_options('primary'),
    )
    button_close.grid(row=1, column=0, padx=16, pady=(0, 16), sticky='e')
    secondary_window.bind('<Escape>', lambda _event: secondary_window.destroy())
    secondary_window.after_idle(button_close.focus_set)
    return secondary_window
