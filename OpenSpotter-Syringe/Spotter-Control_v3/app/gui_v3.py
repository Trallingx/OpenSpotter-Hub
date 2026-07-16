"""Registry-driven Tk desktop shell for OpenSpotter Control.

The shell creates one generic workspace per application plugin and delegates
editor construction, profiles, generation, previews, and direct-run capture
through plugin contracts. Built-in-specific methods remain compatibility
wrappers only.
"""

import os
import traceback
import json
import math
from dataclasses import dataclass
from pathlib import Path

from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter.ttk import Notebook, Style, Combobox


from .core.application_patterns import ApplicationPatternPlugin
from .core.configuration import entries_to_dict, save_defaults, write_state
from .core.geometry import acceptance_square
from .input_configs import GLOBAL_FIELDS
from .ui_theme import COLORS, FONTS, button_options, configure_ttk_styles, entry_options
from .gcode_generation import save_file
from .canvas_drawer import CanvasDrawer
from .machine_parameters_window import MachineParametersWindow
from .paths import GCODE_DIR, VISUAL_OBJECT_CONFIG, WORKFLOW_CONFIG
from .plugin_runtime import application_plugins
from .runtime_logging import get_logger, log_options
from .visual_objects import VisualObjectStore


logger = get_logger("gui")


@dataclass
class _PatternWorkspace:
    """Runtime UI state for one registered application pattern plugin."""

    plugin: ApplicationPatternPlugin
    notebook: Notebook
    instances: dict


class DropletGui(tk.Tk):
    def __init__(self, config_dir):
        super(DropletGui, self).__init__()
        self.config_dir = config_dir
        self.pattern_plugins = application_plugins()
        if not self.pattern_plugins:
            raise RuntimeError("No desktop-capable pattern plugins are available")
        self.pattern_plugins_by_id = {
            plugin.manifest.id: plugin for plugin in self.pattern_plugins
        }
        self.pattern_workspaces = {}
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

        self.entry = []
        self.global_locked = tk.BooleanVar(master=self, value=True)

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

        plugin_ids = [plugin.manifest.id for plugin in self.pattern_plugins]
        default_plugin_id = plugin_ids[0]
        self.workspace_mode_var = tk.StringVar(value=default_plugin_id)
        self.workspace_mode_combo = Combobox(
            mode_control,
            values=plugin_ids,
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

        # ========== LEFT FRAME: Pattern workspaces ==========
        self.left_frame = tk.Frame(self.main_frame, bg=COLORS['bg_primary'])
        self.left_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 4))
        self.left_frame.rowconfigure(0, weight=0)
        self.left_frame.rowconfigure(1, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        self.left_label = tk.Label(
            self.left_frame,
            text="PATTERN PARAMETERS",
            font=FONTS['label'],
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_primary'],
            anchor='w',
        )
        self.left_label.grid(row=0, column=0, sticky='ew', padx=2, pady=(2, 7))

        # Every application plugin receives the same tabbed workspace. Legacy
        # attributes are populated only when a plugin declares those names.
        for plugin in self.pattern_plugins:
            spec = plugin.workspace
            notebook = Notebook(
                self.left_frame,
                style="Custom.TNotebook",
            )
            notebook.grid(row=1, column=0, sticky="nsew")
            instances = {}
            self.pattern_workspaces[plugin.manifest.id] = _PatternWorkspace(
                plugin=plugin,
                notebook=notebook,
                instances=instances,
            )
            setattr(self, spec.notebook_attribute, notebook)
            setattr(self, spec.instance_map_attribute, instances)
            setattr(self, spec.count_attribute, 0)

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
            except (AttributeError, tk.TclError, ValueError):
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
            acceptance_values = acceptance_square(global_values)
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

        selected_patterns = {}
        for plugin in self.pattern_plugins:
            spec = plugin.workspace
            notebook = getattr(self, spec.notebook_attribute, None)
            instances = plugin.instance_map(self)
            selected_number, editor = selected_object(notebook, instances)
            selected_patterns[plugin.manifest.id] = (
                selected_number,
                editor,
            )
            groups = plugin.workflow_preview_groups(
                editor,
                int(selected_number or 0),
            )
            for group in groups:
                register_fields(
                    group.namespace,
                    group.fields,
                    group.entries,
                    group.source,
                )
            source = (
                "{} {} runtime inputs".format(
                    plugin.manifest.display_name,
                    selected_number,
                )
                if editor is not None
                else "{} field default".format(
                    plugin.manifest.display_name
                )
            )
            name = (
                editor.get_name()
                if editor is not None and hasattr(editor, "get_name")
                else plugin.manifest.display_name
            )
            color = (
                editor.get_color()
                if editor is not None and hasattr(editor, "get_color")
                else spec.default_color(1)
            )
            register_value(
                "{}.name".format(plugin.manifest.id),
                name,
                "str",
                "",
                source,
                "Current {} display name.".format(
                    plugin.manifest.display_name.lower()
                ),
            )
            register_value(
                "{}.color".format(plugin.manifest.id),
                color,
                "str",
                "",
                source,
                "Current {} display color.".format(
                    plugin.manifest.display_name.lower()
                ),
            )

        loading_namespace = self._current_workspace_mode()
        active_number = selected_patterns.get(
            loading_namespace,
            (0, None),
        )[0]
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
        for plugin in self.pattern_plugins:
            for index, editor in sorted(plugin.instance_map(self).items()):
                for group in plugin.visual_binding_groups(editor, index):
                    register(
                        group.namespace,
                        group.fields,
                        group.entries,
                        group.source,
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
            requested = self.workspace_mode_var.get().strip().lower()
        except Exception:
            requested = ""
        plugin_map = getattr(self, "pattern_plugins_by_id", {})
        if requested in plugin_map:
            return requested
        return next(iter(plugin_map), requested)

    def _switch_workspace_mode(self):
        mode = self._current_workspace_mode()
        workspaces = getattr(self, "pattern_workspaces", {})
        active = workspaces.get(mode)
        if active is None:
            return
        for plugin_id, workspace in workspaces.items():
            try:
                if plugin_id == mode:
                    workspace.notebook.grid()
                else:
                    workspace.notebook.grid_remove()
            except Exception:
                pass
        spec = active.plugin.workspace
        self.left_label.config(text=spec.parameter_title)
        self.add_object_button.config(text=spec.add_button_text)
        self.remove_object_button.config(text=spec.remove_button_text)
        if mode != self._last_logged_workspace_mode:
            log_options(
                logger,
                "workspace.mode_changed",
                mode=mode,
                pattern_counts={
                    plugin_id: len(workspace.instances)
                    for plugin_id, workspace in workspaces.items()
                },
            )
            self._last_logged_workspace_mode = mode

    def show_help(self):
        plugin_help = "\n".join(
            "- {}: {}".format(
                plugin.manifest.display_name,
                plugin.manifest.description or "pattern workspace",
            )
            for plugin in self.pattern_plugins
        )
        message = (
            "Installed pattern plugins:\n"
            f"{plugin_help}\n\n"
            "Use the dropdown at the top to switch workspaces, then add or "
            "remove recipe tabs for the selected plugin.\n\n"
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
        return self.instance_pattern(self._current_workspace_mode())

    def _remove_active_object(self):
        return self.subtract_pattern(self._current_workspace_mode())

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

    def _plugin_for(self, plugin_id):
        """Return a registered desktop plugin by its stable ID."""

        plugin_map = getattr(self, "pattern_plugins_by_id", None)
        if not plugin_map:
            plugin_map = {
                plugin.manifest.id: plugin
                for plugin in application_plugins()
            }
        plugin = plugin_map.get(plugin_id)
        if plugin is None:
            raise KeyError("Unknown pattern plugin: {!r}".format(plugin_id))
        return plugin

    def _workspace_for(self, plugin_id):
        workspace = getattr(self, "pattern_workspaces", {}).get(plugin_id)
        if workspace is None:
            raise KeyError(
                "Pattern workspace {!r} is not initialized".format(plugin_id)
            )
        return workspace

    def _iter_patterns(self, plugin_id):
        plugin = self._plugin_for(plugin_id)
        instances = plugin.instance_map(self)
        for index in sorted(instances):
            yield index, instances[index]

    def _iter_grids(self):
        """Compatibility iterator for the built-in grid plugin."""

        yield from self._iter_patterns("grid")

    def _iter_spirals(self):
        """Compatibility iterator for the built-in spiral plugin."""

        yield from self._iter_patterns("spiral")

    def _update_pattern_tab_title(self, plugin_id, index, title):
        workspace = self._workspace_for(plugin_id)
        tab_index = int(index) - 1
        if tab_index < 0 or tab_index >= len(workspace.notebook.tabs()):
            return
        fallback = "{} {}".format(
            workspace.plugin.manifest.display_name,
            index,
        )
        workspace.notebook.tab(
            tab_index,
            text=str(title).strip() or fallback,
        )

    def _update_grid_tab_title(self, grid_number, title):
        self._update_pattern_tab_title("grid", grid_number, title)

    def _update_spiral_tab_title(self, spiral_number, title):
        self._update_pattern_tab_title("spiral", spiral_number, title)

    def _get_max_pattern_count(self):
        default_max = 6
        if not self.entry:
            return default_max
        try:
            global_dict = entries_to_dict(self.entry, GLOBAL_FIELDS)
            max_count = int(global_dict.get("max_grid_count", default_max))
        except Exception:
            max_count = default_max
        return max(1, max_count)

    def _get_max_grid_count(self):
        """Compatibility alias for the former grid-specific helper."""

        return self._get_max_pattern_count()

    def instance_pattern(self, plugin_id):
        """Create one editor through its registered plugin factory."""

        workspace = self._workspace_for(plugin_id)
        plugin = workspace.plugin
        spec = plugin.workspace
        maximum = self._get_max_pattern_count()
        active_count = len(workspace.instances)
        if active_count >= maximum:
            log_options(
                logger,
                "pattern.add_blocked",
                plugin_id=plugin_id,
                active_count=active_count,
                maximum=maximum,
            )
            open_secondary_window(
                "Cannot add more {} recipes (maximum {})".format(
                    plugin.manifest.display_name,
                    maximum,
                )
            )
            return None

        index = active_count + 1
        tab_frame = tk.Frame(workspace.notebook)
        workspace.notebook.add(
            tab_frame,
            text="{} {}".format(plugin.manifest.display_name, index),
        )
        editor = plugin.create_editor(
            tab_frame,
            self.config_dir,
            index,
            on_name_changed=lambda name, pid=plugin_id, number=index: (
                self._update_pattern_tab_title(pid, number, name)
            ),
        )
        workspace.instances[index] = editor
        setattr(self, spec.count_attribute, len(workspace.instances))
        display_name = (
            editor.get_name()
            if hasattr(editor, "get_name")
            else "{} {}".format(plugin.manifest.display_name, index)
        )
        self._update_pattern_tab_title(plugin_id, index, display_name)
        log_options(
            logger,
            "pattern.added",
            plugin_id=plugin_id,
            pattern_index=index,
            config_path=plugin.resolve_config_path(self.config_dir, index),
            active_count=len(workspace.instances),
            maximum=maximum,
        )
        return editor

    def instance_grid(self):
        """Compatibility wrapper for the built-in grid plugin."""

        return self.instance_pattern("grid")

    def instance_spiral(self):
        """Compatibility wrapper for the built-in spiral plugin."""

        return self.instance_pattern("spiral")

    def subtract_pattern(self, plugin_id):
        """Remove the final editor from one plugin workspace."""

        workspace = self._workspace_for(plugin_id)
        plugin = workspace.plugin
        spec = plugin.workspace
        if not workspace.instances:
            logger.info(
                "pattern.remove_blocked | plugin_id=%s | reason=no_patterns",
                plugin_id,
            )
            open_secondary_window(
                "No {} recipes to remove".format(
                    plugin.manifest.display_name
                )
            )
            return None

        last_index = max(workspace.instances)
        workspace.notebook.forget(last_index - 1)
        workspace.instances.pop(last_index, None)
        setattr(self, spec.count_attribute, len(workspace.instances))
        log_options(
            logger,
            "pattern.removed",
            plugin_id=plugin_id,
            pattern_index=last_index,
            active_count=len(workspace.instances),
        )
        canvas_drawer = getattr(self, "canvas_drawer", None)
        if canvas_drawer is not None:
            try:
                canvas_drawer.refresh()
            except Exception:
                logger.exception("canvas.refresh_after_pattern_remove_failed")
        return last_index

    def subtract_grid(self):
        """Compatibility wrapper for the built-in grid plugin."""

        return self.subtract_pattern("grid")

    def subtract_spiral(self):
        """Compatibility wrapper for the built-in spiral plugin."""

        return self.subtract_pattern("spiral")

    def check_saves(self):
        pattern_counts = {
            plugin_id: len(workspace.instances)
            for plugin_id, workspace in self.pattern_workspaces.items()
        }
        log_options(
            logger,
            "defaults.save_started",
            pattern_counts=pattern_counts,
        )
        state_payload = {
            "schema_version": 2,
            "patterns": dict(pattern_counts),
        }
        # Keep legacy count keys while schema-v2 readers migrate.
        for workspace in self.pattern_workspaces.values():
            state_payload[workspace.plugin.workspace.state_count_key] = len(
                workspace.instances
            )
        write_state(state_payload, self.config_dir)

        global_dict = entries_to_dict(self.entry, GLOBAL_FIELDS)
        global_dict.update(self._get_canvas_parameter_values())
        save_defaults(
            os.path.join(self.config_dir, "config_global.json"),
            global_dict,
        )

        for workspace in self.pattern_workspaces.values():
            plugin = workspace.plugin
            for index, editor in sorted(workspace.instances.items()):
                plugin.persist_editor_defaults(
                    editor,
                    self.config_dir,
                    index,
                )
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

    def _reset_patterns(self, plugin_id):
        """Clear one workspace so a profile can rebuild exact saved state."""

        workspace = self._workspace_for(plugin_id)
        for tab_id in workspace.notebook.tabs():
            workspace.notebook.forget(tab_id)
        workspace.instances.clear()
        setattr(self, workspace.plugin.workspace.count_attribute, 0)

    def _reset_grids(self):
        """Compatibility wrapper for the built-in grid plugin."""

        self._reset_patterns("grid")

    def _reset_spirals(self):
        """Compatibility wrapper for the built-in spiral plugin."""

        self._reset_patterns("spiral")

    def _parse_generation_json_file(self, filepath):
        """Load and normalize legacy or plugin-oriented settings profiles."""
        with open(filepath, "r", encoding="utf-8") as profile_file:
            profile = json.load(profile_file)

        if not isinstance(profile, dict):
            raise ValueError("Settings profile must contain a JSON object")
        global_settings = profile.get("global_settings")
        if not isinstance(global_settings, dict):
            raise ValueError("'global_settings' must be a JSON object")

        entries_by_plugin = {}
        patterns = profile.get("patterns")
        if patterns is not None:
            if not isinstance(patterns, list):
                raise ValueError("'patterns' must be a JSON array")
            for position, pattern in enumerate(patterns, start=1):
                if not isinstance(pattern, dict):
                    raise ValueError(
                        "Pattern {} must be a JSON object".format(position)
                    )
                plugin_id = str(pattern.get("plugin_id", "")).strip().lower()
                if not plugin_id:
                    raise ValueError(
                        "Pattern {} is missing 'plugin_id'".format(position)
                    )
                if plugin_id in entries_by_plugin:
                    raise ValueError(
                        "Pattern plugin {!r} appears more than once".format(
                            plugin_id
                        )
                    )
                if plugin_id not in self.pattern_plugins_by_id:
                    raise ValueError(
                        "Profile requires unavailable pattern plugin {!r}".format(
                            plugin_id
                        )
                    )
                recipes = pattern.get("recipes", [])
                if not isinstance(recipes, list):
                    raise ValueError(
                        "Pattern {!r} 'recipes' must be a JSON array".format(
                            plugin_id
                        )
                    )
                entries_by_plugin[plugin_id] = recipes
        else:
            for plugin in self.pattern_plugins:
                profile_key = plugin.workspace.profile_key
                recipes = profile.get(profile_key, [])
                if not isinstance(recipes, list):
                    raise ValueError(
                        "{!r} must be a JSON array".format(profile_key)
                    )
                entries_by_plugin[plugin.manifest.id] = recipes

        normalized_entries = {}
        for plugin_id, recipes in entries_by_plugin.items():
            plugin = self._plugin_for(plugin_id)
            normalized_entries[plugin_id] = [
                plugin.validate_profile_entry(recipe, index)
                for index, recipe in enumerate(recipes, start=1)
            ]

        if "workflow" in profile and not isinstance(profile["workflow"], dict):
            raise ValueError("'workflow' must be a JSON object")

        profile["_pattern_entries"] = normalized_entries
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

        pattern_entries = parsed.get("_pattern_entries", {})
        for plugin_id in self.pattern_plugins_by_id:
            self._reset_patterns(plugin_id)
            plugin = self._plugin_for(plugin_id)
            recipes = pattern_entries.get(plugin_id, [])
            for index, recipe in enumerate(recipes, start=1):
                editor = self.instance_pattern(plugin_id)
                if editor is None:
                    raise ValueError(
                        "Profile exceeds the active pattern-count limit"
                    )
                plugin.restore_profile_entry(editor, recipe)
                display_name = (
                    editor.get_name()
                    if hasattr(editor, "get_name")
                    else "{} {}".format(
                        plugin.manifest.display_name,
                        index,
                    )
                )
                self._update_pattern_tab_title(
                    plugin_id,
                    index,
                    display_name,
                )

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
            pattern_counts={
                plugin_id: len(workspace.instances)
                for plugin_id, workspace in self.pattern_workspaces.items()
            },
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
