"""Tk renderer for plugin-owned pattern previews and visual layout objects.

Pattern plugins provide immutable primitives from :mod:`app.core.canvas`.
This module owns only viewport transforms, theme-aware rendering, visual
objects, and the live toolhead overlay.
"""

import math
import tkinter as tk
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageOps, ImageTk
from .core.canvas import (
    CanvasPreview,
    CanvasPreviewContext,
    CanvasPreviewProvider,
    CanvasPreviewStyle,
    MarkerPrimitive,
    PreviewBounds,
)
from .core.configuration import entries_to_dict
from .input_configs import GLOBAL_FIELDS
from .paths import PROJECT_DIR, WORKFLOW_CONFIG
from .plugin_runtime import application_plugins
from .ui_theme import COLORS, FONTS, button_options
from .visual_objects import (
    resolve_visual_object_bindings,
    resolve_visual_image_path,
    visual_object_bounds,
    visual_object_center,
)

LIVE_TOOLHEAD_TAG = "live_toolhead"


def visual_object_shape_options(object_type, fill_color):
    """Return an opaque fill for every editable rectangle or circle."""
    if object_type not in ("rectangle", "circle"):
        raise ValueError(f"Unsupported visual object type '{object_type}'")
    return {
        'fill': str(fill_color),
        'outline': COLORS['plot_outline'],
        'width': 2,
    }


def load_scaled_visual_image(
    image_path,
    pixel_width,
    pixel_height,
    *,
    project_directory=PROJECT_DIR,
):
    """Load one visual-object image at its exact canvas dimensions."""
    resolved_path = resolve_visual_image_path(
        image_path,
        project_directory=project_directory,
    )
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Image file not found: {resolved_path}")
    target_size = (
        max(1, int(round(pixel_width))),
        max(1, int(round(pixel_height))),
    )
    with Image.open(resolved_path) as source:
        return ImageOps.exif_transpose(source).convert("RGBA").resize(
            target_size,
            Image.Resampling.LANCZOS,
        )


def visual_image_cache_key(
    image_path,
    pixel_width,
    pixel_height,
    *,
    project_directory=PROJECT_DIR,
):
    """Return a cache key that changes with the source file or target size."""
    resolved_path = resolve_visual_image_path(
        image_path,
        project_directory=project_directory,
    )
    source_stat = resolved_path.stat()
    return (
        str(resolved_path),
        source_stat.st_mtime_ns,
        source_stat.st_size,
        max(1, int(round(pixel_width))),
        max(1, int(round(pixel_height))),
    )


def resolve_canvas_visual_objects(objects, variable_catalog):
    """Resolve live bindings without allowing one bad object to break the preview."""
    resolved_objects = []
    warnings = []
    for item in objects:
        fallback = dict(item)
        try:
            resolved, item_warnings = resolve_visual_object_bindings(
                fallback,
                variable_catalog,
            )
            if not isinstance(resolved, Mapping):
                raise TypeError("visual binding resolver must return an object mapping")
            resolved_objects.append(dict(resolved))
            if isinstance(item_warnings, str):
                warnings.append(item_warnings)
            else:
                warnings.extend(str(warning) for warning in (item_warnings or ()))
        except Exception as exc:
            resolved_objects.append(fallback)
            object_id = fallback.get("id", "visual object")
            warnings.append(f"{object_id}: {exc}")
    return resolved_objects, warnings


def world_to_canvas_point(
    world_x,
    world_y,
    *,
    origin_x,
    origin_y,
    scale,
    pan_x,
    pan_y,
):
    """Map positive-right/positive-down machine coordinates to the canvas."""
    return (
        (world_x - origin_x) * scale + pan_x,
        (world_y - origin_y) * scale + pan_y,
    )


def canvas_to_world_point(
    canvas_x,
    canvas_y,
    *,
    origin_x,
    origin_y,
    scale,
    pan_x,
    pan_y,
):
    """Invert the positive-down machine-to-canvas transform."""
    return (
        (canvas_x - pan_x) / scale + origin_x,
        (canvas_y - pan_y) / scale + origin_y,
    )


def normalize_live_toolhead_position(position, homed_axes):
    """Return a finite XYZ tuple only when machine X/Y coordinates are valid."""
    axes = set(str(homed_axes or "").strip().lower())
    if not {"x", "y"} <= axes:
        return None
    if not isinstance(position, (tuple, list)) or len(position) < 3:
        return None
    try:
        coordinates = tuple(float(value) for value in position[:3])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in coordinates):
        return None
    return coordinates


class CanvasDrawer:
    def __init__(self, gui, poll_interval=500):
        self.gui = gui
        self.canvas = gui.canvas
        self.poll_interval = poll_interval
        self._prev_snapshot = None
        self._last_exceed_state = False
        self._zoom_factor = 1.0
        self._pan_x = None
        self._pan_y = None
        self._fit_scale = 1.0
        self._origin_x = 0.0
        self._origin_y = 0.0
        self._drag_start = None
        self._resize_after_id = None
        self._poll_after_id = None
        self._visual_image_cache = {}
        self._toolhead_position = None
        self._toolhead_homed_axes = ""
        self._toolhead_item_ids = ()
        self._transform_ready = False
        self._canvas_width = 0
        self._canvas_height = 0

    def set_toolhead_position(self, position, homed_axes=""):
        """Update the non-editable live toolhead overlay without redrawing geometry."""
        normalized_axes = "".join(
            axis
            for axis in "xyz"
            if axis in set(str(homed_axes or "").strip().lower())
        )
        normalized_position = normalize_live_toolhead_position(
            position,
            normalized_axes,
        )
        next_state = (normalized_position, normalized_axes)
        current_state = (
            self._toolhead_position,
            self._toolhead_homed_axes,
        )
        if next_state == current_state:
            return False
        self._toolhead_position = normalized_position
        self._toolhead_homed_axes = normalized_axes
        self._render_live_toolhead()
        return True

    def _clear_live_toolhead(self):
        try:
            self.canvas.delete(LIVE_TOOLHEAD_TAG)
        except (AttributeError, tk.TclError):
            pass
        self._toolhead_item_ids = ()

    def _render_live_toolhead(self):
        position = self._toolhead_position
        if position is None or not self._transform_ready:
            self._clear_live_toolhead()
            return
        scale = self._fit_scale * self._zoom_factor
        if (
            scale <= 0
            or self._pan_x is None
            or self._pan_y is None
        ):
            return
        x, y, z = position
        px, py = world_to_canvas_point(
            x,
            y,
            origin_x=self._origin_x,
            origin_y=self._origin_y,
            scale=scale,
            pan_x=self._pan_x,
            pan_y=self._pan_y,
        )
        marker_radius = 10
        marker_color = COLORS["warning"]
        tags = (LIVE_TOOLHEAD_TAG,)
        horizontal_anchor = "w" if px <= self._canvas_width * 0.65 else "e"
        vertical_anchor = "s" if py >= 34 else "n"
        label_x = px + 15 if horizontal_anchor == "w" else px - 15
        label_y = py - 13 if vertical_anchor == "s" else py + 13
        z_text = f"{z:.3f}" if "z" in self._toolhead_homed_axes else "---"
        label = (
            "LIVE REQUESTED TOOLHEAD\n"
            f"X {x:.3f}   Y {y:.3f}   Z {z_text}"
        )
        if len(self._toolhead_item_ids) == 5:
            ring, diagonal_down, diagonal_up, center, text = (
                self._toolhead_item_ids
            )
            try:
                self.canvas.coords(
                    ring,
                    px - marker_radius,
                    py - marker_radius,
                    px + marker_radius,
                    py + marker_radius,
                )
                self.canvas.coords(
                    diagonal_down,
                    px - marker_radius - 3,
                    py - marker_radius - 3,
                    px + marker_radius + 3,
                    py + marker_radius + 3,
                )
                self.canvas.coords(
                    diagonal_up,
                    px - marker_radius - 3,
                    py + marker_radius + 3,
                    px + marker_radius + 3,
                    py - marker_radius - 3,
                )
                self.canvas.coords(
                    center,
                    px - 2,
                    py - 2,
                    px + 2,
                    py + 2,
                )
                self.canvas.coords(text, label_x, label_y)
                self.canvas.itemconfigure(
                    text,
                    text=label,
                    anchor=f"{vertical_anchor}{horizontal_anchor}",
                    justify=(
                        "left" if horizontal_anchor == "w" else "right"
                    ),
                )
                self.canvas.tag_raise(LIVE_TOOLHEAD_TAG)
                return
            except (AttributeError, tk.TclError):
                self._clear_live_toolhead()
        try:
            self._toolhead_item_ids = (
                self.canvas.create_oval(
                    px - marker_radius,
                    py - marker_radius,
                    px + marker_radius,
                    py + marker_radius,
                    fill="",
                    outline=marker_color,
                    width=2,
                    dash=(3, 2),
                    tags=tags,
                ),
                self.canvas.create_line(
                    px - marker_radius - 3,
                    py - marker_radius - 3,
                    px + marker_radius + 3,
                    py + marker_radius + 3,
                    fill=marker_color,
                    width=3,
                    tags=tags,
                ),
                self.canvas.create_line(
                    px - marker_radius - 3,
                    py + marker_radius + 3,
                    px + marker_radius + 3,
                    py - marker_radius - 3,
                    fill=marker_color,
                    width=3,
                    tags=tags,
                ),
                self.canvas.create_oval(
                    px - 2,
                    py - 2,
                    px + 2,
                    py + 2,
                    fill=marker_color,
                    outline=COLORS["canvas"],
                    width=1,
                    tags=tags,
                ),
                self.canvas.create_text(
                    label_x,
                    label_y,
                    text=label,
                    anchor=f"{vertical_anchor}{horizontal_anchor}",
                    justify="left" if horizontal_anchor == "w" else "right",
                    fill=marker_color,
                    font=FONTS["mono_small"],
                    tags=tags,
                ),
            )
            self.canvas.tag_raise(LIVE_TOOLHEAD_TAG)
        except (AttributeError, tk.TclError):
            self._toolhead_item_ids = ()

    def _visual_photo_image(self, item, pixel_width, pixel_height):
        object_id = str(item["id"])
        cache_key = visual_image_cache_key(
            item["image_path"],
            pixel_width,
            pixel_height,
        )
        cached = self._visual_image_cache.get(object_id)
        if cached is not None and cached[0] == cache_key:
            return cached[1]

        rendered_image = load_scaled_visual_image(
            item["image_path"],
            pixel_width,
            pixel_height,
        )
        photo_image = ImageTk.PhotoImage(
            rendered_image,
            master=self.canvas,
        )
        self._visual_image_cache[object_id] = (cache_key, photo_image)
        return photo_image

    def start(self):
        self._schedule_poll()
        try:
            self.canvas.bind("<MouseWheel>", self._on_mousewheel)
            self.canvas.bind("<Button-1>", self._on_pan_start)
            self.canvas.bind("<B1-Motion>", self._on_pan_move)
            self.canvas.bind("<Configure>", self._on_canvas_resize)
        except Exception:
            pass

    def refresh(self):
        snapshot = self._collect_data()
        self._prev_snapshot = snapshot
        self.draw(snapshot)

    def invalidate(self):
        """Force a redraw after non-entry configuration changes."""
        self._prev_snapshot = None
        self.refresh()

    def request_redraw(self):
        """Redraw immediately without creating another recurring poll chain."""
        self.refresh()

    def reset_view(self):
        """Fit all current content after a layout change."""
        self._zoom_factor = 1.0
        self._pan_x = None
        self._pan_y = None
        self.invalidate()

    def _on_canvas_resize(self, _event=None):
        """Debounce resize redraws so fitted geometry follows the viewport."""
        if self._resize_after_id is not None:
            try:
                self.gui.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.gui.after(80, self._finish_canvas_resize)

    def _finish_canvas_resize(self):
        self._resize_after_id = None
        self._pan_x = None
        self._pan_y = None
        self.refresh()

    def _schedule_poll(self):
        if self._poll_after_id is not None:
            return
        try:
            self._poll_after_id = self.gui.after(self.poll_interval, self._poll)
        except tk.TclError:
            self._poll_after_id = None

    def _poll(self):
        pending_after_id = self._poll_after_id
        self._poll_after_id = None
        if pending_after_id is not None:
            try:
                self.gui.after_cancel(pending_after_id)
            except tk.TclError:
                pass

        try:
            snapshot = self._collect_data()
            if snapshot != self._prev_snapshot:
                self._prev_snapshot = snapshot
                self.draw(snapshot)
        finally:
            self._schedule_poll()

    def _collect_data(self):
        global_vals = entries_to_dict(self.gui.entry, GLOBAL_FIELDS)
        config_dir = Path(
            getattr(self.gui, "config_dir", WORKFLOW_CONFIG.parent)
        )
        workflow_source = getattr(self.gui, "workflow_data", None)
        if workflow_source is None:
            workflow_source = config_dir / WORKFLOW_CONFIG.name
        preview_context = CanvasPreviewContext(
            global_values=global_vals,
            config_dir=config_dir,
            workflow_source=workflow_source,
            style=CanvasPreviewStyle(
                maintenance_primary=COLORS["warning"],
                maintenance_secondary=COLORS["text_muted"],
                maintenance_primary_outline=COLORS["canvas"],
                maintenance_secondary_outline=COLORS["border_strong"],
                washing_line=COLORS["axis_y"],
            ),
        )
        pattern_previews = []
        preview_warnings = []
        plugins = getattr(self.gui, "pattern_plugins", None)
        if plugins is None:
            plugins = application_plugins()
        for plugin in plugins:
            if not isinstance(plugin, CanvasPreviewProvider):
                continue
            try:
                preview = plugin.build_canvas_preview(
                    self.gui,
                    preview_context,
                )
                if not isinstance(preview, CanvasPreview):
                    raise TypeError(
                        "preview hook must return CanvasPreview"
                    )
                pattern_previews.append(preview)
            except Exception as exc:
                plugin_id = getattr(
                    getattr(plugin, "manifest", None),
                    "id",
                    type(plugin).__name__,
                )
                preview_warnings.append(
                    "{} preview is unavailable: {}".format(
                        plugin_id,
                        exc,
                    )
                )
        pattern_preview = CanvasPreview.combine(pattern_previews)
        preview_warnings.extend(pattern_preview.warnings)

        visual_binding_catalog = {}
        visual_binding_warnings = []
        variable_provider = getattr(
            self.gui,
            "_visual_binding_variable_provider",
            None,
        )
        if callable(variable_provider):
            try:
                provided_variables = variable_provider()
                if not isinstance(provided_variables, Mapping):
                    raise TypeError(
                        "visual binding variable provider must return a mapping"
                    )
                visual_binding_catalog = dict(provided_variables)
            except Exception as exc:
                visual_binding_warnings.append(
                    f"Visual binding variables are unavailable: {exc}"
                )

        visual_objects, resolution_warnings = resolve_canvas_visual_objects(
            (
                dict(item)
                for item in getattr(self.gui, 'visual_objects', [])
            ),
            visual_binding_catalog,
        )
        visual_binding_warnings.extend(resolution_warnings)

        return {
            'global': global_vals,
            'pattern_preview': pattern_preview,
            'pattern_preview_warnings': tuple(preview_warnings),
            'visual_objects': visual_objects,
            'visual_binding_warnings': tuple(visual_binding_warnings),
        }

    def draw(self, snapshot):
        self.canvas.delete('all')
        self._toolhead_item_ids = ()
        self._transform_ready = False
        if snapshot is None:
            self._visual_image_cache.clear()
            return

        global_vals = snapshot.get('global', {})
        pattern_preview = snapshot.get(
            'pattern_preview',
            CanvasPreview.empty(),
        )
        if not isinstance(pattern_preview, CanvasPreview):
            pattern_preview = CanvasPreview.empty()
        visual_objects = snapshot.get('visual_objects', [])

        if not global_vals:
            self._visual_image_cache.clear()
            return

        # Base and offsets
        x_abs = float(global_vals.get('x_cord_of_y_line', 0))
        y_abs = float(global_vals.get('y_cord_of_x_line', 0))
        rect_w = float(global_vals.get('base_square_x', 0))
        rect_h = float(global_vals.get('base_square_y', 0))
        inner_w = float(global_vals.get('acceptance_square_x', 0))
        inner_h = float(global_vals.get('acceptance_square_y', 0))

        # --- Inner acceptance rectangle centered in the build plate ---
        inner_x1 = x_abs + (rect_w - inner_w) / 2
        inner_y1 = y_abs + (rect_h - inner_h) / 2
        inner_x2 = inner_x1 + inner_w
        inner_y2 = inner_y1 + inner_h

        # --- Determine world bounds around TCP (0,0) and visible content ---
        xs = [0.0]
        ys = [0.0]
        preview_points = pattern_preview.all_points()
        xs.extend(point[0] for point in preview_points)
        ys.extend(point[1] for point in preview_points)
        for item in visual_objects:
            try:
                left, bottom, right, top = visual_object_bounds(item)
                xs.extend((left, right))
                ys.extend((bottom, top))
            except (KeyError, TypeError, ValueError):
                continue

        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        def _canvas_dimension(axis, fallback):
            measured = self.canvas.winfo_width() if axis == 'width' else self.canvas.winfo_height()
            if measured <= 1:
                try:
                    measured = int(float(self.canvas.cget(axis)))
                except (TypeError, ValueError, tk.TclError):
                    measured = fallback
            return max(2, measured)

        c_w = _canvas_dimension('width', 800)
        c_h = _canvas_dimension('height', 500)
        screen_padding = 54
        range_x = max(maxx - minx, 1.0)
        range_y = max(maxy - miny, 1.0)
        available_width = max(1, c_w - 2 * screen_padding)
        available_height = max(1, c_h - 2 * screen_padding)
        self._fit_scale = min(available_width / range_x, available_height / range_y)
        self._origin_x, self._origin_y = minx, miny
        if self._pan_x is None:
            self._pan_x = (c_w - range_x * self._fit_scale) / 2
        if self._pan_y is None:
            self._pan_y = (c_h - range_y * self._fit_scale) / 2
        effective_scale = self._fit_scale * self._zoom_factor
        self._canvas_width = c_w
        self._canvas_height = c_h
        self._transform_ready = True

        def world_to_canvas(wx, wy):
            return world_to_canvas_point(
                wx,
                wy,
                origin_x=self._origin_x,
                origin_y=self._origin_y,
                scale=effective_scale,
                pan_x=self._pan_x,
                pan_y=self._pan_y,
            )

        def canvas_to_world(px, py):
            return canvas_to_world_point(
                px,
                py,
                origin_x=self._origin_x,
                origin_y=self._origin_y,
                scale=effective_scale,
                pan_x=self._pan_x,
                pan_y=self._pan_y,
            )

        # Every preview-capable plugin participates in the same safety check.
        exceed = pattern_preview.extends_outside(
            PreviewBounds(
                x_min=inner_x1,
                y_min=inner_y1,
                x_max=inner_x2,
                y_max=inner_y2,
            )
        )
        if exceed and not getattr(self, '_last_exceed_state', False):
            self._show_exceed_popup()
        self._last_exceed_state = exceed

        # --- Background ---
        self.canvas.create_rectangle(
            0,
            0,
            c_w,
            c_h,
            fill=COLORS['canvas'],
            outline='',
        )

        # --- Millimetre grid and axes, always referenced to the TCP cross ---
        visible_left, visible_top = canvas_to_world(0, 0)
        visible_right, visible_bottom = canvas_to_world(c_w, c_h)
        world_left, world_right = sorted((visible_left, visible_right))
        world_bottom, world_top = sorted((visible_bottom, visible_top))

        def _nice_grid_step(target_world_units):
            if target_world_units <= 0:
                return 10.0
            exponent = math.floor(math.log10(target_world_units))
            fraction = target_world_units / (10 ** exponent)
            if fraction <= 1:
                nice_fraction = 1
            elif fraction <= 2:
                nice_fraction = 2
            elif fraction <= 5:
                nice_fraction = 5
            else:
                nice_fraction = 10
            return nice_fraction * (10 ** exponent)

        grid_step = _nice_grid_step(72.0 / max(effective_scale, 1e-9))
        minor_step = grid_step / 5.0
        first_grid_x = math.ceil(world_left / grid_step) * grid_step
        first_grid_y = math.ceil(world_bottom / grid_step) * grid_step
        coordinate_color = COLORS['text_muted']

        value = math.ceil(world_left / minor_step) * minor_step
        while value <= world_right + minor_step * 1e-9:
            px, _py = world_to_canvas(value, 0)
            self.canvas.create_line(
                px, 0, px, c_h, fill=COLORS['grid_minor'], width=1
            )
            value += minor_step
        value = math.ceil(world_bottom / minor_step) * minor_step
        while value <= world_top + minor_step * 1e-9:
            _px, py = world_to_canvas(0, value)
            self.canvas.create_line(
                0, py, c_w, py, fill=COLORS['grid_minor'], width=1
            )
            value += minor_step

        value = first_grid_x
        while value <= world_right + grid_step * 1e-9:
            px, _py = world_to_canvas(value, 0)
            self.canvas.create_line(px, 0, px, c_h, fill=COLORS['grid_major'], width=1)
            if abs(value) > grid_step * 1e-9:
                self.canvas.create_text(
                    px + 3,
                    c_h - 3,
                    text=f"{value:g}",
                    anchor='sw',
                    fill=coordinate_color,
                    font=FONTS['caption'],
                )
            value += grid_step
        value = first_grid_y
        while value <= world_top + grid_step * 1e-9:
            _px, py = world_to_canvas(0, value)
            self.canvas.create_line(0, py, c_w, py, fill=COLORS['grid_major'], width=1)
            if abs(value) > grid_step * 1e-9:
                self.canvas.create_text(
                    3,
                    py - 3,
                    text=f"{value:g}",
                    anchor='sw',
                    fill=coordinate_color,
                    font=FONTS['caption'],
                )
            value += grid_step

        axis_left, axis_y = world_to_canvas(world_left, 0)
        axis_right, _axis_y = world_to_canvas(world_right, 0)
        axis_x, axis_y_min = world_to_canvas(0, world_bottom)
        _axis_x, axis_y_max = world_to_canvas(0, world_top)
        axis_tags = ('coordinate_axis',)
        self.canvas.create_line(
            axis_left, axis_y, axis_right, axis_y,
            fill=COLORS['axis'], width=2, arrow=tk.LAST, tags=axis_tags,
        )
        self.canvas.create_line(
            axis_x, axis_y_min, axis_x, axis_y_max,
            fill=COLORS['axis'], width=2, arrow=tk.LAST, tags=axis_tags,
        )
        self.canvas.create_text(
            min(c_w - 4, axis_right - 4), axis_y - 5,
            text='X / mm', anchor='se', fill=COLORS['axis'],
            font=FONTS['label'], tags=axis_tags,
        )
        self.canvas.create_text(
            axis_x + 5, min(c_h - 4, axis_y_max - 4),
            text='Y / mm', anchor='sw', fill=COLORS['axis'],
            font=FONTS['label'], tags=axis_tags,
        )

        # --- User-managed display objects ---
        def _contrasting_text_color(fill_color):
            try:
                red, green, blue = self.canvas.winfo_rgb(fill_color)
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                return COLORS['text_on_accent'] if luminance > 32768 else COLORS['text_primary']
            except tk.TclError:
                return COLORS['text_primary']

        live_image_ids = set()
        for item in visual_objects:
            try:
                object_type = item["type"]
                fill_color = str(item["color"])
                left, y_min, right, y_max = visual_object_bounds(item)
                center_x, center_y = visual_object_center(item)
                left_px, top_px = world_to_canvas(left, y_min)
                right_px, bottom_px = world_to_canvas(right, y_max)
                if object_type == "image":
                    object_id = str(item["id"])
                    live_image_ids.add(object_id)
                    pixel_width = abs(right_px - left_px)
                    pixel_height = abs(bottom_px - top_px)
                    try:
                        photo_image = self._visual_photo_image(
                            item,
                            pixel_width,
                            pixel_height,
                        )
                        self.canvas.create_image(
                            left_px,
                            top_px,
                            image=photo_image,
                            anchor=tk.NW,
                        )
                        image_outline = COLORS['plot_outline']
                        image_dash = None
                    except (OSError, ValueError, tk.TclError):
                        self._visual_image_cache.pop(object_id, None)
                        image_outline = COLORS['error']
                        image_dash = (4, 3)
                    self.canvas.create_rectangle(
                        left_px,
                        top_px,
                        right_px,
                        bottom_px,
                        fill='',
                        outline=image_outline,
                        width=1,
                        dash=image_dash,
                    )
                    if image_dash:
                        self.canvas.create_line(
                            left_px,
                            top_px,
                            right_px,
                            bottom_px,
                            fill=COLORS['error'],
                            width=1,
                        )
                        self.canvas.create_line(
                            left_px,
                            bottom_px,
                            right_px,
                            top_px,
                            fill=COLORS['error'],
                            width=1,
                        )
                else:
                    draw_shape = (
                        self.canvas.create_oval
                        if object_type == "circle"
                        else self.canvas.create_rectangle
                    )
                    draw_shape(
                        left_px,
                        top_px,
                        right_px,
                        bottom_px,
                        **visual_object_shape_options(object_type, fill_color),
                    )
                center_px, center_py = world_to_canvas(center_x, center_y)
                self.canvas.create_text(
                    center_px,
                    center_py,
                    text=str(item.get("text", "")),
                    fill=(
                        fill_color
                        if object_type == "image"
                        else _contrasting_text_color(fill_color)
                    ),
                    justify='center',
                    font=("Segoe UI Semibold", int(item.get("text_size", 10))),
                )
            except (KeyError, TypeError, ValueError, tk.TclError):
                continue
        self._visual_image_cache = {
            object_id: cached
            for object_id, cached in self._visual_image_cache.items()
            if object_id in live_image_ids
        }

        # --- Map dispense volume to diameter ---
        try:
            v1 = float(getattr(self.gui, 'disp_v1_entry').get())
            d1 = float(getattr(self.gui, 'disp_d1_entry').get())
            v2 = float(getattr(self.gui, 'disp_v2_entry').get())
            d2 = float(getattr(self.gui, 'disp_d2_entry').get())
            m = (d2 - d1) / (v2 - v1) if abs(v2 - v1) > 1e-9 else 0
            b = d1 - m * v1
        except Exception:
            m, b = 0, 0.6

        def _series_outline(series_color):
            try:
                red, green, blue = self.canvas.winfo_rgb(series_color)
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                return (
                    COLORS['text_secondary']
                    if luminance < 18500
                    else COLORS['canvas']
                )
            except tk.TclError:
                return COLORS['text_secondary']

        def _marker_radius(volume_ul, size_mm, minimum_pixels):
            diameter_mm = (
                max(0.0, m * float(volume_ul) + b)
                if volume_ul is not None
                else max(0.0, float(size_mm))
            )
            return min(
                max(
                    int(minimum_pixels),
                    int((diameter_mm / 2.0) * effective_scale),
                ),
                80,
            )

        def _draw_marker(marker):
            px, py = world_to_canvas(marker.x, marker.y)
            radius = _marker_radius(
                marker.volume_ul,
                marker.size_mm,
                marker.minimum_pixels,
            )
            draw_shape = (
                self.canvas.create_rectangle
                if marker.shape == "square"
                else self.canvas.create_oval
            )
            draw_shape(
                px - radius,
                py - radius,
                px + radius,
                py + radius,
                fill=marker.color,
                outline=marker.outline or _series_outline(marker.color),
                width=1,
            )

        # Render plugin layers in a stable order without knowing their type or
        # identity. A future plugin only needs to return core primitives.
        layers = []
        layers.extend(
            (marker.z_index, 0, index, "marker", marker)
            for index, marker in enumerate(pattern_preview.markers)
        )
        layers.extend(
            (polyline.z_index, 1, index, "polyline", polyline)
            for index, polyline in enumerate(pattern_preview.polylines)
        )
        layers.extend(
            (line.z_index, 2, index, "line", line)
            for index, line in enumerate(pattern_preview.lines)
        )
        for _z_index, _kind_order, _index, kind, primitive in sorted(
            layers
        ):
            if kind == "marker":
                _draw_marker(primitive)
                continue
            if kind == "line":
                start_x, start_y = world_to_canvas(*primitive.start)
                end_x, end_y = world_to_canvas(*primitive.end)
                options = {
                    "fill": primitive.color,
                    "width": primitive.width,
                }
                if primitive.dash:
                    options["dash"] = primitive.dash
                self.canvas.create_line(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    **options,
                )
                continue

            pixel_points = [
                world_to_canvas(x, y)
                for x, y in primitive.points
            ]
            if len(pixel_points) >= 2:
                coordinates = [
                    coordinate
                    for point in pixel_points
                    for coordinate in point
                ]
                self.canvas.create_line(
                    *coordinates,
                    fill=(
                        primitive.outline
                        or _series_outline(primitive.color)
                    ),
                    width=primitive.width + 2,
                )
                self.canvas.create_line(
                    *coordinates,
                    fill=primitive.color,
                    width=primitive.width,
                )
            if primitive.show_markers:
                for x, y in primitive.points:
                    _draw_marker(
                        MarkerPrimitive(
                            x=x,
                            y=y,
                            color=primitive.color,
                            volume_ul=primitive.marker_volume_ul,
                            outline=primitive.outline,
                            minimum_pixels=(
                                primitive.marker_minimum_pixels
                            ),
                        )
                    )

        # Solid layout surfaces must not hide the TCP coordinate axes.
        self.canvas.tag_raise('coordinate_axis')

        # Keep the calibrated TCP crossing legible above every preview layer.
        origin_px, origin_py = world_to_canvas(0, 0)
        marker_radius = max(5, min(11, 2.5 * effective_scale))
        self.canvas.create_oval(
            origin_px - marker_radius,
            origin_py - marker_radius,
            origin_px + marker_radius,
            origin_py + marker_radius,
            fill=COLORS['canvas'],
            outline=COLORS['text_primary'],
            width=2,
        )
        self.canvas.create_line(
            origin_px - marker_radius - 4,
            origin_py,
            origin_px + marker_radius + 4,
            origin_py,
            fill=COLORS['axis_x'],
            width=2,
        )
        self.canvas.create_line(
            origin_px,
            origin_py - marker_radius - 4,
            origin_px,
            origin_py + marker_radius + 4,
            fill=COLORS['axis_y'],
            width=2,
        )
        self.canvas.create_text(
            origin_px - marker_radius - 6,
            origin_py - marker_radius - 4,
            text='TCP (0,0)',
            anchor='se',
            fill=COLORS['text_primary'],
            font=FONTS['label'],
        )
        self._render_live_toolhead()

    def _on_mousewheel(self, event):
        try:
            delta = event.delta
            if delta == 0:
                return
            factor = 1.1 if delta > 0 else 0.9
            self._apply_zoom(factor, event.x, event.y)
        except Exception:
            pass

    def _apply_zoom(self, factor, focus_x, focus_y):
        scale_old = self._fit_scale * self._zoom_factor
        if scale_old <= 0:
            return
        world_x = (focus_x - self._pan_x) / scale_old + self._origin_x
        world_y = (focus_y - self._pan_y) / scale_old + self._origin_y
        self._zoom_factor = max(0.1, min(10.0, self._zoom_factor * factor))
        scale_new = self._fit_scale * self._zoom_factor
        self._pan_x = focus_x - (world_x - self._origin_x) * scale_new
        self._pan_y = focus_y - (world_y - self._origin_y) * scale_new
        self.refresh()

    def _on_pan_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_pan_move(self, event):
        if not self._drag_start:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._pan_x += dx
        self._pan_y += dy
        self._drag_start = (event.x, event.y)
        self.refresh()

    def _show_exceed_popup(self):
        popup = tk.Toplevel(self.gui)
        popup.title("Pattern Acceptance Alert")
        popup.configure(bg=COLORS['bg_primary'])
        popup.transient(self.gui)
        popup.attributes('-topmost', True)
        panel = tk.Frame(
            popup,
            bg=COLORS['bg_secondary'],
            highlightbackground=COLORS['error'],
            highlightthickness=1,
            bd=0,
        )
        panel.pack(fill='both', expand=True, padx=12, pady=12)
        tk.Label(
            panel,
            text="ACCEPTANCE LIMIT EXCEEDED",
            font=FONTS['title'],
            fg=COLORS['error'],
            bg=COLORS['bg_secondary'],
        ).pack(anchor='w', padx=18, pady=(16, 5))
        tk.Label(
            panel,
            text=(
                "One or more planned points fall outside the runtime acceptance "
                "boundary. Review the highlighted preview before generating or "
                "running the job."
            ),
            wraplength=520,
            justify='left',
            font=FONTS['normal'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
        ).pack(anchor='w', padx=18, pady=(0, 14))
        close_btn = tk.Button(
            panel,
            text="ACKNOWLEDGE",
            command=popup.destroy,
            **button_options('danger'),
        )
        close_btn.pack(anchor='e', padx=18, pady=(0, 16))
        popup.bind('<Escape>', lambda _event: popup.destroy())
        popup.update_idletasks()
        width, height = popup.winfo_width(), popup.winfo_height()
        x = popup.winfo_screenwidth() // 2 - width // 2
        y = popup.winfo_screenheight() // 2 - height // 2
        popup.geometry(f'{width}x{height}+{x}+{y}')
        close_btn.focus_set()
