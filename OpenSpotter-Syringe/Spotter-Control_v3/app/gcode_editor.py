"""Runtime editor for the configurable spotter workflow.

The editor intentionally contains no machine program defaults.  Defaults,
validation, rendering, and persistence all belong to :mod:`gcode_workflow`.
This module only stages and edits that data in a modal Tkinter window.
"""

from __future__ import annotations

import copy
import inspect
import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from .ui_theme import COLORS, FONTS, button_options, configure_ttk_styles, entry_options
except ImportError:  # pragma: no cover - supports direct module smoke tests
    from ui_theme import COLORS, FONTS, button_options, configure_ttk_styles, entry_options


_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BLOCK_ROLES = ("start", "loading", "printing", "cleaning", "end", "custom")


def _load_workflow_core():
    """Import the workflow core lazily to avoid a GUI/core import cycle."""

    try:
        from . import gcode_workflow
    except ImportError:  # pragma: no cover - supports direct module smoke tests
        import gcode_workflow
    return gcode_workflow


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _stringify(value: Any, limit: int = 90) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _call_callback(callback: Callable[..., Any], data: Dict[str, Any]) -> None:
    """Call a save callback with data, while allowing a no-argument callback."""

    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        callback(data)
        return
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(
        parameter.kind == parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    if positional or has_varargs:
        callback(data)
    else:
        callback()


def _call_provider(provider: Any) -> Mapping[str, Any]:
    if provider is None:
        return {}
    result = provider() if callable(provider) else provider
    return result if isinstance(result, Mapping) else {}


def _set_nested(mapping: Dict[str, Any], dotted_name: str, value: Any) -> None:
    parts = [part for part in dotted_name.split(".") if part]
    if not parts:
        return
    cursor = mapping
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


def _get_nested(mapping: Mapping[str, Any], dotted_name: str, default: Any = None) -> Any:
    value: Any = mapping
    for part in dotted_name.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return value


@dataclass
class ValidationIssue:
    message: str
    severity: str = "error"
    path: str = ""
    line: Optional[int] = None

    def display(self) -> str:
        location = self.path
        if self.line is not None:
            location = f"{location}, line {self.line}" if location else f"line {self.line}"
        prefix = self.severity.upper()
        return f"{prefix}: {location}: {self.message}" if location else f"{prefix}: {self.message}"


class WorkflowBackend:
    """Narrow adapter around :mod:`gcode_workflow`'s public API."""

    def __init__(self, config_path: Any = None, store: Any = None):
        self.core = _load_workflow_core()
        if store is not None:
            self.store = store
        elif config_path is None:
            self.store = self.core.WorkflowStore()
        else:
            self.store = self.core.WorkflowStore(Path(config_path))

    def default_workflow(self) -> Dict[str, Any]:
        default_factory = getattr(self.core, "default_workflow", None)
        if callable(default_factory):
            return copy.deepcopy(default_factory())
        store_default = getattr(self.store, "default_workflow", None)
        if callable(store_default):
            return copy.deepcopy(store_default())
        raise RuntimeError("The workflow core does not expose default_workflow().")

    def load(self) -> Dict[str, Any]:
        try:
            workflow = self.store.load()
        except FileNotFoundError:
            workflow = self.default_workflow()
        if not isinstance(workflow, dict):
            raise TypeError("WorkflowStore.load() must return a dictionary.")
        return copy.deepcopy(workflow)

    def save(self, workflow: Dict[str, Any]) -> Any:
        return self.store.save(copy.deepcopy(workflow))

    def validate(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        validator = getattr(self.store, "validate", None)
        if callable(validator):
            validated = validator(copy.deepcopy(workflow))
        else:
            validated = self.core.validate_workflow(copy.deepcopy(workflow))
        if not isinstance(validated, dict):
            raise TypeError("Workflow validation must return a dictionary.")
        return validated

    def variable_catalog(
        self,
        workflow: Dict[str, Any],
        context: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        catalog = self.core.build_variable_catalog(
            context=dict(context or {}), workflow=copy.deepcopy(workflow)
        )
        if isinstance(catalog, Mapping):
            rows: List[Dict[str, Any]] = []
            for name, item in catalog.items():
                row = dict(item) if isinstance(item, Mapping) else {"value": item}
                row.setdefault("name", name)
                rows.append(row)
            return rows
        return [dict(item) for item in catalog if isinstance(item, Mapping)]

    def render_preview(
        self,
        workflow: Dict[str, Any],
        trigger: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> str:
        rendered = self.core.render_preview(
            copy.deepcopy(workflow), trigger, dict(context or {})
        )
        return rendered if isinstance(rendered, str) else _stringify(rendered, limit=100000)


class GCodeWorkflowEditor(tk.Toplevel):
    """Modal, transactional editor for a workflow stored by ``WorkflowStore``."""

    def __init__(
        self,
        parent: tk.Misc,
        config_path: Any = None,
        *,
        on_saved: Optional[Callable[..., Any]] = None,
        runtime_context: Any = None,
        variable_provider: Any = None,
        store: Any = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.on_saved = on_saved
        self.runtime_context = runtime_context
        self.variable_provider = variable_provider
        self.backend = WorkflowBackend(config_path=config_path, store=store)

        self._loading_ui = False
        self._selection_guard = False
        self._dirty = False
        self._preview_after_id: Optional[str] = None
        self._current_block: Optional[int] = None
        self._current_section: Optional[int] = None
        self._catalog_rows: List[Dict[str, Any]] = []

        try:
            loaded = self.backend.load()
        except Exception as exc:
            messagebox.showerror(
                "Workflow Editor",
                f"The workflow could not be loaded.\n\n{exc}",
                parent=parent,
            )
            self.destroy()
            raise

        self.workflow = self._normalise_workflow(loaded)
        self._original = copy.deepcopy(self.workflow)

        self.title("G-code Workflow Editor")
        self.configure(bg=COLORS["bg_primary"])
        self.minsize(1100, 700)
        self.geometry(self._initial_geometry())
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._configure_styles()
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_block_list(select=0 if self._blocks() else None)
        self._refresh_variables()
        self._refresh_preview()
        self.after_idle(self._activate_modal)

    # ------------------------------------------------------------------
    # Window and data setup
    # ------------------------------------------------------------------

    def _initial_geometry(self) -> str:
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
        except tk.TclError:
            return "1400x860"
        width = max(1100, min(1540, screen_w - 80))
        height = max(700, min(940, screen_h - 100))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _activate_modal(self) -> None:
        if not self.winfo_exists():
            return
        self._open_windowed_fullscreen()
        try:
            self._body_canvas.yview_moveto(0.0)
        except (AttributeError, tk.TclError):
            pass
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _open_windowed_fullscreen(self) -> None:
        """Maximize the editor while retaining normal window decorations."""
        try:
            self.attributes("-fullscreen", False)
        except tk.TclError:
            pass
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
        try:
            self.geometry(
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
            )
        except tk.TclError:
            pass

    def _normalise_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(workflow)
        result.setdefault("schema_version", 1)
        result.setdefault("name", "Spotter Workflow")
        blocks = result.setdefault("blocks", [])
        if not isinstance(blocks, list):
            raise TypeError("Workflow 'blocks' must be a list.")
        for block in blocks:
            if not isinstance(block, dict):
                raise TypeError("Every workflow block must be a dictionary.")
            block.setdefault("id", _new_id("block"))
            block.setdefault("name", "Untitled Block")
            block.setdefault("role", "custom")
            block.setdefault("enabled", True)
            sections = block.setdefault("sections", [])
            if not isinstance(sections, list):
                raise TypeError(f"Sections in block '{block['name']}' must be a list.")
            for section in sections:
                if not isinstance(section, dict):
                    raise TypeError("Every workflow section must be a dictionary.")
                section.setdefault("id", _new_id("section"))
                section.setdefault("name", "Untitled Section")
                section.setdefault("trigger", "")
                section.setdefault("condition", "")
                section.setdefault("template", "")
        variables = result.setdefault("custom_variables", [])
        if not isinstance(variables, list):
            raise TypeError("Workflow 'custom_variables' must be a list.")
        return result

    def _blocks(self) -> List[Dict[str, Any]]:
        return self.workflow["blocks"]

    def _sections(self, block_index: int) -> List[Dict[str, Any]]:
        return self._blocks()[block_index]["sections"]

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        configure_ttk_styles(style)

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], Any],
        *,
        accent: bool = False,
        danger: bool = False,
        width: Optional[int] = None,
    ) -> tk.Button:
        kind = "primary" if accent else "danger" if danger else "secondary"
        options = button_options(kind)
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            **options,
        )

    def _label(self, parent: tk.Misc, text: str, *, header: bool = False) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_primary"] if header else COLORS["text_secondary"],
            font=FONTS["label"] if header else FONTS["small"],
            anchor="w",
        )

    def _entry(
        self,
        parent: tk.Misc,
        textvariable: tk.Variable,
        *,
        track_changes: bool = True,
    ) -> tk.Entry:
        widget = tk.Entry(
            parent,
            textvariable=textvariable,
            **entry_options(),
        )
        if track_changes:
            widget.bind("<KeyRelease>", self._field_edited, add="+")
        return widget

    def _panel(self, parent: tk.Misc) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
        )

    def _text(self, parent: tk.Misc, *, wrap: str = "none") -> tk.Text:
        widget = tk.Text(
            parent,
            wrap=wrap,
            undo=True,
            maxundo=-1,
            bg=COLORS["bg_tertiary"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["selection"],
            font=FONTS["mono"],
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
        )
        widget.bind("<<Modified>>", self._text_edited, add="+")
        return widget

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=COLORS["bg_secondary"])
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        tk.Label(
            header,
            text="G-code Workflow",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_primary"],
            font=FONTS["title"],
        ).grid(row=0, column=0, padx=(14, 8), pady=(10, 2), sticky="w")
        tk.Label(
            header,
            text=(
                "Edit event-hook blocks and runtime variables; block order resolves "
                "sections attached to the same planner event."
            ),
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
        ).grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 9), sticky="w")

        body = tk.Frame(self, bg=COLORS["bg_primary"])
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._body_canvas = tk.Canvas(
            body,
            bg=COLORS["bg_primary"],
            highlightthickness=0,
            bd=0,
            yscrollincrement=36,
        )
        body_scroll = ttk.Scrollbar(
            body,
            orient="vertical",
            command=self._body_canvas.yview,
        )
        self._body_canvas.configure(yscrollcommand=body_scroll.set)
        self._body_canvas.grid(row=0, column=0, sticky="nsew")
        body_scroll.grid(row=0, column=1, sticky="ns")

        self._scroll_content = tk.Frame(
            self._body_canvas,
            bg=COLORS["bg_primary"],
        )
        self._scroll_content.columnconfigure(0, weight=1)
        self._scroll_content.rowconfigure(0, weight=1)
        self._body_window = self._body_canvas.create_window(
            (0, 0),
            window=self._scroll_content,
            anchor="nw",
        )
        self._scroll_content.bind(
            "<Configure>",
            self._update_body_scrollregion,
            add="+",
        )
        self._body_canvas.bind(
            "<Configure>",
            self._resize_scroll_content,
            add="+",
        )
        self.bind("<MouseWheel>", self._on_body_mousewheel, add="+")
        self.bind("<Button-4>", self._on_body_mousewheel, add="+")
        self.bind("<Button-5>", self._on_body_mousewheel, add="+")

        screen_height = max(700, self.winfo_screenheight())
        workspace_height = max(500, min(660, screen_height - 430))
        output_height = 300
        self._body_min_height = workspace_height + output_height + 20

        outer = tk.PanedWindow(
            self._scroll_content,
            orient=tk.VERTICAL,
            bg=COLORS["bg_primary"],
            sashwidth=6,
            sashrelief="flat",
            bd=0,
            height=self._body_min_height,
        )
        outer.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        workspace = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            bg=COLORS["bg_primary"],
            sashwidth=6,
            sashrelief="flat",
            bd=0,
        )
        self._build_block_panel(workspace)
        self._build_section_panel(workspace)
        self._build_variable_panel(workspace)
        outer.add(
            workspace,
            minsize=480,
            height=workspace_height,
            stretch="always",
        )

        self._build_output_panel(outer)
        outer.add(
            self.output_panel,
            minsize=260,
            height=output_height,
            stretch="always",
        )

        footer = tk.Frame(self, bg=COLORS["bg_secondary"])
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Changes are staged until Save.")
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=8, sticky="ew")
        self._button(footer, "Cancel", self.cancel).grid(row=0, column=1, padx=4, pady=6)
        self._button(footer, "Validate", self._refresh_preview).grid(
            row=0, column=2, padx=4, pady=6
        )
        self._button(footer, "Save", self.save, accent=True).grid(
            row=0, column=3, padx=(4, 12), pady=6
        )

    def _update_body_scrollregion(self, _event: Any = None) -> None:
        if not hasattr(self, "_body_canvas"):
            return
        try:
            bounds = self._body_canvas.bbox("all")
            if bounds:
                self._body_canvas.configure(scrollregion=bounds)
        except tk.TclError:
            pass

    def _resize_scroll_content(self, event: tk.Event) -> None:
        try:
            target_height = max(self._body_min_height, int(event.height))
            self._body_canvas.itemconfigure(
                self._body_window,
                width=max(1, int(event.width)),
                height=target_height,
            )
            self._update_body_scrollregion()
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass

    def _on_body_mousewheel(self, event: tk.Event):
        """Scroll the page unless the pointer is over an inner scroll widget."""
        widget = getattr(event, "widget", None)
        inner_scroll_widgets = (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)
        if isinstance(widget, inner_scroll_widgets):
            return None
        if isinstance(widget, tk.Canvas) and widget is not self._body_canvas:
            return None
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = int(getattr(event, "delta", 0))
            if delta == 0:
                return None
            direction = -1 if delta > 0 else 1
        try:
            self._body_canvas.yview_scroll(direction * 3, "units")
        except tk.TclError:
            return None
        return "break"

    def _build_block_panel(self, parent: tk.PanedWindow) -> None:
        panel = self._panel(parent)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        self._label(panel, "Workflow Blocks", header=True).grid(
            row=0, column=0, padx=10, pady=(10, 6), sticky="ew"
        )
        list_frame = tk.Frame(panel, bg=COLORS["bg_secondary"])
        list_frame.grid(row=1, column=0, padx=8, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.block_list = tk.Listbox(
            list_frame,
            exportselection=False,
            activestyle="none",
            bg=COLORS["bg_tertiary"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            font=FONTS["normal"],
            relief="flat",
            bd=0,
        )
        block_scroll = ttk.Scrollbar(list_frame, command=self.block_list.yview)
        self.block_list.configure(yscrollcommand=block_scroll.set)
        self.block_list.grid(row=0, column=0, sticky="nsew")
        block_scroll.grid(row=0, column=1, sticky="ns")
        self.block_list.bind("<<ListboxSelect>>", self._on_block_selected)

        details = tk.Frame(panel, bg=COLORS["bg_secondary"])
        details.grid(row=2, column=0, padx=8, pady=7, sticky="ew")
        details.columnconfigure(1, weight=1)
        self.block_name_var = tk.StringVar()
        self.block_role_var = tk.StringVar(value="custom")
        self.block_enabled_var = tk.BooleanVar(value=True)
        self._label(details, "Name").grid(row=0, column=0, padx=(0, 6), pady=3, sticky="w")
        self._entry(details, self.block_name_var).grid(row=0, column=1, pady=3, sticky="ew")
        self._label(details, "Role").grid(row=1, column=0, padx=(0, 6), pady=3, sticky="w")
        self.block_role_combo = ttk.Combobox(
            details,
            textvariable=self.block_role_var,
            values=_BLOCK_ROLES,
            state="readonly",
            font=FONTS["small"],
        )
        self.block_role_combo.grid(row=1, column=1, pady=3, sticky="ew")
        self.block_role_combo.bind("<<ComboboxSelected>>", self._field_edited)
        tk.Checkbutton(
            details,
            text="Enabled",
            variable=self.block_enabled_var,
            command=self._field_edited,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_primary"],
            selectcolor=COLORS["bg_tertiary"],
            activebackground=COLORS["bg_secondary"],
            activeforeground=COLORS["accent"],
            font=FONTS["small"],
        ).grid(row=2, column=1, pady=3, sticky="w")

        actions = tk.Frame(panel, bg=COLORS["bg_secondary"])
        actions.grid(row=3, column=0, padx=8, pady=(0, 9), sticky="ew")
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        block_actions = (
            ("Add", self._add_block, False),
            ("Duplicate", self._duplicate_block, False),
            ("Remove", self._remove_block, True),
            ("Move Up", lambda: self._move_block(-1), False),
            ("Move Down", lambda: self._move_block(1), False),
            ("Enable / Disable", self._toggle_block, False),
            ("Revert", self._revert_block, False),
        )
        for index, (label, command, danger) in enumerate(block_actions):
            self._button(actions, label, command, danger=danger).grid(
                row=index // 3,
                column=index % 3,
                padx=2,
                pady=2,
                sticky="ew",
            )
        parent.add(panel, minsize=250, width=285, stretch="never")

    def _build_section_panel(self, parent: tk.PanedWindow) -> None:
        panel = self._panel(parent)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(3, weight=1)
        self._label(panel, "Block Sections", header=True).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="ew"
        )

        section_sidebar = tk.Frame(panel, bg=COLORS["bg_secondary"])
        section_sidebar.grid(row=1, column=0, rowspan=3, padx=(8, 6), pady=(0, 8), sticky="ns")
        section_sidebar.rowconfigure(0, weight=1)
        self.section_list = tk.Listbox(
            section_sidebar,
            width=22,
            height=8,
            exportselection=False,
            activestyle="none",
            bg=COLORS["bg_tertiary"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            font=FONTS["small"],
            relief="flat",
            bd=0,
        )
        self.section_list.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.section_list.bind("<<ListboxSelect>>", self._on_section_selected)
        section_actions = (
            ("+", self._add_section),
            ("Duplicate", self._duplicate_section),
            ("−", self._remove_section),
            ("↑", lambda: self._move_section(-1)),
            ("↓", lambda: self._move_section(1)),
        )
        for index, (label, command) in enumerate(section_actions):
            self._button(section_sidebar, label, command).grid(
                row=1 + index // 2,
                column=index % 2,
                padx=2,
                pady=2,
                sticky="ew",
            )

        fields = tk.Frame(panel, bg=COLORS["bg_secondary"])
        fields.grid(row=1, column=1, padx=(0, 8), sticky="ew")
        fields.columnconfigure(1, weight=1)
        self.section_name_var = tk.StringVar()
        self.section_trigger_var = tk.StringVar()
        self.section_condition_var = tk.StringVar()
        self._label(fields, "Section name").grid(row=0, column=0, padx=(0, 7), pady=3)
        self._entry(fields, self.section_name_var).grid(row=0, column=1, pady=3, sticky="ew")
        self._label(fields, "Trigger").grid(row=1, column=0, padx=(0, 7), pady=3, sticky="w")
        self.trigger_combo = ttk.Combobox(
            fields,
            textvariable=self.section_trigger_var,
            state="normal",
            font=FONTS["small"],
        )
        self.trigger_combo.grid(row=1, column=1, pady=3, sticky="ew")
        self.trigger_combo.bind("<KeyRelease>", self._field_edited)
        self.trigger_combo.bind("<<ComboboxSelected>>", self._field_edited)
        self._label(fields, "Condition").grid(row=2, column=0, padx=(0, 7), pady=3, sticky="w")
        self.condition_entry = self._entry(fields, self.section_condition_var)
        self.condition_entry.grid(row=2, column=1, pady=3, sticky="ew")
        self._button(
            fields,
            "Insert selected",
            self._insert_condition_variable,
        ).grid(row=2, column=2, padx=(6, 0), pady=3, sticky="e")

        template_header = tk.Frame(panel, bg=COLORS["bg_secondary"])
        template_header.grid(row=2, column=1, padx=(0, 8), pady=(7, 4), sticky="ew")
        template_header.columnconfigure(0, weight=1)
        self._label(template_header, "Template").grid(row=0, column=0, sticky="w")
        self._button(template_header, "Insert Selected Variable", self._insert_variable).grid(
            row=0, column=1, sticky="e"
        )

        text_frame = tk.Frame(panel, bg=COLORS["bg_secondary"])
        text_frame.grid(row=3, column=1, padx=(0, 8), pady=(0, 8), sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.template_text = self._text(text_frame)
        template_y = ttk.Scrollbar(text_frame, command=self.template_text.yview)
        template_x = ttk.Scrollbar(text_frame, orient="horizontal", command=self.template_text.xview)
        self.template_text.configure(yscrollcommand=template_y.set, xscrollcommand=template_x.set)
        self.template_text.grid(row=0, column=0, sticky="nsew")
        template_y.grid(row=0, column=1, sticky="ns")
        template_x.grid(row=1, column=0, sticky="ew")
        parent.add(panel, minsize=480, stretch="always")

    def _build_variable_panel(self, parent: tk.PanedWindow) -> None:
        panel = self._panel(parent)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=3)
        panel.rowconfigure(5, weight=2)
        self._label(panel, "Variable Browser", header=True).grid(
            row=0, column=0, padx=10, pady=(10, 6), sticky="ew"
        )
        search_row = tk.Frame(panel, bg=COLORS["bg_secondary"])
        search_row.grid(row=1, column=0, padx=8, sticky="ew")
        search_row.columnconfigure(1, weight=1)
        self._label(search_row, "Search").grid(row=0, column=0, padx=(0, 6))
        self.variable_search_var = tk.StringVar()
        search = self._entry(
            search_row,
            self.variable_search_var,
            track_changes=False,
        )
        search.grid(row=0, column=1, sticky="ew")
        search.bind("<KeyRelease>", lambda _event: self._filter_variables(), add="+")
        self._button(search_row, "Refresh", self._refresh_variables).grid(row=0, column=2, padx=(5, 0))

        hint = tk.Label(
            panel,
            text="Double-click a variable to insert it at the template cursor.",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="w",
        )
        hint.grid(row=2, column=0, padx=8, pady=(5, 3), sticky="ew")

        tree_frame = tk.Frame(panel, bg=COLORS["bg_secondary"])
        tree_frame.grid(row=3, column=0, padx=8, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        columns = ("name", "value", "type", "unit", "scope")
        self.variable_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Workflow.Treeview",
            selectmode="browse",
        )
        headings = {
            "name": ("Variable", 190),
            "value": ("Current value", 105),
            "type": ("Type", 65),
            "unit": ("Unit", 65),
            "scope": ("Scope", 80),
        }
        for column, (label, width) in headings.items():
            self.variable_tree.heading(column, text=label)
            self.variable_tree.column(column, width=width, minwidth=45, stretch=column == "name")
        tree_y = ttk.Scrollbar(tree_frame, command=self.variable_tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.variable_tree.xview)
        self.variable_tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.variable_tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        self.variable_tree.bind("<Double-1>", lambda _event: self._insert_variable())
        self.variable_tree.bind("<<TreeviewSelect>>", self._show_variable_description)

        self.variable_description_var = tk.StringVar(value="Select a variable to see its description.")
        tk.Label(
            panel,
            textvariable=self.variable_description_var,
            wraplength=390,
            justify="left",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="nw",
        ).grid(row=4, column=0, padx=8, pady=5, sticky="ew")

        custom_frame = tk.LabelFrame(
            panel,
            text=" Custom Variables ",
            bg=COLORS["bg_secondary"],
            fg=COLORS["accent"],
            font=FONTS["small"],
            bd=1,
            relief="flat",
            highlightbackground=COLORS["border"],
        )
        custom_frame.grid(row=5, column=0, padx=8, pady=(0, 8), sticky="nsew")
        custom_frame.rowconfigure(0, weight=1)
        custom_frame.columnconfigure(0, weight=1)
        self.custom_list = tk.Listbox(
            custom_frame,
            height=5,
            exportselection=False,
            activestyle="none",
            bg=COLORS["bg_tertiary"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            font=FONTS["small"],
            relief="flat",
            bd=0,
        )
        self.custom_list.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.custom_list.bind("<Double-1>", lambda _event: self._edit_custom_variable())
        self._button(custom_frame, "Add", self._add_custom_variable).grid(
            row=1, column=0, padx=3, pady=(0, 5), sticky="ew"
        )
        self._button(custom_frame, "Edit", self._edit_custom_variable).grid(
            row=1, column=1, padx=3, pady=(0, 5), sticky="ew"
        )
        self._button(custom_frame, "Remove", self._remove_custom_variable, danger=True).grid(
            row=1, column=2, padx=3, pady=(0, 5), sticky="ew"
        )
        parent.add(panel, minsize=370, width=440, stretch="never")

    def _build_output_panel(self, parent: tk.PanedWindow) -> None:
        self.output_panel = self._panel(parent)
        self.output_panel.rowconfigure(1, weight=1)
        self.output_panel.columnconfigure(0, weight=1)
        preview_controls = tk.Frame(self.output_panel, bg=COLORS["bg_secondary"])
        preview_controls.grid(row=0, column=0, padx=8, pady=(7, 3), sticky="ew")
        preview_controls.columnconfigure(1, weight=1)
        self._label(preview_controls, "Preview trigger").grid(row=0, column=0, padx=(0, 7))
        self.preview_trigger_var = tk.StringVar()
        self.preview_trigger_combo = ttk.Combobox(
            preview_controls,
            textvariable=self.preview_trigger_var,
            state="normal",
            font=FONTS["small"],
        )
        self.preview_trigger_combo.grid(row=0, column=1, sticky="ew")
        self.preview_trigger_combo.bind("<<ComboboxSelected>>", self._preview_trigger_changed)
        self.preview_trigger_combo.bind("<Return>", self._preview_trigger_changed)
        self._button(preview_controls, "Refresh Preview", self._refresh_preview).grid(
            row=0, column=2, padx=(7, 0)
        )

        notebook = ttk.Notebook(self.output_panel, style="Workflow.TNotebook")
        notebook.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        preview_frame = tk.Frame(notebook, bg=COLORS["bg_secondary"])
        validation_frame = tk.Frame(notebook, bg=COLORS["bg_secondary"])
        notebook.add(preview_frame, text="Rendered Preview")
        notebook.add(validation_frame, text="Validation")
        for frame in (preview_frame, validation_frame):
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
        self.preview_text = self._text(preview_frame)
        self.preview_text.configure(undo=False, state="disabled")
        self.preview_text.grid(row=0, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self.validation_text = self._text(validation_frame, wrap="word")
        self.validation_text.configure(undo=False, state="disabled")
        self.validation_text.grid(row=0, column=0, sticky="nsew")
        validation_scroll = ttk.Scrollbar(validation_frame, command=self.validation_text.yview)
        self.validation_text.configure(yscrollcommand=validation_scroll.set)
        validation_scroll.grid(row=0, column=1, sticky="ns")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-s>", lambda _event: self.save())
        self.bind("<Control-S>", lambda _event: self.save())
        self.bind("<Escape>", lambda _event: self.cancel())

    # ------------------------------------------------------------------
    # Change tracking and selection synchronisation
    # ------------------------------------------------------------------

    def _field_edited(self, _event: Any = None) -> None:
        if self._loading_ui:
            return
        self._commit_current()
        self._refresh_current_list_labels()
        self._mark_dirty()
        self._schedule_preview()

    def _refresh_current_list_labels(self) -> None:
        if self._current_block is None or self._current_block >= len(self._blocks()):
            return
        previous_guard = self._selection_guard
        self._selection_guard = True
        try:
            block_index = self._current_block
            self.block_list.delete(block_index)
            self.block_list.insert(
                block_index,
                self._block_display(self._blocks()[block_index], block_index),
            )
            self.block_list.selection_set(block_index)
            if self._current_section is None:
                return
            sections = self._sections(block_index)
            if self._current_section >= len(sections):
                return
            section_index = self._current_section
            section = sections[section_index]
            trigger = section.get("trigger") or "no trigger"
            self.section_list.delete(section_index)
            self.section_list.insert(
                section_index,
                f"{section_index + 1}. {section.get('name', 'Section')} - {trigger}",
            )
            self.section_list.selection_set(section_index)
        finally:
            self._selection_guard = previous_guard

    def _text_edited(self, event: tk.Event) -> None:
        widget = event.widget
        try:
            modified = widget.edit_modified()
            widget.edit_modified(False)
        except tk.TclError:
            return
        if modified and not self._loading_ui and widget is self.template_text:
            self._mark_dirty()
            self._schedule_preview()

    def _mark_dirty(self) -> None:
        self._dirty = True
        if hasattr(self, "status_var"):
            self.status_var.set("Unsaved workflow changes.")

    def _schedule_preview(self) -> None:
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except tk.TclError:
                pass
        self._preview_after_id = self.after(450, self._refresh_preview)

    def _commit_current(self) -> None:
        if self._current_block is None or self._current_block >= len(self._blocks()):
            return
        block = self._blocks()[self._current_block]
        block["name"] = self.block_name_var.get().strip() or "Untitled Block"
        block["role"] = self.block_role_var.get().strip() or "custom"
        block["enabled"] = bool(self.block_enabled_var.get())
        if self._current_section is None:
            return
        sections = block["sections"]
        if self._current_section >= len(sections):
            return
        section = sections[self._current_section]
        section["name"] = self.section_name_var.get().strip() or "Untitled Section"
        section["trigger"] = self.section_trigger_var.get().strip()
        section["condition"] = self.section_condition_var.get().strip()
        try:
            section["template"] = self.template_text.get("1.0", "end-1c")
        except tk.TclError:
            section["template"] = section.get("template", "")

    def _set_block_fields_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in self.block_role_combo.master.winfo_children():
            if isinstance(child, tk.Entry):
                child.configure(state=state)
        self.block_role_combo.configure(state="readonly" if enabled else "disabled")

    def _set_section_fields_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in self.trigger_combo.master.winfo_children():
            if isinstance(child, tk.Entry):
                child.configure(state=state)
        self.trigger_combo.configure(state=state)
        self.template_text.configure(state=state)

    # ------------------------------------------------------------------
    # Block operations
    # ------------------------------------------------------------------

    def _block_display(self, block: Mapping[str, Any], index: int) -> str:
        marker = "●" if block.get("enabled", True) else "○"
        role = str(block.get("role", "custom"))
        name = str(block.get("name", f"Block {index + 1}"))
        return f"{marker} {index + 1}. {name}  [{role}]"

    def _refresh_block_list(self, select: Optional[int] = None) -> None:
        self._selection_guard = True
        try:
            self.block_list.delete(0, "end")
            for index, block in enumerate(self._blocks()):
                self.block_list.insert("end", self._block_display(block, index))
            self._current_block = None
            self._current_section = None
            if select is not None and self._blocks():
                select = max(0, min(select, len(self._blocks()) - 1))
                self.block_list.selection_set(select)
                self.block_list.activate(select)
                self.block_list.see(select)
        finally:
            self._selection_guard = False
        if select is not None and self._blocks():
            self._load_block(select)
        elif not self._blocks():
            self._clear_block_editor()

    def _on_block_selected(self, _event: Any = None) -> None:
        if self._selection_guard:
            return
        selection = self.block_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if index == self._current_block:
            return
        self._commit_current()
        self._load_block(index)

    def _load_block(self, index: int) -> None:
        if not (0 <= index < len(self._blocks())):
            self._clear_block_editor()
            return
        self._loading_ui = True
        try:
            self._current_block = index
            block = self._blocks()[index]
            self.block_name_var.set(str(block.get("name", "")))
            self.block_role_var.set(str(block.get("role", "custom")))
            self.block_enabled_var.set(bool(block.get("enabled", True)))
            self._set_block_fields_enabled(True)
            self._refresh_section_list(select=0 if block["sections"] else None)
        finally:
            self._loading_ui = False

    def _clear_block_editor(self) -> None:
        self._loading_ui = True
        try:
            self._current_block = None
            self._current_section = None
            self.block_name_var.set("")
            self.block_role_var.set("custom")
            self.block_enabled_var.set(False)
            self.section_list.delete(0, "end")
            self._clear_section_editor()
            self._set_block_fields_enabled(False)
        finally:
            self._loading_ui = False

    def _add_block(self) -> None:
        self._commit_current()
        insert_at = len(self._blocks()) if self._current_block is None else self._current_block + 1
        number = len(self._blocks()) + 1
        block = {
            "id": _new_id("block"),
            "name": f"New Block {number}",
            "role": "custom",
            "enabled": True,
            "sections": [
                {
                    "id": _new_id("section"),
                    "name": "New Section",
                    "trigger": "",
                    "condition": "",
                    "template": "",
                }
            ],
        }
        self._blocks().insert(insert_at, block)
        self._mark_dirty()
        self._refresh_block_list(select=insert_at)
        self._update_trigger_choices()
        self._schedule_preview()

    def _duplicate_block(self) -> None:
        if self._current_block is None:
            return
        self._commit_current()
        source = copy.deepcopy(self._blocks()[self._current_block])
        source["id"] = _new_id("block")
        source["name"] = f"{source.get('name', 'Block')} Copy"
        for section in source.get("sections", []):
            section["id"] = _new_id("section")
        destination = self._current_block + 1
        self._blocks().insert(destination, source)
        self._mark_dirty()
        self._refresh_block_list(select=destination)
        self._update_trigger_choices()
        self._schedule_preview()

    def _remove_block(self) -> None:
        if self._current_block is None:
            return
        self._commit_current()
        block = self._blocks()[self._current_block]
        role = block.get("role", "custom")
        warning = (
            "This is a core workflow block. Removing it can make generated jobs "
            "incomplete.\n\n"
            if role in _BLOCK_ROLES[:-1]
            else ""
        )
        if not messagebox.askyesno(
            "Remove Block",
            f"{warning}Remove '{block.get('name', 'this block')}'?",
            parent=self,
        ):
            return
        index = self._current_block
        del self._blocks()[index]
        self._mark_dirty()
        new_index = min(index, len(self._blocks()) - 1) if self._blocks() else None
        self._refresh_block_list(select=new_index)
        self._update_trigger_choices()
        self._schedule_preview()

    def _move_block(self, direction: int) -> None:
        if self._current_block is None:
            return
        self._commit_current()
        destination = self._current_block + direction
        if not (0 <= destination < len(self._blocks())):
            return
        self._blocks()[self._current_block], self._blocks()[destination] = (
            self._blocks()[destination],
            self._blocks()[self._current_block],
        )
        self._mark_dirty()
        self._refresh_block_list(select=destination)
        self._schedule_preview()

    def _toggle_block(self) -> None:
        if self._current_block is None:
            return
        self.block_enabled_var.set(not self.block_enabled_var.get())
        self._commit_current()
        self._mark_dirty()
        index = self._current_block
        self._refresh_block_list(select=index)
        self._schedule_preview()

    def _revert_block(self) -> None:
        if self._current_block is None:
            return
        self._commit_current()
        current = self._blocks()[self._current_block]
        replacement = next(
            (
                block
                for block in self._original.get("blocks", [])
                if block.get("id") == current.get("id")
            ),
            None,
        )
        if replacement is None:
            messagebox.showinfo(
                "Revert Block",
                "This block was added after the editor opened and has no saved version to restore.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Revert Block",
            f"Discard unsaved changes to '{current.get('name', 'this block')}'?",
            parent=self,
        ):
            return
        index = self._current_block
        self._blocks()[index] = copy.deepcopy(replacement)
        self._mark_dirty()
        self._refresh_block_list(select=index)
        self._update_trigger_choices()
        self._schedule_preview()

    # ------------------------------------------------------------------
    # Section operations
    # ------------------------------------------------------------------

    def _refresh_section_list(self, select: Optional[int] = None) -> None:
        self._selection_guard = True
        try:
            self.section_list.delete(0, "end")
            if self._current_block is None:
                self._clear_section_editor()
                return
            sections = self._sections(self._current_block)
            for index, section in enumerate(sections):
                trigger = section.get("trigger") or "no trigger"
                self.section_list.insert(
                    "end", f"{index + 1}. {section.get('name', 'Section')} - {trigger}"
                )
            self._current_section = None
            if select is not None and sections:
                select = max(0, min(select, len(sections) - 1))
                self.section_list.selection_set(select)
                self.section_list.activate(select)
                self.section_list.see(select)
        finally:
            self._selection_guard = False
        if self._current_block is not None and select is not None and self._sections(self._current_block):
            self._load_section(select)
        elif self._current_block is not None and not self._sections(self._current_block):
            self._clear_section_editor()

    def _on_section_selected(self, _event: Any = None) -> None:
        if self._selection_guard or self._current_block is None:
            return
        selection = self.section_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if index == self._current_section:
            return
        self._commit_current()
        self._load_section(index)

    def _load_section(self, index: int) -> None:
        if self._current_block is None:
            self._clear_section_editor()
            return
        sections = self._sections(self._current_block)
        if not (0 <= index < len(sections)):
            self._clear_section_editor()
            return
        self._loading_ui = True
        try:
            self._current_section = index
            section = sections[index]
            self.section_name_var.set(str(section.get("name", "")))
            self.section_trigger_var.set(str(section.get("trigger", "")))
            self.section_condition_var.set(str(section.get("condition", "")))
            self._set_section_fields_enabled(True)
            self.template_text.delete("1.0", "end")
            self.template_text.insert("1.0", str(section.get("template", "")))
            self.template_text.edit_modified(False)
            if not self.preview_trigger_var.get():
                self.preview_trigger_var.set(self.section_trigger_var.get())
            self._update_trigger_choices()
        finally:
            self._loading_ui = False

    def _clear_section_editor(self) -> None:
        self._loading_ui = True
        try:
            self._current_section = None
            self.section_name_var.set("")
            self.section_trigger_var.set("")
            self.section_condition_var.set("")
            self.template_text.configure(state="normal")
            self.template_text.delete("1.0", "end")
            self.template_text.edit_modified(False)
            self._set_section_fields_enabled(False)
        finally:
            self._loading_ui = False

    def _new_section(self, number: int) -> Dict[str, Any]:
        trigger = self.section_trigger_var.get().strip() or self.preview_trigger_var.get().strip()
        return {
            "id": _new_id("section"),
            "name": f"New Section {number}",
            "trigger": trigger,
            "condition": "",
            "template": "",
        }

    def _add_section(self) -> None:
        if self._current_block is None:
            return
        self._commit_current()
        sections = self._sections(self._current_block)
        insert_at = len(sections) if self._current_section is None else self._current_section + 1
        sections.insert(insert_at, self._new_section(len(sections) + 1))
        self._mark_dirty()
        self._refresh_section_list(select=insert_at)
        self._update_trigger_choices()
        self._schedule_preview()

    def _duplicate_section(self) -> None:
        if self._current_block is None or self._current_section is None:
            return
        self._commit_current()
        sections = self._sections(self._current_block)
        duplicate = copy.deepcopy(sections[self._current_section])
        duplicate["id"] = _new_id("section")
        duplicate["name"] = f"{duplicate.get('name', 'Section')} Copy"
        destination = self._current_section + 1
        sections.insert(destination, duplicate)
        self._mark_dirty()
        self._refresh_section_list(select=destination)
        self._update_trigger_choices()
        self._schedule_preview()

    def _remove_section(self) -> None:
        if self._current_block is None or self._current_section is None:
            return
        self._commit_current()
        sections = self._sections(self._current_block)
        section = sections[self._current_section]
        if not messagebox.askyesno(
            "Remove Section",
            f"Remove '{section.get('name', 'this section')}' from the block?",
            parent=self,
        ):
            return
        index = self._current_section
        del sections[index]
        self._mark_dirty()
        select = min(index, len(sections) - 1) if sections else None
        self._refresh_section_list(select=select)
        self._update_trigger_choices()
        self._schedule_preview()

    def _move_section(self, direction: int) -> None:
        if self._current_block is None or self._current_section is None:
            return
        self._commit_current()
        sections = self._sections(self._current_block)
        destination = self._current_section + direction
        if not (0 <= destination < len(sections)):
            return
        sections[self._current_section], sections[destination] = (
            sections[destination],
            sections[self._current_section],
        )
        self._mark_dirty()
        self._refresh_section_list(select=destination)
        self._schedule_preview()

    def _all_triggers(self) -> List[str]:
        triggers = list(getattr(self.backend.core, "EVENT_TRIGGERS", ()))
        seen = set(triggers)
        for block in self._blocks():
            for section in block.get("sections", []):
                trigger = str(section.get("trigger", "")).strip()
                if trigger and trigger not in seen:
                    seen.add(trigger)
                    triggers.append(trigger)
        return triggers

    def _update_trigger_choices(self) -> None:
        triggers = self._all_triggers()
        self.trigger_combo.configure(values=triggers)
        self.preview_trigger_combo.configure(values=triggers)
        if not self.preview_trigger_var.get() and triggers:
            self.preview_trigger_var.set(triggers[0])

    # ------------------------------------------------------------------
    # Variable catalog and custom variables
    # ------------------------------------------------------------------

    def _preview_context(self) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        supplied_context = _call_provider(self.runtime_context)
        context.update(copy.deepcopy(dict(supplied_context)))
        provided = _call_provider(self.variable_provider)
        for name, supplied in provided.items():
            metadata = supplied if isinstance(supplied, Mapping) else {}
            value = metadata.get("value") if metadata else supplied
            context[str(name)] = value
            _set_nested(context, str(name), value)
        return context

    def _event_preview_context(
        self,
        context: Mapping[str, Any],
        trigger: str,
        workflow: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a representative live event sample for editor previews.

        Spot/refill/wash values do not exist until generation is planned.  The
        editor derives a deterministic sample from the currently selected GUI
        recipe so preview output and the variable browser remain useful instead
        of showing neutral zeroes.
        """
        enriched = copy.deepcopy(dict(context))

        def number(path: str, default: float = 0.0) -> float:
            try:
                return float(_get_nested(enriched, path, default))
            except (TypeError, ValueError):
                return float(default)

        def integer(path: str, default: int = 0) -> int:
            try:
                return int(float(_get_nested(enriched, path, default)))
            except (TypeError, ValueError):
                return int(default)

        def put(path: str, value: Any) -> None:
            _set_nested(enriched, path, value)

        grid_spot_events = {
            "grid_spot_move", "grid_row_start", "grid_spot_dispense"
        }
        cleaning_spot_events = {
            "cleaning_spot_move", "cleaning_row_start", "cleaning_spot_dispense"
        }
        spiral_spot_events = {"spiral_drop", "spiral_continuous"}
        washing_events = {"washing_start", "washing_cycle", "washing_end"}
        rinse_events = {
            "syringe_empty_start", "rinse_cycle", "rinse_midpoint", "syringe_empty_end"
        }

        if trigger.startswith("spiral_"):
            job_kind = "spiral"
        elif (
            trigger.startswith("grid_")
            or trigger.startswith("cleaning_")
            or trigger.startswith("washing_")
        ):
            job_kind = "grid"
        else:
            job_kind = str(_get_nested(enriched, "runtime.job.kind", "grid"))
        put("runtime.job.kind", job_kind)

        # Resolve the staged conversion factor when possible, so changing it in
        # the custom-variable dialog immediately changes representative spots.
        mm_per_ul = 1.0
        for definition in (workflow or self.workflow).get("custom_variables", []):
            if definition.get("name") == "syringe_mm_per_ul":
                literal = definition.get("value")
                if isinstance(literal, (int, float)) and not isinstance(literal, bool):
                    mm_per_ul = float(literal)
                break
        try:
            preview_engine = self.backend.core.WorkflowEngine(
                workflow or self.workflow,
                enriched,
            )
            mm_per_ul = float(preview_engine.custom_value("syringe_mm_per_ul"))
            spiral_resolution = float(
                preview_engine.custom_value("spiral_resolution_radians")
            )
        except Exception:
            spiral_resolution = 0.08

        anchor_x = number("global.x_cord_of_y_line") + number("global.tuning_offset_x")
        anchor_y = number("global.y_cord_of_x_line") + number("global.tuning_offset_y")

        if trigger in grid_spot_events:
            volume_ul = number("grid.dispense_vol")
            put("runtime.spot.index", 0)
            put("runtime.spot.row", 0)
            put("runtime.spot.column", 0)
            put("runtime.spot.x", anchor_x + number("grid.grid_offset_x"))
            put("runtime.spot.y", anchor_y + number("grid.grid_offset_y"))
            put("runtime.spot.dispense_mm", volume_ul * mm_per_ul)
            put("runtime.spot.is_row_start", True)
        elif trigger in cleaning_spot_events:
            volume_ul = number("cleaning.dispense_vol_cleaning")
            put("runtime.spot.index", 0)
            put("runtime.spot.row", 0)
            put("runtime.spot.column", 0)
            put("runtime.spot.x", anchor_x + number("cleaning.grid_offset_x_cleaning"))
            put("runtime.spot.y", anchor_y + number("cleaning.grid_offset_y_cleaning"))
            put("runtime.spot.dispense_mm", volume_ul * mm_per_ul)
            put("runtime.spot.is_row_start", True)
            put("cleaning.cycle", 0)
        elif trigger in spiral_spot_events:
            center_x = number("spiral.center_x")
            center_y = number("spiral.center_y")
            start_radius = max(0.0, number("spiral.start_radius"))
            spacing = max(1e-9, number("spiral.spacing_mm", 1.5))
            base_ul = max(0.0, number("spiral.dispense_vol"))
            theta = 0.0
            radius = start_radius
            segment_length = 0.0
            continuous = trigger == "spiral_continuous"
            if continuous:
                theta = max(1e-9, spiral_resolution)
                radius = start_radius + spacing * theta / (2.0 * math.pi)
                previous_x = center_x + start_radius
                previous_y = center_y
                current_x = center_x + radius * math.cos(theta)
                current_y = center_y + radius * math.sin(theta)
                segment_length = math.hypot(current_x - previous_x, current_y - previous_y)
            else:
                current_x = center_x + radius
                current_y = center_y
            volume_ul = max(base_ul, segment_length * base_ul) if continuous else base_ul
            put("runtime.spot.index", 1 if continuous else 0)
            put("runtime.spot.start_index", 0)
            put("runtime.spot.x", current_x)
            put("runtime.spot.y", current_y)
            put("runtime.spot.dispense_ul", volume_ul)
            put("runtime.spot.dispense_mm", volume_ul * mm_per_ul)
            put("runtime.spot.segment_length", segment_length)
            put("runtime.spot.theta", theta)
            put("runtime.spot.radius", radius)
            put("runtime.spot.continuous", continuous)

        if trigger == "syringe_reload":
            namespace = "spiral" if job_kind == "spiral" else "grid"
            base_ul = max(0.0, number(f"{namespace}.dispense_vol"))
            row_add_ul = max(0.0, number("grid.row_add_volume")) if namespace == "grid" else 0.0
            rows = max(0, integer("grid.rows", 1)) if namespace == "grid" else 1
            cols = max(0, integer("grid.cols", 1)) if namespace == "grid" else 1
            print_ul = rows * cols * base_ul + max(0, rows - 1) * row_add_ul
            cleaning_ul = (
                max(0, integer("cleaning.rows_cleaning"))
                * max(0, integer("cleaning.cols_cleaning"))
                * max(0.0, number("cleaning.dispense_vol_cleaning"))
                if namespace == "grid"
                else 0.0
            )
            largest_ul = max(base_ul + row_add_ul, number("cleaning.dispense_vol_cleaning"))
            reserve_ul = largest_ul * (1.0 + max(0.0, number("global.drop_extra_aspirate")))
            cap_mm = max(0.0, number("global.max_syringe_vol")) * mm_per_ul
            total_needed_mm = (print_ul + cleaning_ul + reserve_ul) * mm_per_ul
            target_mm = min(total_needed_mm, cap_mm)
            priming_mm = max(0.0, number("global.priming_vol")) * mm_per_ul
            refill_values = {
                "reason": "representative_preview",
                "dynamic": total_needed_mm > cap_mm,
                "container_id": integer("container.id"),
                "fill_mm": target_mm + priming_mm,
                "priming_mm": priming_mm,
                "target_fill_mm": target_mm,
                "target_fill_ul": target_mm / mm_per_ul if mm_per_ul > 0 else 0.0,
                "remaining_spots_mm": print_ul * mm_per_ul,
                "cleaning_mm": cleaning_ul * mm_per_ul,
                "reserve_mm": reserve_ul * mm_per_ul,
                "total_needed_mm": total_needed_mm,
                "cap_mm": cap_mm,
            }
            for key, value in refill_values.items():
                put(f"runtime.refill.{key}", value)

        if trigger in washing_events:
            wash_x = number("washing.washing_x_pos")
            put("runtime.washing.cycle", 0)
            put("runtime.washing.x_start", wash_x)
            put("runtime.washing.x_end", wash_x + number("washing.washing_line_lenght"))

        if trigger in rinse_events:
            put("runtime.rinse.cycle", 1)
            put("runtime.rinse.phase", 2 if trigger in {"rinse_midpoint", "syringe_empty_end"} else 1)
            put("runtime.rinse.max_mm", number("global.max_syringe_mm"))
            put("runtime.rinse.min_mm", number("global.min_syringe_mm"))

        # Emptying events use the leftovers container, while reload uses the
        # loading container supplied by the host application.
        if trigger in rinse_events:
            namespace = "spiral" if job_kind == "spiral" else "grid"
            container_id = integer(f"{namespace}.leftovers_into", integer("container.id"))
            put("container.id", container_id)
            put("container.x", number(f"global.container{container_id}_x"))
            put("container.y", number(f"global.container{container_id}_y"))
            put("container.z", number(f"global.container{container_id}_z"))
        return enriched

    def _preview_trigger_changed(self, _event: Any = None) -> None:
        self._refresh_variables()
        self._refresh_preview()

    def _provider_catalog(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        for name, supplied in _call_provider(self.variable_provider).items():
            if isinstance(supplied, Mapping):
                row = dict(supplied)
            else:
                row = {"value": supplied}
            row.setdefault("name", str(name))
            row.setdefault("label", str(name))
            row.setdefault("type", type(row.get("value")).__name__)
            row.setdefault("unit", "")
            row.setdefault("scope", str(name).split(".", 1)[0] if "." in str(name) else "runtime")
            row.setdefault("source", "runtime UI")
            row.setdefault("description", "Current value supplied by the runtime application.")
            rows[str(name)] = row
        return rows

    def _refresh_variables(self) -> None:
        self._commit_current()
        try:
            context = self._preview_context()
            context = self._event_preview_context(
                context,
                self.preview_trigger_var.get().strip(),
            )
            catalog = self.backend.variable_catalog(self.workflow, context)
        except Exception as exc:
            catalog = []
            self.status_var.set(f"Variable catalog unavailable: {exc}")

        rows: Dict[str, Dict[str, Any]] = {}
        for item in catalog:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            row = dict(item)
            row.setdefault("label", name)
            row.setdefault("value", "")
            row.setdefault("type", "")
            row.setdefault("unit", "")
            row.setdefault("scope", "")
            row.setdefault("source", "workflow")
            row.setdefault("description", "")
            rows[name] = row
        for name, supplied in self._provider_catalog().items():
            if name in rows:
                rows[name].update({key: value for key, value in supplied.items() if value not in (None, "")})
            else:
                rows[name] = supplied
        self._catalog_rows = sorted(
            rows.values(), key=lambda row: (str(row.get("scope", "")), str(row.get("name", "")))
        )
        self._filter_variables()
        self._refresh_custom_list()

    def _filter_variables(self) -> None:
        if not hasattr(self, "variable_tree"):
            return
        selected_name = self._selected_variable_name()
        query = self.variable_search_var.get().strip().lower()
        self.variable_tree.delete(*self.variable_tree.get_children())
        self._visible_variable_rows: Dict[str, Dict[str, Any]] = {}
        select_iid = None
        for index, row in enumerate(self._catalog_rows):
            haystack = " ".join(
                str(row.get(key, ""))
                for key in ("name", "label", "description", "scope", "source", "unit", "type")
            ).lower()
            if query and query not in haystack:
                continue
            iid = f"variable_{index}"
            self._visible_variable_rows[iid] = row
            self.variable_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("name", ""),
                    _stringify(row.get("value", "")),
                    row.get("type", ""),
                    row.get("unit", ""),
                    row.get("scope", ""),
                ),
            )
            if row.get("name") == selected_name:
                select_iid = iid
        if select_iid:
            self.variable_tree.selection_set(select_iid)
            self.variable_tree.see(select_iid)

    def _selected_variable(self) -> Optional[Dict[str, Any]]:
        selection = self.variable_tree.selection()
        if not selection:
            return None
        return self._visible_variable_rows.get(selection[0])

    def _selected_variable_name(self) -> Optional[str]:
        row = self._selected_variable() if hasattr(self, "_visible_variable_rows") else None
        return str(row.get("name")) if row else None

    def _show_variable_description(self, _event: Any = None) -> None:
        row = self._selected_variable()
        if not row:
            self.variable_description_var.set("Select a variable to see its description.")
            return
        label = row.get("label") or row.get("name")
        source = row.get("source") or "workflow"
        description = row.get("description") or "No description provided."
        triggers = row.get("triggers") or []
        events = (
            "\nEvents: " + ", ".join(str(trigger) for trigger in triggers)
            if triggers
            else ""
        )
        job_kinds = row.get("job_kinds") or []
        jobs = (
            "\nJobs: " + ", ".join(str(kind) for kind in job_kinds)
            if job_kinds
            else ""
        )
        self.variable_description_var.set(
            f"{label} - {source}\n{description}{events}{jobs}"
        )

    def _insert_variable(self) -> None:
        row = self._selected_variable()
        if not row:
            messagebox.showinfo(
                "Insert Variable",
                "Select a variable in the browser first.",
                parent=self,
            )
            return
        if self._current_section is None:
            messagebox.showinfo(
                "Insert Variable",
                "Select or add a workflow section first.",
                parent=self,
            )
            return
        name = str(row.get("name", "")).strip()
        if not name:
            return
        try:
            self.template_text.insert("insert", "{{" + name + "}}")
            self.template_text.focus_set()
        except tk.TclError:
            return
        self._mark_dirty()
        self._schedule_preview()

    def _insert_condition_variable(self) -> None:
        """Insert the selected catalog path as a raw safe expression name."""
        row = self._selected_variable()
        if not row:
            messagebox.showinfo(
                "Insert Variable",
                "Select a variable in the browser first.",
                parent=self,
            )
            return
        if self._current_section is None:
            messagebox.showinfo(
                "Insert Variable",
                "Select or add a workflow section first.",
                parent=self,
            )
            return
        name = str(row.get("name", "")).strip()
        if not name:
            return
        try:
            cursor = self.condition_entry.index(tk.INSERT)
            current = self.section_condition_var.get()
            before = " " if cursor and not current[:cursor].endswith(" ") else ""
            after = (
                " "
                if cursor < len(current) and not current[cursor:].startswith(" ")
                else ""
            )
            self.condition_entry.insert(cursor, f"{before}{name}{after}")
            self.condition_entry.focus_set()
        except tk.TclError:
            return
        self._field_edited()

    def _custom_variables(self) -> List[Dict[str, Any]]:
        return self.workflow["custom_variables"]

    def _expression_variable_names(
        self, editing: Optional[Mapping[str, Any]] = None
    ) -> List[str]:
        """Return every catalog path, excluding the variable being edited."""
        editing_name = str((editing or {}).get("name", "")).strip()
        blocked = f"custom.{editing_name}" if editing_name else ""
        return sorted(
            {
                str(row.get("name", "")).strip()
                for row in self._catalog_rows
                if str(row.get("name", "")).strip()
                and str(row.get("name", "")).strip() != blocked
            },
            key=str.casefold,
        )

    def _refresh_custom_list(self, select: Optional[int] = None) -> None:
        self.custom_list.delete(0, "end")
        for variable in self._custom_variables():
            mode = "fx" if "expression" in variable else "="
            unit = f" {variable.get('unit')}" if variable.get("unit") else ""
            self.custom_list.insert("end", f"{mode} {variable.get('name', 'unnamed')} [{variable.get('type', '')}{unit}]")
        if select is not None and self._custom_variables():
            select = max(0, min(select, len(self._custom_variables()) - 1))
            self.custom_list.selection_set(select)
            self.custom_list.activate(select)
            self.custom_list.see(select)

    def _open_custom_dialog(
        self, variable: Optional[Mapping[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        existing_names = {
            str(item.get("name", ""))
            for item in self._custom_variables()
            if item is not variable
        }
        dialog = _CustomVariableDialog(
            self,
            variable=dict(variable or {}),
            existing_names=existing_names,
            variable_names=self._expression_variable_names(variable),
        )
        self.wait_window(dialog)
        self.after_idle(self._activate_modal)
        return dialog.result

    def _add_custom_variable(self) -> None:
        variable = self._open_custom_dialog()
        if variable is None:
            return
        self._custom_variables().append(variable)
        self._mark_dirty()
        self._refresh_variables()
        self._refresh_custom_list(select=len(self._custom_variables()) - 1)
        self._schedule_preview()

    def _edit_custom_variable(self) -> None:
        selection = self.custom_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        original = self._custom_variables()[index]
        existing_names = {
            str(item.get("name", ""))
            for item_index, item in enumerate(self._custom_variables())
            if item_index != index
        }
        dialog = _CustomVariableDialog(
            self,
            variable=copy.deepcopy(original),
            existing_names=existing_names,
            variable_names=self._expression_variable_names(original),
        )
        self.wait_window(dialog)
        self.after_idle(self._activate_modal)
        if dialog.result is None:
            return
        self._custom_variables()[index] = dialog.result
        self._mark_dirty()
        self._refresh_variables()
        self._refresh_custom_list(select=index)
        self._schedule_preview()

    def _remove_custom_variable(self) -> None:
        selection = self.custom_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        variable = self._custom_variables()[index]
        if not messagebox.askyesno(
            "Remove Variable",
            (
                f"Remove '{variable.get('name', 'this variable')}'?\n\n"
                "Templates or expressions that use it will fail validation until updated."
            ),
            parent=self,
        ):
            return
        del self._custom_variables()[index]
        self._mark_dirty()
        self._refresh_variables()
        self._refresh_custom_list(select=min(index, len(self._custom_variables()) - 1))
        self._schedule_preview()

    # ------------------------------------------------------------------
    # Validation, preview, persistence
    # ------------------------------------------------------------------

    def _issues_from_error(self, error: BaseException) -> List[ValidationIssue]:
        raw = getattr(error, "errors", None)
        if raw is None:
            raw = getattr(error, "issues", None)
        if raw is None:
            return [ValidationIssue(str(error) or error.__class__.__name__)]
        if isinstance(raw, Mapping):
            raw = raw.get("errors", raw.get("issues", [raw]))
        if isinstance(raw, (str, bytes)):
            raw = [raw]
        issues = []
        for item in raw:
            if isinstance(item, Mapping):
                issues.append(
                    ValidationIssue(
                        message=str(item.get("message", item.get("error", item))),
                        severity=str(item.get("severity", "error")).lower(),
                        path=str(item.get("path", item.get("field", ""))),
                        line=item.get("line") if isinstance(item.get("line"), int) else None,
                    )
                )
            else:
                issues.append(ValidationIssue(str(item)))
        return issues

    def _validate_staged(self) -> Tuple[Optional[Dict[str, Any]], List[ValidationIssue]]:
        self._commit_current()
        try:
            return self.backend.validate(self.workflow), []
        except Exception as exc:
            return None, self._issues_from_error(exc)

    def _write_readonly(self, widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.edit_modified(False)
        widget.configure(state="disabled")

    def _refresh_preview(self) -> None:
        self._preview_after_id = None
        if not self.winfo_exists():
            return
        validated, issues = self._validate_staged()
        if issues:
            self._write_readonly(
                self.validation_text,
                "\n".join(issue.display() for issue in issues),
            )
            self._write_readonly(
                self.preview_text,
                "Preview is unavailable until validation errors are resolved.",
            )
            self.status_var.set(f"Workflow has {len(issues)} validation error(s).")
            return
        self._write_readonly(self.validation_text, "Workflow is valid.")
        trigger = self.preview_trigger_var.get().strip()
        if not trigger:
            self._write_readonly(
                self.preview_text,
                "Choose a trigger to render its enabled workflow sections.",
            )
            self.status_var.set("Workflow is valid; select a trigger to preview it.")
            return
        try:
            context = self._preview_context()
            context = self._event_preview_context(
                context,
                trigger,
                validated or self.workflow,
            )
            preview = self.backend.render_preview(validated or self.workflow, trigger, context)
        except Exception as exc:
            issue = ValidationIssue(str(exc), path=f"trigger {trigger}")
            self._write_readonly(self.validation_text, issue.display())
            self._write_readonly(self.preview_text, "Preview could not be rendered.")
            self.status_var.set("Preview context is incomplete or invalid.")
            return
        self._write_readonly(
            self.preview_text,
            preview if preview else "No enabled section emits content for this trigger.",
        )
        self.status_var.set("Workflow is valid. Changes remain staged until Save.")

    def save(self) -> bool:
        validated, issues = self._validate_staged()
        if issues or validated is None:
            self._write_readonly(
                self.validation_text,
                "\n".join(issue.display() for issue in issues),
            )
            self.status_var.set("Save blocked by workflow validation errors.")
            messagebox.showerror(
                "Cannot Save Workflow",
                "Resolve the validation errors shown at the bottom of the editor, then save again.",
                parent=self,
            )
            return False
        try:
            destination = self.backend.save(validated)
        except Exception as exc:
            messagebox.showerror(
                "Cannot Save Workflow",
                f"The workflow could not be saved.\n\n{exc}",
                parent=self,
            )
            self.status_var.set("Workflow save failed; staged changes are still open.")
            return False

        self.workflow = copy.deepcopy(validated)
        self._original = copy.deepcopy(validated)
        self._dirty = False
        callback_error = None
        if self.on_saved is not None:
            try:
                _call_callback(self.on_saved, copy.deepcopy(validated))
            except Exception as exc:  # persistence already succeeded
                callback_error = exc
        if callback_error is not None:
            messagebox.showwarning(
                "Workflow Saved",
                (
                    f"The workflow was saved to {destination}, but the host refresh callback failed.\n\n"
                    f"{callback_error}"
                ),
                parent=self,
            )
        self.destroy()
        return True

    def cancel(self) -> None:
        self._commit_current()
        changed = self._dirty or self.workflow != self._original
        if changed and not messagebox.askyesno(
            "Discard Workflow Changes",
            "Discard all staged workflow and variable changes?",
            parent=self,
        ):
            return
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except tk.TclError:
                pass
        self.destroy()


class _CustomVariableDialog(tk.Toplevel):
    """Small modal editor for one literal or calculated custom variable."""

    def __init__(
        self,
        parent: GCodeWorkflowEditor,
        *,
        variable: Dict[str, Any],
        existing_names: Iterable[str],
        variable_names: Iterable[str] = (),
    ):
        super().__init__(parent)
        self.parent = parent
        self.variable = variable
        self.existing_names = set(existing_names)
        self.variable_names = sorted(set(variable_names), key=str.casefold)
        self.result: Optional[Dict[str, Any]] = None
        self.title("Custom Variable")
        self.configure(bg=COLORS["bg_secondary"])
        self.resizable(True, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.name_var = tk.StringVar(value=str(variable.get("name", "")))
        self.label_var = tk.StringVar(value=str(variable.get("label", "")))
        self.type_var = tk.StringVar(value=str(variable.get("type", "number")))
        self.unit_var = tk.StringVar(value=str(variable.get("unit", "")))
        self.mode_var = tk.StringVar(value="expression" if "expression" in variable else "literal")
        initial_value = variable.get("expression", variable.get("value", ""))
        self.value_var = tk.StringVar(value=str(initial_value))
        self.description_var = tk.StringVar(value=str(variable.get("description", "")))
        self._build()
        self._update_mode_hint()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._accept())
        self.update_idletasks()
        width = 620
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.after_idle(self._activate)

    def _activate(self) -> None:
        try:
            self.grab_set()
            self.name_entry.focus_set()
        except tk.TclError:
            pass

    def _entry(self, parent: tk.Misc, variable: tk.Variable) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            **entry_options(),
        )

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        labels = (
            "Name",
            "Label",
            "Type",
            "Unit",
            "Mode",
            "Value / expression",
            "Description",
        )
        for row, label in enumerate(labels):
            tk.Label(
                self,
                text=label,
                bg=COLORS["bg_secondary"],
                fg=COLORS["text_secondary"],
                font=FONTS["small"],
                anchor="w",
            ).grid(row=row, column=0, padx=(12, 8), pady=5, sticky="w")
        self.name_entry = self._entry(self, self.name_var)
        self.name_entry.grid(row=0, column=1, padx=(0, 12), pady=(12, 5), sticky="ew")
        self._entry(self, self.label_var).grid(row=1, column=1, padx=(0, 12), pady=5, sticky="ew")
        type_combo = ttk.Combobox(
            self,
            textvariable=self.type_var,
            values=("number", "integer", "boolean", "string"),
            state="readonly",
            font=FONTS["small"],
        )
        type_combo.grid(row=2, column=1, padx=(0, 12), pady=5, sticky="ew")
        self._entry(self, self.unit_var).grid(row=3, column=1, padx=(0, 12), pady=5, sticky="ew")

        mode_frame = tk.Frame(self, bg=COLORS["bg_secondary"])
        mode_frame.grid(row=4, column=1, padx=(0, 12), pady=(4, 1), sticky="ew")
        for column, (label, mode) in enumerate((("Literal", "literal"), ("Expression", "expression"))):
            tk.Radiobutton(
                mode_frame,
                text=label,
                value=mode,
                variable=self.mode_var,
                command=self._update_mode_hint,
                bg=COLORS["bg_secondary"],
                fg=COLORS["text_primary"],
                selectcolor=COLORS["bg_tertiary"],
                activebackground=COLORS["bg_secondary"],
                activeforeground=COLORS["accent"],
                font=FONTS["small"],
            ).grid(row=0, column=column, sticky="w", padx=(0, 12))
        self.value_entry = self._entry(self, self.value_var)
        self.value_entry.grid(row=5, column=1, padx=(0, 12), pady=5, sticky="ew")
        self._entry(self, self.description_var).grid(row=6, column=1, padx=(0, 12), pady=5, sticky="ew")

        variable_row = tk.Frame(self, bg=COLORS["bg_secondary"])
        variable_row.grid(
            row=7,
            column=0,
            columnspan=2,
            padx=12,
            pady=(3, 5),
            sticky="ew",
        )
        variable_row.columnconfigure(1, weight=1)
        tk.Label(
            variable_row,
            text="Expression variable",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.expression_variable_var = tk.StringVar(
            value=self.variable_names[0] if self.variable_names else ""
        )
        self.expression_variable_combo = ttk.Combobox(
            variable_row,
            textvariable=self.expression_variable_var,
            values=self.variable_names,
            state="normal",
            font=FONTS["small"],
        )
        self.expression_variable_combo.grid(row=0, column=1, sticky="ew")
        tk.Button(
            variable_row,
            text="Insert",
            command=self._insert_expression_variable,
            **button_options("secondary"),
        ).grid(row=0, column=2, padx=(6, 0))
        self.mode_hint_var = tk.StringVar()
        tk.Label(
            self,
            textvariable=self.mode_hint_var,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="w",
        ).grid(row=8, column=0, columnspan=2, padx=12, pady=(2, 8), sticky="ew")

        buttons = tk.Frame(self, bg=COLORS["bg_secondary"])
        buttons.grid(row=9, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="e")
        tk.Button(
            buttons,
            text="Cancel",
            command=self.destroy,
            **button_options("secondary"),
        ).pack(side="left", padx=3)
        tk.Button(
            buttons,
            text="Apply",
            command=self._accept,
            **button_options("primary"),
        ).pack(side="left", padx=3)

    def _insert_expression_variable(self) -> None:
        name = self.expression_variable_var.get().strip()
        if not name:
            return
        if self.mode_var.get() != "expression":
            self.mode_var.set("expression")
            self._update_mode_hint()
        try:
            cursor = self.value_entry.index(tk.INSERT)
            current = self.value_var.get()
            before = " " if cursor and not current[:cursor].endswith(" ") else ""
            after = (
                " "
                if cursor < len(current) and not current[cursor:].startswith(" ")
                else ""
            )
            self.value_entry.insert(cursor, f"{before}{name}{after}")
            self.value_entry.focus_set()
        except tk.TclError:
            return

    def _update_mode_hint(self) -> None:
        if self.mode_var.get() == "expression":
            self.mode_hint_var.set(
                "Expressions may reference catalog variables and use the core's safe arithmetic functions."
            )
        else:
            self.mode_hint_var.set("Literal values are converted according to the selected type.")

    def _literal_value(self, text: str, variable_type: str) -> Any:
        if variable_type == "string":
            return text
        if variable_type == "boolean":
            lowered = text.strip().lower()
            if lowered in ("true", "yes", "1", "on"):
                return True
            if lowered in ("false", "no", "0", "off"):
                return False
            raise ValueError("Boolean literals must be true/false, yes/no, on/off, or 1/0.")
        if variable_type == "integer":
            return int(text.strip())
        if variable_type == "number":
            value = float(text.strip())
            return int(value) if value.is_integer() else value
        raise ValueError(f"Unsupported variable type: {variable_type}")

    def _accept(self) -> None:
        name = self.name_var.get().strip()
        if not _VARIABLE_NAME_RE.fullmatch(name):
            messagebox.showerror(
                "Invalid Variable",
                "Use a letter or underscore first, followed by letters, digits, or underscores.",
                parent=self,
            )
            return
        if name in self.existing_names:
            messagebox.showerror(
                "Invalid Variable",
                f"A custom variable named '{name}' already exists.",
                parent=self,
            )
            return
        variable_type = self.type_var.get().strip() or "number"
        text = self.value_var.get()
        result: Dict[str, Any] = {
            "name": name,
            "label": self.label_var.get().strip() or name.replace("_", " ").title(),
            "type": variable_type,
            "unit": self.unit_var.get().strip(),
            "description": self.description_var.get().strip(),
        }
        if self.mode_var.get() == "expression":
            expression = text.strip()
            if not expression:
                messagebox.showerror(
                    "Invalid Variable",
                    "Enter an expression for a calculated variable.",
                    parent=self,
                )
                return
            result["expression"] = expression
        else:
            try:
                result["value"] = self._literal_value(text, variable_type)
            except (TypeError, ValueError) as exc:
                messagebox.showerror("Invalid Variable", str(exc), parent=self)
                return
        self.result = result
        self.destroy()


WorkflowEditor = GCodeWorkflowEditor


def open_workflow_editor(
    parent: tk.Misc,
    config_path: Any = None,
    *,
    on_saved: Optional[Callable[..., Any]] = None,
    runtime_context: Any = None,
    variable_provider: Any = None,
    store: Any = None,
) -> GCodeWorkflowEditor:
    """Open and return the modal runtime workflow editor.

    ``variable_provider`` may be a mapping or a no-argument callable returning
    current runtime values. ``runtime_context`` follows the same convention.
    The workflow is persisted only when the editor's Save action succeeds.
    """

    return GCodeWorkflowEditor(
        parent,
        config_path,
        on_saved=on_saved,
        runtime_context=runtime_context,
        variable_provider=variable_provider,
        store=store,
    )


open_gcode_workflow_editor = open_workflow_editor


__all__ = [
    "GCodeWorkflowEditor",
    "WorkflowEditor",
    "open_workflow_editor",
    "open_gcode_workflow_editor",
]
