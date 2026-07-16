"""Runtime editor for canvas objects and optional program-variable links."""

from __future__ import annotations

import math
import tkinter as tk
import traceback
from collections.abc import Mapping
from tkinter import colorchooser, filedialog, messagebox
from tkinter.ttk import Combobox
from uuid import uuid4

from PIL import Image

from .paths import ASSETS_DIR, PROJECT_DIR
from .ui_theme import COLORS, FONTS, button_options, entry_options
from .visual_objects import (
    VISUAL_BINDABLE_PROPERTIES,
    VISUAL_OBJECT_TYPES,
    VisualObjectValidationError,
    normalize_visual_object,
    normalize_visual_object_config,
    resolve_visual_image_path,
    serialize_visual_image_path,
)


class VisualObjectEditor(tk.Toplevel):
    """Edit canvas objects and optional links to live program inputs."""

    def __init__(
        self,
        owner,
        objects,
        on_change,
        *,
        variable_provider=None,
        variable_setter=None,
    ):
        super().__init__(owner)
        self.owner = owner
        self.on_change = on_change
        self.variable_provider = variable_provider
        self.variable_setter = variable_setter
        self.objects = [dict(item) for item in objects]
        self.selected_index = None
        self._binding_catalog = {}
        self._binding_value_baseline = {}
        self._active_binding_targets = {}
        self.binding_combos = {}

        self.title("OpenSpotter | Visual Layout")
        self.geometry("1040x620")
        self.minsize(900, 560)
        self.configure(bg=COLORS["bg_primary"])
        self.transient(owner)

        self.type_var = tk.StringVar(value="rectangle")
        self.x_var = tk.StringVar(value="0")
        self.y_var = tk.StringVar(value="0")
        self.width_var = tk.StringVar(value="20")
        self.height_var = tk.StringVar(value="20")
        self.image_path_var = tk.StringVar(value="")
        self.color_var = tk.StringVar(value="#9aa7b2")
        self.text_var = tk.StringVar(value="New object")
        self.text_size_var = tk.StringVar(value="10")
        self.anchor_help_var = tk.StringVar()
        self.binding_status_var = tk.StringVar(
            value="Choose a program variable beside X, Y, width, or height to link it."
        )
        self.binding_vars = {
            property_name: tk.StringVar(value="")
            for property_name in VISUAL_BINDABLE_PROPERTIES
        }
        self.geometry_vars = {
            "x": self.x_var,
            "y": self.y_var,
            "width": self.width_var,
            "height": self.height_var,
        }
        self._geometry_dirty = set()
        self._suspend_geometry_tracking = False
        for property_name, variable in self.geometry_vars.items():
            variable.trace_add(
                "write",
                lambda *_args, name=property_name: self._geometry_value_changed(
                    name
                ),
            )

        self._build_ui()
        self.type_var.trace_add("write", lambda *_args: self._update_type_ui())
        self._update_type_ui()
        self._refresh_list()
        if self.objects:
            self.listbox.selection_set(0)
            self._select_index(0)

    def _build_ui(self):
        header = tk.Frame(self, bg=COLORS["bg_secondary"])
        header.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(
            header,
            text="VISUAL LAYOUT OBJECTS",
            font=FONTS["label"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(
            header,
            text=(
                "Unlinked properties are display only. Linked geometry follows a "
                "program input; changing it here writes back only when that input "
                "is editable. Use SAVE DEFAULTS to persist changed program inputs. "
                "All positions are millimetres from TCP (0,0)."
            ),
            font=FONTS["small"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
            justify="left",
            wraplength=980,
        ).pack(anchor="w", padx=10, pady=(0, 8))

        body = tk.Frame(self, bg=COLORS["bg_primary"])
        body.pack(fill="both", expand=True, padx=8, pady=4)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)

        list_frame = tk.Frame(body, bg=COLORS["bg_secondary"])
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame,
            exportselection=False,
            bg=COLORS["bg_tertiary"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["text_primary"],
            font=FONTS["normal"],
            relief="flat",
            bd=0,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.listbox.bind("<<ListboxSelect>>", self._on_selection)

        form = tk.Frame(body, bg=COLORS["bg_secondary"])
        form.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        form.columnconfigure(1, weight=1)

        row = 0
        self.type_combo = self._add_combobox_row(
            form,
            row,
            "Type",
            self.type_var,
            VISUAL_OBJECT_TYPES,
        )
        row += 1
        self._add_bound_entry_row(form, row, "X (mm)", "x", self.x_var)
        row += 1
        self._add_bound_entry_row(form, row, "Y (mm)", "y", self.y_var)
        row += 1
        self._add_bound_entry_row(
            form,
            row,
            "Width (mm)",
            "width",
            self.width_var,
        )
        row += 1
        self._add_bound_entry_row(
            form,
            row,
            "Height (mm)",
            "height",
            self.height_var,
        )
        row += 1

        self.image_path_label = tk.Label(
            form,
            text="Image file",
            font=FONTS["normal"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        )
        self.image_path_label.grid(
            row=row,
            column=0,
            sticky="w",
            padx=10,
            pady=5,
        )
        image_path_frame = tk.Frame(form, bg=COLORS["bg_secondary"])
        image_path_frame.grid(
            row=row,
            column=1,
            sticky="ew",
            padx=10,
            pady=5,
        )
        image_path_frame.columnconfigure(0, weight=1)
        self.image_path_entry = tk.Entry(
            image_path_frame,
            textvariable=self.image_path_var,
            **entry_options(mono=True),
        )
        self.image_path_entry.grid(row=0, column=0, sticky="ew")
        self.import_image_button = tk.Button(
            image_path_frame,
            text="IMPORT IMAGE…",
            command=self._choose_image,
            **button_options("secondary"),
        )
        self.import_image_button.grid(row=0, column=1, padx=(6, 0))
        row += 1

        tk.Label(
            form,
            text="Color / image text",
            font=FONTS["normal"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        color_frame = tk.Frame(form, bg=COLORS["bg_secondary"])
        color_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        color_frame.columnconfigure(0, weight=1)
        tk.Entry(
            color_frame,
            textvariable=self.color_var,
            **entry_options(mono=True),
        ).grid(row=0, column=0, sticky="ew")
        tk.Button(
            color_frame,
            text="Choose…",
            command=self._choose_color,
            **button_options("secondary"),
        ).grid(row=0, column=1, padx=(6, 0))
        row += 1

        self._add_entry_row(form, row, "Description", self.text_var)
        row += 1
        self._add_entry_row(form, row, "Text size", self.text_size_var)
        row += 1
        tk.Label(
            form,
            textvariable=self.binding_status_var,
            justify="left",
            wraplength=650,
            font=FONTS["small"],
            fg=COLORS["accent"],
            bg=COLORS["bg_secondary"],
        ).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=10,
            pady=(8, 2),
        )
        row += 1
        tk.Label(
            form,
            textvariable=self.anchor_help_var,
            justify="left",
            wraplength=650,
            font=FONTS["small"],
            fg=COLORS["text_secondary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 4))

        buttons = tk.Frame(self, bg=COLORS["bg_primary"])
        buttons.pack(fill="x", padx=8, pady=(4, 8))
        self._button(buttons, "ADD OBJECT", self._add_new, "secondary").pack(
            side="left", padx=(0, 4)
        )
        self._button(buttons, "APPLY CHANGES", self._apply, "primary").pack(
            side="left", padx=4
        )
        self._button(buttons, "REMOVE", self._remove, "danger").pack(
            side="left", padx=4
        )
        self._button(buttons, "CLOSE", self._close, "secondary").pack(
            side="right"
        )
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _add_entry_row(self, parent, row, label, variable):
        tk.Label(
            parent,
            text=label,
            font=FONTS["normal"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        tk.Entry(
            parent,
            textvariable=variable,
            **entry_options(mono=True),
        ).grid(row=row, column=1, sticky="ew", padx=10, pady=5)

    def _add_bound_entry_row(
        self,
        parent,
        row,
        label,
        property_name,
        variable,
    ):
        tk.Label(
            parent,
            text=label,
            font=FONTS["normal"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=row, column=0, sticky="w", padx=10, pady=5)

        value_frame = tk.Frame(parent, bg=COLORS["bg_secondary"])
        value_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        value_frame.columnconfigure(1, weight=1)
        tk.Entry(
            value_frame,
            textvariable=variable,
            width=12,
            **entry_options(mono=True),
        ).grid(row=0, column=0, sticky="ew")
        combo = Combobox(
            value_frame,
            textvariable=self.binding_vars[property_name],
            values=[""],
            state="readonly",
            font=FONTS["small"],
            width=42,
        )
        combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, name=property_name: self._binding_selected(name),
        )
        self.binding_combos[property_name] = combo

    def _add_combobox_row(self, parent, row, label, variable, values):
        tk.Label(
            parent,
            text=label,
            font=FONTS["normal"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_secondary"],
        ).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        combo = Combobox(
            parent,
            textvariable=variable,
            values=list(values),
            state="readonly",
            font=FONTS["normal"],
        )
        combo.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        return combo

    @staticmethod
    def _button(parent, text, command, kind="secondary"):
        return tk.Button(
            parent,
            text=text,
            command=command,
            **button_options(kind),
        )

    def _read_variable_catalog(self):
        provider = self.variable_provider
        if provider is None:
            return {}
        supplied = provider() if callable(provider) else provider
        if not isinstance(supplied, Mapping):
            raise VisualObjectValidationError(
                "The program-variable provider must return a mapping"
            )
        return {str(name): value for name, value in supplied.items()}

    def _geometry_value_changed(self, property_name):
        if not self._suspend_geometry_tracking:
            self._geometry_dirty.add(property_name)

    def _set_geometry_value(self, property_name, value):
        self._suspend_geometry_tracking = True
        try:
            self.geometry_vars[property_name].set(str(value))
        finally:
            self._suspend_geometry_tracking = False
        self._geometry_dirty.discard(property_name)

    @staticmethod
    def _catalog_value(metadata):
        if isinstance(metadata, Mapping):
            if metadata.get("valid") is False:
                raise VisualObjectValidationError("the program value is not valid")
            value = metadata.get("value")
        else:
            value = metadata
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise VisualObjectValidationError(
                "the program value is not numeric"
            ) from exc
        if not math.isfinite(numeric_value):
            raise VisualObjectValidationError(
                "the program value is not finite"
            )
        return numeric_value

    @classmethod
    def _catalog_item_is_numeric(cls, metadata):
        if isinstance(metadata, Mapping):
            value_type = str(metadata.get("type", "")).strip().lower()
            if value_type in ("bool", "boolean", "str", "string"):
                return False
            if value_type in ("float", "int", "integer", "number"):
                return True
            metadata = metadata.get("value")
        if isinstance(metadata, bool):
            return False
        try:
            cls._catalog_value(metadata)
        except VisualObjectValidationError:
            return False
        return True

    def _refresh_binding_catalog(self, extra_names=()):
        self._binding_catalog = self._read_variable_catalog()
        names = {
            name
            for name, metadata in self._binding_catalog.items()
            if self._catalog_item_is_numeric(metadata)
        }
        names.update(str(name) for name in extra_names if str(name).strip())
        choices = [""] + sorted(names)
        for combo in self.binding_combos.values():
            combo.configure(values=choices)

    def _sync_bound_value(self, property_name, *, announce=True):
        target_name = self.binding_vars[property_name].get().strip()
        if not target_name:
            self._binding_value_baseline.pop(property_name, None)
            if announce:
                self.binding_status_var.set(
                    f"{property_name.upper()} is not linked; its value remains visual only."
                )
            return

        metadata = self._binding_catalog.get(target_name)
        if metadata is None:
            self._binding_value_baseline.pop(property_name, None)
            self.binding_status_var.set(
                f"{property_name.upper()} references missing variable '{target_name}'. "
                "The stored visual value is used until the variable exists or the link is removed."
            )
            return
        try:
            numeric_value = self._catalog_value(metadata)
        except VisualObjectValidationError as exc:
            self._binding_value_baseline.pop(property_name, None)
            self.binding_status_var.set(
                f"{property_name.upper()} cannot read '{target_name}': {exc}. "
                "The stored visual value is being used."
            )
            return
        if property_name in ("width", "height") and numeric_value <= 0:
            self._binding_value_baseline.pop(property_name, None)
            self.binding_status_var.set(
                f"{property_name.upper()} cannot use '{target_name}' because "
                "width and height must be greater than zero. The stored visual "
                "value is being used."
            )
            return

        self._set_geometry_value(property_name, numeric_value)
        self._binding_value_baseline[property_name] = numeric_value
        if not announce:
            return

        if isinstance(metadata, Mapping):
            description = str(metadata.get("description", "")).strip()
            source = str(metadata.get("source", "")).strip()
            unit = str(metadata.get("unit", "")).strip()
            writable = metadata.get("writable", True)
        else:
            description = source = unit = ""
            writable = True
        details = " · ".join(
            part for part in (description, source, unit) if part
        )
        lock_note = (
            " Editable from this window."
            if writable
            else " Source is currently locked/read-only."
        )
        self.binding_status_var.set(
            f"{property_name.upper()} ↔ {target_name}"
            + (f" · {details}" if details else "")
            + lock_note
        )

    def _binding_selected(self, property_name):
        target_name = self.binding_vars[property_name].get().strip()
        try:
            previous_target = self._active_binding_targets.get(property_name, "")
            self._refresh_binding_catalog(
                extra_names=(target_name, previous_target)
            )
            if (
                not target_name
                and previous_target
                and property_name not in self._geometry_dirty
            ):
                metadata = self._binding_catalog.get(previous_target)
                if metadata is not None:
                    try:
                        frozen_value = self._catalog_value(metadata)
                        if (
                            property_name not in ("width", "height")
                            or frozen_value > 0
                        ):
                            self._set_geometry_value(
                                property_name,
                                frozen_value,
                            )
                    except VisualObjectValidationError:
                        pass
            self.binding_vars[property_name].set(target_name)
            if target_name:
                self._active_binding_targets[property_name] = target_name
            else:
                self._active_binding_targets.pop(property_name, None)
            self._sync_bound_value(property_name)
        except Exception as exc:
            messagebox.showerror("Visual object binding", str(exc), parent=self)

    def _update_type_ui(self):
        object_type = self.type_var.get()
        image_state = "normal" if object_type == "image" else "disabled"
        self.image_path_entry.configure(state=image_state)
        self.import_image_button.configure(state="normal")

        if object_type == "circle":
            self.anchor_help_var.set(
                "Circle X/Y is its centre point. Width and height are its two "
                "diameters; unequal values draw an oval."
            )
        elif object_type == "image":
            self.anchor_help_var.set(
                "Image X/Y is its top-left corner. Width and height are its "
                "displayed size in millimetres; the image is scaled to those "
                "exact dimensions."
            )
        else:
            self.anchor_help_var.set(
                "Rectangle X/Y is its top-left corner. Width extends right in "
                "+X and height extends down in +Y."
            )

    def _choose_image(self):
        if self.selected_index is None:
            messagebox.showinfo(
                "Import image",
                "Select an object or add a new one first.",
                parent=self,
            )
            return
        selected = filedialog.askopenfilename(
            parent=self,
            title="Choose image for visual object",
            initialdir=str(ASSETS_DIR),
            filetypes=[
                (
                    "Image files",
                    "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp",
                ),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        try:
            with Image.open(selected) as source:
                source.verify()
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Import image",
                f"Choose a readable image file.\n\n{exc}",
                parent=self,
            )
            return
        self.type_var.set("image")
        self.image_path_var.set(
            serialize_visual_image_path(
                selected,
                project_directory=PROJECT_DIR,
            )
        )

    def _choose_color(self):
        chosen = colorchooser.askcolor(
            color=self.color_var.get() or "#9aa7b2",
            parent=self,
            title="Choose object color",
        )[1]
        if chosen:
            self.color_var.set(chosen)

    def _refresh_list(self, selected_index=None):
        self.listbox.delete(0, tk.END)
        for item in self.objects:
            name = item.get("text", "").strip() or "Untitled object"
            object_type = item.get("type", "rectangle").capitalize()
            link_note = "  ·  Linked" if item.get("bindings") else ""
            self.listbox.insert(
                tk.END,
                f"{name}  ·  {object_type}{link_note}",
            )
        if selected_index is not None and 0 <= selected_index < len(self.objects):
            self.listbox.selection_set(selected_index)
            self.listbox.see(selected_index)
            self._select_index(selected_index)

    def _on_selection(self, _event=None):
        selection = self.listbox.curselection()
        if selection:
            self._select_index(selection[0])

    def _select_index(self, index):
        self.selected_index = index
        item = self.objects[index]
        self.type_var.set(str(item["type"]))
        self._geometry_dirty.clear()
        for property_name in VISUAL_BINDABLE_PROPERTIES:
            self._set_geometry_value(property_name, item[property_name])
        self.image_path_var.set(str(item.get("image_path", "")))
        self.color_var.set(str(item["color"]))
        self.text_var.set(str(item["text"]))
        self.text_size_var.set(str(item["text_size"]))
        bindings = item.get("bindings", {})
        self._binding_value_baseline.clear()
        self._active_binding_targets = {
            property_name: str(target_name)
            for property_name, target_name in bindings.items()
        }
        try:
            self._refresh_binding_catalog(extra_names=bindings.values())
        except Exception as exc:
            self._binding_catalog = {}
            self.binding_status_var.set(
                f"Program variables are unavailable: {exc}"
            )
        for property_name in VISUAL_BINDABLE_PROPERTIES:
            self.binding_vars[property_name].set(
                str(bindings.get(property_name, ""))
            )
            if self.binding_vars[property_name].get():
                self._sync_bound_value(property_name, announce=False)
        linked = [
            f"{property_name.upper()} ↔ {self.binding_vars[property_name].get()}"
            for property_name in VISUAL_BINDABLE_PROPERTIES
            if self.binding_vars[property_name].get()
        ]
        unresolved = [
            property_name.upper()
            for property_name in VISUAL_BINDABLE_PROPERTIES
            if self.binding_vars[property_name].get()
            and property_name not in self._binding_value_baseline
        ]
        if unresolved:
            self.binding_status_var.set(
                "Linked source unavailable or invalid for "
                + ", ".join(unresolved)
                + "; stored visual fallback values are active."
            )
        elif linked:
            self.binding_status_var.set(
                "Linked: "
                + ", ".join(linked)
                + ". Program values drive the canvas; edit a value and Apply to write back."
            )
        else:
            self.binding_status_var.set(
                "No geometry links. X, Y, width, and height are visual-only values."
            )

    def _draft(self, object_id):
        object_type = self.type_var.get()
        color = self.color_var.get().strip()
        try:
            self.winfo_rgb(color)
        except tk.TclError as exc:
            raise VisualObjectValidationError(
                f"'{color}' is not a color understood by Tkinter"
            ) from exc
        image_path = self.image_path_var.get().strip()
        if object_type == "image":
            if not image_path:
                raise VisualObjectValidationError(
                    "Choose an image file for image objects."
                )
            resolved_image = resolve_visual_image_path(
                image_path,
                project_directory=PROJECT_DIR,
            )
            if not resolved_image.is_file():
                raise VisualObjectValidationError(
                    f"Image file does not exist: {resolved_image}"
                )
            try:
                with Image.open(resolved_image) as source:
                    source.verify()
            except (OSError, ValueError) as exc:
                raise VisualObjectValidationError(
                    f"Choose a readable image file: {resolved_image}"
                ) from exc
            image_path = serialize_visual_image_path(
                resolved_image,
                project_directory=PROJECT_DIR,
            )
        return normalize_visual_object(
            {
                "id": object_id,
                "type": object_type,
                "x": self.x_var.get(),
                "y": self.y_var.get(),
                "width": self.width_var.get(),
                "height": self.height_var.get(),
                "image_path": image_path,
                "color": color,
                "text": self.text_var.get(),
                "text_size": self.text_size_var.get(),
                "bindings": {
                    property_name: self.binding_vars[property_name].get().strip()
                    for property_name in VISUAL_BINDABLE_PROPERTIES
                    if self.binding_vars[property_name].get().strip()
                },
            },
            fallback_id=object_id,
        )

    @staticmethod
    def _same_number(left, right):
        return math.isclose(
            float(left),
            float(right),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )

    def _prepare_binding_updates(self, draft):
        """Adopt live source changes and collect intentional reverse writes."""
        catalog = self._read_variable_catalog()
        self._binding_catalog = catalog
        groups = {}

        for property_name, target_name in draft.get("bindings", {}).items():
            metadata = catalog.get(target_name)
            if metadata is None:
                continue
            try:
                current_value = self._catalog_value(metadata)
            except VisualObjectValidationError:
                continue
            group = groups.setdefault(
                target_name,
                {
                    "current": current_value,
                    "metadata": metadata,
                    "properties": [],
                },
            )
            group["properties"].append(
                {
                    "name": property_name,
                    "local": float(draft[property_name]),
                    "dirty": property_name in self._geometry_dirty,
                }
            )

        updates = {}
        current_by_target = {}
        for target_name, group in groups.items():
            current_value = group["current"]
            current_by_target[target_name] = current_value
            dirty_values = [
                item["local"]
                for item in group["properties"]
                if item["dirty"]
            ]
            if dirty_values:
                desired_value = dirty_values[0]
                if any(
                    not self._same_number(desired_value, other_value)
                    for other_value in dirty_values[1:]
                ):
                    raise VisualObjectValidationError(
                        f"Properties linked to '{target_name}' must use the same value"
                    )
            else:
                desired_value = current_value

            for item in group["properties"]:
                property_name = item["name"]
                if (
                    property_name in ("width", "height")
                    and desired_value <= 0
                ):
                    continue
                draft[property_name] = desired_value

            if self._same_number(desired_value, current_value):
                continue
            metadata = group["metadata"]
            writable = (
                metadata.get("writable", True)
                if isinstance(metadata, Mapping)
                else True
            )
            if not writable:
                if target_name.startswith("global."):
                    raise VisualObjectValidationError(
                        f"'{target_name}' is locked. Unlock GLOBAL MACHINE "
                        "PARAMETERS before changing this linked value."
                    )
                raise VisualObjectValidationError(
                    f"Linked program variable '{target_name}' is read-only"
                )
            updates[target_name] = desired_value
        return updates, current_by_target

    def _write_binding_updates(self, updates):
        if updates and not callable(self.variable_setter):
            raise VisualObjectValidationError(
                "This window cannot write linked program variables"
            )
        applied = []
        canonical = {}
        for target_name, desired_value in updates.items():
            result = self.variable_setter(target_name, desired_value)
            canonical[target_name] = (
                desired_value if result is None else float(result)
            )
            applied.append(target_name)
        return canonical, applied

    def _rollback_binding_updates(self, applied, previous_values):
        if not callable(self.variable_setter):
            return
        for target_name in reversed(applied):
            if target_name not in previous_values:
                continue
            try:
                self.variable_setter(
                    target_name,
                    previous_values[target_name],
                )
            except Exception:
                pass

    def _publish(self, selected_index=None):
        normalized = normalize_visual_object_config({"objects": self.objects})
        self.on_change(normalized["objects"])
        self.objects = [dict(item) for item in normalized["objects"]]
        try:
            self._refresh_list(selected_index)
        except Exception:
            traceback.print_exc()

    def _add_new(self):
        new_object = {
            "id": f"visual-{uuid4().hex}",
            "type": "rectangle",
            "x": 0.0,
            "y": 0.0,
            "width": 20.0,
            "height": 20.0,
            "color": "#9aa7b2",
            "text": f"Object {len(self.objects) + 1}",
            "text_size": 10,
        }
        self.objects.append(new_object)
        try:
            self._publish(len(self.objects) - 1)
        except Exception as exc:
            self.objects.pop()
            messagebox.showerror("Visual object", str(exc), parent=self)

    def _apply(self):
        if self.selected_index is None:
            messagebox.showinfo(
                "Visual object",
                "Select an object or add a new one first.",
                parent=self,
            )
            return
        previous = dict(self.objects[self.selected_index])
        applied_targets = []
        previous_values = {}
        try:
            current_id = self.objects[self.selected_index]["id"]
            draft = self._draft(current_id)
            updates, previous_values = self._prepare_binding_updates(draft)
            canonical_values, applied_targets = self._write_binding_updates(updates)
            for property_name, target_name in draft.get("bindings", {}).items():
                if target_name in canonical_values:
                    draft[property_name] = canonical_values[target_name]
            self.objects[self.selected_index] = normalize_visual_object(
                draft,
                fallback_id=current_id,
            )
            self._publish(self.selected_index)
        except Exception as exc:
            self._rollback_binding_updates(applied_targets, previous_values)
            self.objects[self.selected_index] = previous
            messagebox.showerror("Visual object", str(exc), parent=self)

    def _remove(self):
        if self.selected_index is None:
            return
        item = self.objects[self.selected_index]
        label = item.get("text", "").strip() or "this object"
        if not messagebox.askyesno(
            "Remove visual object",
            f"Remove '{label}' from the canvas?",
            parent=self,
        ):
            return
        removed_index = self.selected_index
        removed = self.objects.pop(removed_index)
        self.selected_index = None
        try:
            next_index = min(removed_index, len(self.objects) - 1)
            self._publish(next_index if next_index >= 0 else None)
        except Exception as exc:
            self.objects.insert(removed_index, removed)
            messagebox.showerror("Visual object", str(exc), parent=self)

    def _close(self):
        if getattr(self.owner, "_visual_object_editor", None) is self:
            self.owner._visual_object_editor = None
        self.destroy()


def open_visual_object_editor(
    owner,
    objects,
    on_change,
    *,
    variable_provider=None,
    variable_setter=None,
):
    """Open one editor per main application window."""
    existing = getattr(owner, "_visual_object_editor", None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return existing

    editor = VisualObjectEditor(
        owner,
        objects,
        on_change,
        variable_provider=variable_provider,
        variable_setter=variable_setter,
    )
    owner._visual_object_editor = editor

    return editor
