"""Schema-driven Tk form construction shared by core screens and plugins."""

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Optional

from ..schema import TRUE_VALUES, Field
from ...ui_theme import COLORS, FONTS, entry_options


ENTRY_WIDGET = "entry"
COMBOBOX_WIDGET = "combobox"
SUPPORTED_WIDGETS = frozenset((ENTRY_WIDGET, COMBOBOX_WIDGET))


def _widget_kind(field: Field) -> str:
    """Return the requested widget kind, inferring a combobox from choices."""

    declared = str(field.widget or "").strip().lower()
    if not declared:
        return COMBOBOX_WIDGET if field.choices else ENTRY_WIDGET
    if declared not in SUPPORTED_WIDGETS:
        raise ValueError(
            "Unsupported widget {!r} for field {!r}; expected one of {}".format(
                field.widget,
                field.key,
                ", ".join(sorted(SUPPORTED_WIDGETS)),
            )
        )
    return declared


def _display_value(field: Field, value: Any) -> str:
    """Format a field value for a readonly combobox."""

    if str(field.unit).strip().lower() == "bool" or isinstance(
        field.default,
        bool,
    ):
        enabled = (
            value.strip().lower() in TRUE_VALUES
            if isinstance(value, str)
            else bool(value)
        )
        return "True" if enabled else "False"
    return str(value)


def _choice_values(field: Field) -> List[str]:
    """Return choices in the same display format used for default values."""

    return [_display_value(field, choice) for choice in field.choices]


def _create_input_widget(parent: Any, field: Field) -> Any:
    """Create the input control declared by ``field``."""

    kind = _widget_kind(field)
    if kind == COMBOBOX_WIDGET:
        return ttk.Combobox(
            parent,
            values=_choice_values(field),
            state="readonly",
            font=FONTS["small"],
        )
    return tk.Entry(parent, **entry_options(mono=True))


def _set_initial_value(widget: Any, field: Field, value: Any) -> None:
    """Populate a newly created widget while tolerating legacy Tk shims."""

    is_combobox = isinstance(widget, ttk.Combobox)
    display_value = (
        _display_value(field, value) if is_combobox else str(value)
    )
    try:
        if is_combobox:
            widget.set(display_value)
        else:
            widget.insert(0, display_value)
    except Exception:
        # Some downstream integrations provide entry-like widget shims rather
        # than real Tk controls. Retain the historical best-effort behavior.
        try:
            widget.insert(0, display_value)
        except Exception:
            pass


def _request_canvas_redraw(gui: Any) -> None:
    """Request a preview redraw when a compatible GUI host is available."""

    drawer = getattr(gui, "canvas_drawer", None)
    redraw = getattr(drawer, "request_redraw", None)
    if callable(redraw):
        redraw()


def _bind_redraw(widget: Any, gui: Any) -> None:
    """Bind the appropriate edit event to the optional canvas preview."""

    if gui is None or not hasattr(gui, "canvas_drawer"):
        return
    event_name = (
        "<<ComboboxSelected>>"
        if isinstance(widget, ttk.Combobox)
        else "<KeyRelease>"
    )
    widget.bind(event_name, lambda _event: _request_canvas_redraw(gui))


def _create_tab_frames(
    fields: Iterable[Field],
    input_frame: Any,
) -> Dict[str, Any]:
    """Create notebook pages for each distinct non-empty field tab."""

    tab_names = []
    for field in fields:
        tab_name = str(field.tab or "")
        if tab_name and tab_name not in tab_names:
            tab_names.append(tab_name)
    if not tab_names:
        input_frame.columnconfigure(1, weight=1)
        return {}

    notebook = ttk.Notebook(input_frame, style="Custom.TNotebook")
    notebook.grid(row=0, column=0, sticky="nsew")
    input_frame.rowconfigure(0, weight=1)
    input_frame.columnconfigure(0, weight=1)

    tab_frames = {}
    for tab_name in tab_names:
        frame = tk.Frame(
            notebook,
            bg=COLORS["bg_secondary"],
            relief="flat",
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        for column in range(3):
            frame.columnconfigure(column, weight=1 if column == 1 else 0)
        frame.rowconfigure(0, weight=0)
        notebook.add(frame, text=tab_name)
        tab_frames[tab_name] = frame
    return tab_frames


def create_labels(
    fields: Iterable[Field],
    defaults: Mapping[str, Any],
    entries: MutableSequence[Any],
    input_frame: Any,
    gui: Optional[Any] = None,
    start_row: int = 1,
    widgets_list: Optional[MutableSequence[Any]] = None,
) -> None:
    """Build labeled controls for ``fields`` and append inputs to ``entries``.

    Fields with a ``tab`` value are grouped into notebook pages. A field uses
    a normal entry by default, or a readonly combobox when its schema declares
    ``widget="combobox"`` or supplies ``choices``.

    The argument order intentionally matches the historical
    :func:`app.grid.create_labels` helper so existing plugins and integrations
    can migrate without call-site changes.
    """

    field_list = list(fields)
    tab_frames = _create_tab_frames(field_list, input_frame)
    row_by_tab = dict((tab_name, start_row) for tab_name in tab_frames)

    for index, field in enumerate(field_list):
        tab_name = str(field.tab or "")
        parent = tab_frames.get(tab_name, input_frame)
        if tab_name in row_by_tab:
            row = row_by_tab[tab_name]
            row_by_tab[tab_name] += 1
        else:
            row = start_row + index

        background = parent.cget("bg")
        label = tk.Label(
            parent,
            text=field.label,
            bg=background,
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
        )
        input_widget = _create_input_widget(parent, field)
        unit_label = tk.Label(
            parent,
            text=field.unit,
            bg=background,
            fg=COLORS["text_muted"],
            font=FONTS["caption"],
        )

        value = defaults.get(field.key, field.default)
        _set_initial_value(input_widget, field, value)
        _bind_redraw(input_widget, gui)

        label.grid(row=row, column=0, sticky="WE", pady=4, padx=8)
        input_widget.grid(row=row, column=1, sticky="WE", padx=4, pady=4)
        unit_label.grid(row=row, column=2, sticky="W", pady=4, padx=4)

        entries.append(input_widget)
        if widgets_list is not None:
            widgets_list.extend((label, input_widget, unit_label))


__all__ = [
    "COMBOBOX_WIDGET",
    "ENTRY_WIDGET",
    "SUPPORTED_WIDGETS",
    "create_labels",
]
