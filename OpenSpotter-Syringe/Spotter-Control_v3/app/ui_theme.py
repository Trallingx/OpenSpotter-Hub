"""Shared visual system for the OpenSpotter desktop tools.

The palette is deliberately neutral and low-saturation so experimental data,
warnings, and plotted series remain the most prominent elements on screen.
Classic Tk widgets and ttk widgets both consume these tokens.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict


COLORS = {
    # Surfaces
    "bg_primary": "#0d1114",
    "bg_secondary": "#151a1e",
    "bg_tertiary": "#20272c",
    "bg_elevated": "#273036",
    "canvas": "#0a0e11",
    # Interaction
    "accent": "#79a7b5",
    "accent_hover": "#92bcc8",
    "accent_muted": "#263c44",
    "alt_accent": "#9babb3",
    "hover": "#2a3339",
    "selection": "#314852",
    "focus": "#8ab5c1",
    # Content
    "text_primary": "#e5eaed",
    "text_secondary": "#9aa6ad",
    "text_muted": "#68747b",
    "text_on_accent": "#0b1114",
    "border": "#303940",
    "border_strong": "#48545c",
    "disabled_bg": "#181e22",
    "disabled_text": "#7b878e",
    # Status
    "success": "#769a84",
    "success_hover": "#88aa95",
    "warning": "#b39a6d",
    "warning_hover": "#c3aa7c",
    "error": "#b86e72",
    "error_hover": "#c98084",
    # Plotting
    "grid_minor": "#182126",
    "grid_major": "#253239",
    "axis": "#8fa3ad",
    "axis_x": "#ba7779",
    "axis_y": "#68a1ad",
    "plot_outline": "#52616a",
    "sensor_fill": "#1c252a",
    "sensor_outline": "#677983",
}


FONTS = {
    "display": ("Segoe UI Semibold", 20),
    "title": ("Segoe UI Semibold", 17),
    "header": ("Segoe UI Semibold", 11),
    "label": ("Segoe UI Semibold", 9),
    "normal": ("Segoe UI", 10),
    "small": ("Segoe UI", 9),
    "caption": ("Segoe UI", 8),
    "mono": ("Consolas", 10),
    "mono_small": ("Consolas", 9),
}


def configure_ttk_styles(style: ttk.Style) -> None:
    """Apply the shared theme to ttk controls owned by ``style``."""

    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        ".",
        background=COLORS["bg_secondary"],
        foreground=COLORS["text_primary"],
        fieldbackground=COLORS["bg_tertiary"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        troughcolor=COLORS["bg_primary"],
        selectbackground=COLORS["selection"],
        selectforeground=COLORS["text_primary"],
        font=FONTS["normal"],
    )

    style.configure(
        "TCombobox",
        background=COLORS["bg_tertiary"],
        fieldbackground=COLORS["bg_tertiary"],
        foreground=COLORS["text_primary"],
        arrowcolor=COLORS["text_secondary"],
        bordercolor=COLORS["border"],
        padding=(8, 5),
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", COLORS["bg_tertiary"]),
            ("disabled", COLORS["disabled_bg"]),
        ],
        foreground=[
            ("readonly", COLORS["text_primary"]),
            ("disabled", COLORS["disabled_text"]),
        ],
        background=[
            ("active", COLORS["hover"]),
            ("readonly", COLORS["bg_tertiary"]),
        ],
        arrowcolor=[
            ("active", COLORS["accent"]),
            ("disabled", COLORS["disabled_text"]),
        ],
        bordercolor=[("focus", COLORS["focus"])],
    )

    for orientation in ("Vertical", "Horizontal"):
        style.configure(
            f"{orientation}.TScrollbar",
            background=COLORS["bg_elevated"],
            troughcolor=COLORS["bg_primary"],
            bordercolor=COLORS["bg_primary"],
            arrowcolor=COLORS["text_secondary"],
            gripcount=0,
        )
        style.map(
            f"{orientation}.TScrollbar",
            background=[("active", COLORS["selection"])],
            arrowcolor=[("active", COLORS["text_primary"])],
        )

    for prefix in ("Custom", "Workflow"):
        tab_padding = (5, 6) if prefix == "Custom" else (12, 7)
        style.configure(
            f"{prefix}.TNotebook",
            background=COLORS["bg_primary"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            f"{prefix}.TNotebook.Tab",
            background=COLORS["bg_secondary"],
            foreground=COLORS["text_secondary"],
            borderwidth=0,
            padding=tab_padding,
            font=FONTS["label"],
        )
        style.map(
            f"{prefix}.TNotebook.Tab",
            background=[
                ("selected", COLORS["bg_elevated"]),
                ("active", COLORS["hover"]),
            ],
            foreground=[
                ("selected", COLORS["text_primary"]),
                ("active", COLORS["text_primary"]),
            ],
        )

    style.configure(
        "Workflow.Treeview",
        background=COLORS["bg_tertiary"],
        fieldbackground=COLORS["bg_tertiary"],
        foreground=COLORS["text_primary"],
        bordercolor=COLORS["border"],
        rowheight=25,
        borderwidth=0,
        font=FONTS["small"],
    )
    style.configure(
        "Workflow.Treeview.Heading",
        background=COLORS["bg_elevated"],
        foreground=COLORS["text_secondary"],
        bordercolor=COLORS["border"],
        relief="flat",
        padding=(6, 6),
        font=FONTS["label"],
    )
    style.map(
        "Workflow.Treeview",
        background=[("selected", COLORS["selection"])],
        foreground=[("selected", COLORS["text_primary"])],
    )
    style.map(
        "Workflow.Treeview.Heading",
        background=[("active", COLORS["hover"])],
        foreground=[("active", COLORS["text_primary"])],
    )


def button_options(kind: str = "secondary") -> Dict[str, object]:
    """Return consistent options for a classic ``tk.Button``."""

    variants = {
        "primary": (
            COLORS["accent"],
            COLORS["text_on_accent"],
            COLORS["accent_hover"],
            COLORS["text_on_accent"],
        ),
        "secondary": (
            COLORS["bg_elevated"],
            COLORS["text_primary"],
            COLORS["hover"],
            COLORS["text_primary"],
        ),
        "success": (
            COLORS["success"],
            COLORS["text_on_accent"],
            COLORS["success_hover"],
            COLORS["text_on_accent"],
        ),
        "danger": (
            COLORS["error"],
            COLORS["text_primary"],
            COLORS["error_hover"],
            COLORS["text_primary"],
        ),
        "ghost": (
            COLORS["bg_secondary"],
            COLORS["text_secondary"],
            COLORS["hover"],
            COLORS["text_primary"],
        ),
    }
    background, foreground, active_background, active_foreground = variants.get(
        kind, variants["secondary"]
    )
    return {
        "bg": background,
        "fg": foreground,
        "activebackground": active_background,
        "activeforeground": active_foreground,
        "disabledforeground": COLORS["disabled_text"],
        "font": FONTS["label"],
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "padx": 12,
        "pady": 7,
        "cursor": "hand2",
    }


def entry_options(*, mono: bool = False) -> Dict[str, object]:
    """Return the shared high-contrast options for classic text inputs."""

    return {
        "bg": COLORS["bg_tertiary"],
        "fg": COLORS["text_primary"],
        "insertbackground": COLORS["accent"],
        "selectbackground": COLORS["selection"],
        "selectforeground": COLORS["text_primary"],
        "disabledbackground": COLORS["disabled_bg"],
        "disabledforeground": COLORS["disabled_text"],
        "readonlybackground": COLORS["disabled_bg"],
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 1,
        "highlightbackground": COLORS["border"],
        "highlightcolor": COLORS["focus"],
        "font": FONTS["mono"] if mono else FONTS["normal"],
    }
