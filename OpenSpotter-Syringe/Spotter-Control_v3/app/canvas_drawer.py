import math
import tkinter as tk
from collections.abc import Mapping

from PIL import Image, ImageOps, ImageTk
from .SpotterFunctions import build_containers, entries_to_dict
from .input_configs import GLOBAL_FIELDS, GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS, SPIRAL_FIELDS
from .paths import PROJECT_DIR
from .ui_theme import COLORS, FONTS, button_options
from .visual_objects import (
    resolve_visual_object_bindings,
    resolve_visual_image_path,
    visual_object_bounds,
    visual_object_center,
)


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
        grids, cleaning_grids, washing_data = [], [], []
        grid_flags = {}
        spirals = []

        for idx, grid_obj in sorted(self.gui.grid_tab_dict.items()):
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                vals = entries_to_dict(grid_obj.grid_entry, GRID_FIELDS)
                grid_color = "green"
                if hasattr(grid_obj, 'get_grid_color'):
                    try:
                        grid_color = grid_obj.get_grid_color()
                    except Exception:
                        grid_color = "green"
                grids.append((idx, vals, grid_color))

                flags = {
                    'cleaning_enabled': bool(grid_obj.cleaning_enabled.get()),
                    'washing_enabled': bool(grid_obj.washing_enabled.get()),
                    'wash_after_loading': bool(grid_obj.wash_after_loading_enabled.get()),
                    'final_rinse_enabled': bool(grid_obj.final_rinse_enabled.get()),
                    'final_rinse_add_cleaning_grid': bool(
                        grid_obj.final_rinse_add_cleaning_grid.get()
                    ),
                }
                grid_flags[idx] = flags

                if flags['cleaning_enabled'] or (
                    flags['final_rinse_enabled']
                    and flags['final_rinse_add_cleaning_grid']
                ):
                    vals_clean = entries_to_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
                    cleaning_grids.append((idx, vals_clean))

                if flags['washing_enabled']:
                    vals_wash = entries_to_dict(grid_obj.washing_entry, WASHING_FIELDS)
                    washing_data.append((idx, vals_wash))

        # Collect spiral definitions (if any)
        if hasattr(self.gui, 'spiral_tab_dict'):
            for idx, spiral_obj in sorted(self.gui.spiral_tab_dict.items()):
                try:
                    if spiral_obj and hasattr(spiral_obj, 'spiral_entry'):
                        vals = entries_to_dict(spiral_obj.spiral_entry, SPIRAL_FIELDS)
                        spiral_color = 'orange'
                        try:
                            spiral_color = spiral_obj.get_grid_color()
                        except Exception:
                            pass
                        spirals.append((idx, vals, spiral_color))
                except Exception:
                    continue

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
            'grids': grids,
            'cleaning_grids': cleaning_grids,
            'washing_data': washing_data,
            'grid_flags': grid_flags,
            'spirals': spirals,
            'visual_objects': visual_objects,
            'visual_binding_warnings': tuple(visual_binding_warnings),
        }

    def draw(self, snapshot):
        self.canvas.delete('all')
        if snapshot is None:
            self._visual_image_cache.clear()
            return

        global_vals = snapshot.get('global', {})
        grids_list = snapshot.get('grids', [])
        cleaning_grids_list = snapshot.get('cleaning_grids', [])
        washing_data_list = snapshot.get('washing_data', [])
        grid_flags = snapshot.get('grid_flags', {})
        spirals_list = snapshot.get('spirals', [])
        visual_objects = snapshot.get('visual_objects', [])

        if not global_vals:
            self._visual_image_cache.clear()
            return

        # Base and offsets
        x_abs = float(global_vals.get('x_cord_of_y_line', 0))
        y_abs = float(global_vals.get('y_cord_of_x_line', 0))
        first_x_off = float(global_vals.get('tuning_offset_x', 0))
        first_y_off = float(global_vals.get('tuning_offset_y', 0))
        rect_w = float(global_vals.get('base_square_x', 0))
        rect_h = float(global_vals.get('base_square_y', 0))
        inner_w = float(global_vals.get('acceptance_square_x', 0))
        inner_h = float(global_vals.get('acceptance_square_y', 0))

        # Plan spiral geometry before fitting/safety checks so the canvas and
        # generated job use identical coordinates and workflow resolution.
        spiral_preview_paths = []
        preview_engine = None
        try:
            from pathlib import Path

            from .gcode_workflow import WorkflowEngine, build_runtime_context_defaults
            from .paths import WORKFLOW_CONFIG
            from .plugins.spiral import SpiralPlugin

            preview_context = build_runtime_context_defaults()
            preview_context["global"].update(global_vals)
            workflow_path = Path(self.gui.config_dir) / WORKFLOW_CONFIG.name
            preview_engine = WorkflowEngine(workflow_path, preview_context)
            spiral_planner = SpiralPlugin()
            for spiral_index, spiral_values, spiral_color in spirals_list:
                try:
                    preview_engine.update_context({
                        "spiral": dict(spiral_values),
                        "runtime": {
                            "job": {"kind": "spiral", "pattern_index": spiral_index}
                        },
                    })
                    spiral_resolution = float(
                        preview_engine.custom_value("spiral_resolution_radians")
                    )
                    millimeters_per_microliter = float(
                        preview_engine.custom_value("syringe_mm_per_ul")
                    )
                    planned = spiral_planner.plan({
                        "params": spiral_values,
                        "resolution_radians": spiral_resolution,
                        "millimeters_per_microliter": millimeters_per_microliter,
                    })
                    paths_by_start = {}
                    for point in planned:
                        paths_by_start.setdefault(point["start_index"], []).append(
                            (point["x"], point["y"])
                        )
                    path_groups = list(paths_by_start.values())
                    spiral_preview_paths.append({
                        "index": spiral_index,
                        "path": [point for path in path_groups for point in path],
                        "paths": path_groups,
                        "color": spiral_color,
                        "dispense": float(spiral_values.get('dispense_vol', 0.003)),
                        "mode": str(spiral_values.get('spiral_mode', 'drop')).strip().lower(),
                    })
                except Exception:
                    continue
        except Exception:
            spiral_preview_paths = []

        # --- Collect points and grid extents ---
        points = []
        grid_extents = []
        washing_by_grid = {idx: vals for idx, vals in washing_data_list}
        cleaning_by_grid = {idx: vals for idx, vals in cleaning_grids_list}

        cleaning_cycles_by_grid = {idx: [] for idx, _values, _color in grids_list}
        if preview_engine is not None:
            try:
                from .gcode_planner import calculate_grid_refill_ul, generate_grid_events

                class _PreviewSink:
                    @staticmethod
                    def write(_text):
                        return None

                class _PreviewEventEngine:
                    def __init__(self, workflow_engine):
                        self.workflow_engine = workflow_engine
                        self.cleaning_cycles = []

                    def custom_value(self, name):
                        return self.workflow_engine.custom_value(name)

                    def emit(self, trigger, overrides):
                        if trigger == "cleaning_start":
                            self.cleaning_cycles.append(
                                int(overrides["cleaning"]["cycle"])
                            )
                        return ""

                preview_common = {
                    "x_offset": x_abs + first_x_off,
                    "y_offset": y_abs + first_y_off,
                    "priming_vol": float(global_vals.get("priming_vol", 0.0)),
                    "drop_extra_aspirate": float(
                        global_vals.get("drop_extra_aspirate", 0.0)
                    ),
                    "max_syringe_vol": float(
                        global_vals.get("max_syringe_vol", 0.0)
                    ),
                }
                containers = build_containers(global_vals)
                for grid_index, grid_values, _grid_color in grids_list:
                    flags = grid_flags.get(grid_index, {})
                    cleaning_values = cleaning_by_grid.get(grid_index, {})
                    washing_values = washing_by_grid.get(grid_index, {})
                    preview_engine.update_context({
                        "grid": dict(grid_values),
                        "cleaning": dict(cleaning_values),
                        "washing": dict(washing_values),
                        "runtime": {
                            "job": {"kind": "grid", "pattern_index": grid_index}
                        },
                    })
                    recorder = _PreviewEventEngine(preview_engine)
                    cleaning_cycle_counter = [0]
                    syringe_tracker = [0.0]
                    washing_spot_counter = [0]
                    generate_grid_events(
                        file=_PreviewSink(),
                        engine=recorder,
                        common=preview_common,
                        grid_values=grid_values,
                        cleaning_values=cleaning_values,
                        washing_values=washing_values,
                        flags=flags,
                        containers=containers,
                        refill_ul=calculate_grid_refill_ul(
                            preview_common,
                            grid_values,
                            cleaning_values,
                            flags,
                        ),
                        washing_spot_counter=washing_spot_counter,
                        syringe_tracker=syringe_tracker,
                        cleaning_cycle_counter=cleaning_cycle_counter,
                    )
                    cycles = list(recorder.cleaning_cycles)
                    if flags.get("final_rinse_enabled") and flags.get(
                        "final_rinse_add_cleaning_grid"
                    ):
                        cycles.append(cleaning_cycle_counter[0])
                    cleaning_cycles_by_grid[grid_index] = cycles
            except Exception:
                pass

        def _cleaning_cycle_origins_for_grid(g_idx, rows, cols):
            cleaning_vals = cleaning_by_grid.get(g_idx)
            if not cleaning_vals:
                return []

            try:
                offset_x = float(cleaning_vals.get('grid_offset_x_cleaning', 0.0))
                offset_y = float(cleaning_vals.get('grid_offset_y_cleaning', 0.0))
                rel_x = float(cleaning_vals.get('x_relative_increase', 0.0))
                rel_y = float(cleaning_vals.get('y_relative_increase', 0.0))
            except Exception:
                return []

            return [
                (
                    x_abs + first_x_off + offset_x + cycle_index * rel_x,
                    y_abs + first_y_off + offset_y + cycle_index * rel_y,
                    cycle_index,
                )
                for cycle_index in cleaning_cycles_by_grid.get(g_idx, [])
            ]

        cleaning_preview_points = []
        for g_idx, vals, grid_color in grids_list:
            rows = int(vals.get('rows', 0))
            cols = int(vals.get('cols', 0))
            x_step = float(vals.get('pitch_x', 0))
            y_step = float(vals.get('pitch_y', 0))
            grid_x_off = float(vals.get('grid_offset_x', 0))
            grid_y_off = float(vals.get('grid_offset_y', 0))
            dispense = float(vals.get('dispense_vol', 0))

            # Grid positions include first offsets
            start_x = x_abs + first_x_off + grid_x_off
            start_y = y_abs + first_y_off + grid_y_off

            width = (cols - 1) * x_step if cols > 0 else 0
            height = (rows - 1) * y_step if rows > 0 else 0
            end_x = start_x + width
            end_y = start_y + height
            grid_extents.append({
                'grid_idx': g_idx,
                'x1': min(start_x, end_x),
                'y1': min(start_y, end_y),
                'x2': max(start_x, end_x),
                'y2': max(start_y, end_y),
            })

            for r in range(rows):
                for c in range(cols):
                    points.append((start_x + c * x_step, start_y + r * y_step, g_idx, dispense, grid_color))

            cleaning_vals = cleaning_by_grid.get(g_idx)
            if cleaning_vals:
                c_rows = int(float(cleaning_vals.get('rows_cleaning', 0)))
                c_cols = int(float(cleaning_vals.get('cols_cleaning', 0)))
                c_pitch_x = float(cleaning_vals.get('pitch_x_cleaning', 0.0))
                c_pitch_y = float(cleaning_vals.get('pitch_y_cleaning', 0.0))
                for cycle_start_x, cycle_start_y, cycle_index in _cleaning_cycle_origins_for_grid(g_idx, rows, cols):
                    for cr in range(c_rows):
                        for cc in range(c_cols):
                            cleaning_preview_points.append((
                                cycle_start_x + cc * c_pitch_x,
                                cycle_start_y + cr * c_pitch_y,
                                cycle_index,
                            ))
        # --- Inner acceptance rectangle centered in the build plate ---
        inner_x1 = x_abs + (rect_w - inner_w) / 2
        inner_y1 = y_abs + (rect_h - inner_h) / 2
        inner_x2 = inner_x1 + inner_w
        inner_y2 = inner_y1 + inner_h

        # --- Determine world bounds around TCP (0,0) and visible content ---
        xs = [0.0]
        ys = [0.0]
        xs.extend(point[0] for point in points)
        ys.extend(point[1] for point in points)
        xs.extend(point[0] for point in cleaning_preview_points)
        ys.extend(point[1] for point in cleaning_preview_points)
        xs.extend(x for item in spiral_preview_paths for x, _y in item["path"])
        ys.extend(y for item in spiral_preview_paths for _x, y in item["path"])

        for item in visual_objects:
            try:
                left, bottom, right, top = visual_object_bounds(item)
                xs.extend((left, right))
                ys.extend((bottom, top))
            except (KeyError, TypeError, ValueError):
                continue

        for _grid_index, washing_values in washing_data_list:
            try:
                wash_x = float(washing_values.get('washing_x_pos', 0))
                wash_y = float(washing_values.get('washing_y_pos', 0))
                wash_length = float(washing_values.get('washing_line_lenght', 0))
                xs.extend((wash_x, wash_x + wash_length))
                ys.append(wash_y)
            except (TypeError, ValueError):
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

        # --- Check if any grid exceeds acceptance rectangle ---
        exceed = False
        for g in grid_extents:
            if g['x1'] < inner_x1 or g['y1'] < inner_y1 or g['x2'] > inner_x2 or g['y2'] > inner_y2:
                exceed = True
                break
        if not exceed:
            for cx, cy, _ in cleaning_preview_points:
                if cx < inner_x1 or cy < inner_y1 or cx > inner_x2 or cy > inner_y2:
                    exceed = True
                    break
        if not exceed:
            for spiral in spiral_preview_paths:
                if any(
                    x < inner_x1 or y < inner_y1 or x > inner_x2 or y > inner_y2
                    for x, y in spiral["path"]
                ):
                    exceed = True
                    break
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

        # --- Draw grid points ---
        for x, y, g_idx, dispense, grid_color in points:
            px, py = world_to_canvas(x, y)
            diam_mm = max(0, m * dispense + b)
            rad_px = min(max(1, int((diam_mm / 2) * effective_scale)), 80)
            self.canvas.create_oval(px - rad_px, py - rad_px, px + rad_px, py + rad_px,
                                    fill=grid_color, outline=_series_outline(grid_color), width=1)

        # --- Draw the spiral geometry already used for bounds/safety checks ---
        for spiral in spiral_preview_paths:
            paths = spiral["paths"]
            if not paths:
                continue
            s_color = spiral["color"]
            dispense = spiral["dispense"]
            mode = spiral["mode"]

            # Draw each start separately.  Joining starts would imply a
            # deposited connector that generation intentionally does not emit.
            for path in paths:
                last_px = None
                for px_world, py_world in path:
                    px_canvas, py_canvas = world_to_canvas(px_world, py_world)
                    if last_px is not None:
                        self.canvas.create_line(
                            last_px[0], last_px[1], px_canvas, py_canvas,
                            fill=_series_outline(s_color), width=4,
                        )
                        self.canvas.create_line(
                            last_px[0], last_px[1], px_canvas, py_canvas,
                            fill=s_color, width=2,
                        )
                    last_px = (px_canvas, py_canvas)

            # for drop mode, mark spots as circles
            if mode == 'drop':
                for px_world, py_world in spiral["path"]:
                    px_canvas, py_canvas = world_to_canvas(px_world, py_world)
                    diam_mm = max(0, m * dispense + b)
                    rad_px = max(2, int((diam_mm / 2) * effective_scale))
                    self.canvas.create_oval(
                        px_canvas - rad_px,
                        py_canvas - rad_px,
                        px_canvas + rad_px,
                        py_canvas + rad_px,
                        fill=s_color,
                        outline=_series_outline(s_color),
                        width=1,
                    )

        # --- Draw cleaning grids (cycle 0 solid, follow-up cycles faded) ---
        for g_idx, vals, _grid_color in grids_list:
            cleaning_vals = cleaning_by_grid.get(g_idx)
            if not cleaning_vals:
                continue

            rows = int(vals.get('rows', 0))
            cols = int(vals.get('cols', 0))
            c_rows = int(float(cleaning_vals.get('rows_cleaning', 0)))
            c_cols = int(float(cleaning_vals.get('cols_cleaning', 0)))
            if c_rows <= 0 or c_cols <= 0:
                continue

            c_pitch_x = float(cleaning_vals.get('pitch_x_cleaning', 0.0))
            c_pitch_y = float(cleaning_vals.get('pitch_y_cleaning', 0.0))

            for start_x, start_y, cycle_index in _cleaning_cycle_origins_for_grid(g_idx, rows, cols):
                fill_color = COLORS['warning'] if cycle_index == 0 else COLORS['text_muted']
                outline_color = COLORS['canvas'] if cycle_index == 0 else COLORS['border_strong']

                for r in range(c_rows):
                    for c in range(c_cols):
                        cx = start_x + c * c_pitch_x
                        cy = start_y + r * c_pitch_y
                        px, py = world_to_canvas(cx, cy)
                        s = max(2, int(0.08 * effective_scale))
                        self.canvas.create_rectangle(px - s, py - s, px + s, py + s, fill=fill_color, outline=outline_color)

        # --- Draw washing lines ---
        for g_idx, wvals in washing_data_list:
            wash = {k: float(v) for k, v in wvals.items()}
            x_start, x_offset = wash.get('washing_x_pos', 0), wash.get('washing_line_lenght', 0)
            row_offset = wash.get('washing_y_pos', 0)

            # Washing coordinates are absolute machine coordinates, same as container positions.
            start_x_world = x_start
            end_x_world = start_x_world + x_offset
            y_world = row_offset

            px_left, py = world_to_canvas(start_x_world, y_world)
            px_right, _py = world_to_canvas(end_x_world, y_world)

            self.canvas.create_line(
                px_left,
                py,
                px_right,
                py,
                width=3,
                fill=COLORS['axis_y'],
                dash=(8, 3),
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
