import tkinter as tk
from SpotterFunctions import read_entries_as_dict
from input_configs import GLOBAL_FIELDS, GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS, SPIRAL_FIELDS

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

    def start(self):
        self.gui.after(self.poll_interval, self._poll)
        try:
            self.canvas.bind("<MouseWheel>", self._on_mousewheel)
            self.canvas.bind("<Button-1>", self._on_pan_start)
            self.canvas.bind("<B1-Motion>", self._on_pan_move)
        except Exception:
            pass

    def refresh(self):
        snapshot = self._collect_data()
        self.draw(snapshot)

    def _poll(self):
        snapshot = self._collect_data()
        if snapshot != self._prev_snapshot:
            self._prev_snapshot = snapshot
            self.draw(snapshot)
        self.gui.after(self.poll_interval, self._poll)

    def _collect_data(self):
        global_vals = read_entries_as_dict(self.gui.entry, GLOBAL_FIELDS)
        grids, cleaning_grids, washing_data = [], [], []
        containers = []
        spirals = []

        for idx, grid_obj in sorted(self.gui.grid_tab_dict.items()):
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                vals = read_entries_as_dict(grid_obj.grid_entry, GRID_FIELDS)
                grid_color = "green"
                if hasattr(grid_obj, 'get_grid_color'):
                    try:
                        grid_color = grid_obj.get_grid_color()
                    except Exception:
                        grid_color = "green"
                grids.append((idx, vals, grid_color))

                if getattr(grid_obj, 'cleaning_enabled', tk.BooleanVar()).get():
                    vals_clean = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
                    cleaning_grids.append((idx, vals_clean))

                if getattr(grid_obj, 'washing_enabled', tk.BooleanVar()).get():
                    vals_wash = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
                    washing_data.append((idx, vals_wash))

        # Collect spiral definitions (if any)
        if hasattr(self.gui, 'spiral_tab_dict'):
            for idx, spiral_obj in sorted(self.gui.spiral_tab_dict.items()):
                try:
                    if spiral_obj and hasattr(spiral_obj, 'spiral_entry'):
                        vals = read_entries_as_dict(spiral_obj.spiral_entry, SPIRAL_FIELDS)
                        spiral_color = 'orange'
                        try:
                            spiral_color = spiral_obj.get_grid_color()
                        except Exception:
                            pass
                        spirals.append((idx, vals, spiral_color))
                except Exception:
                    continue

        for idx in range(1, 7):
            try:
                cx = float(global_vals.get(f'container{idx}_x', 0))
                cy = float(global_vals.get(f'container{idx}_y', 0))
                containers.append((idx, cx, cy))
            except Exception:
                continue

        return {
            'global': global_vals,
            'grids': grids,
            'cleaning_grids': cleaning_grids,
            'washing_data': washing_data,
            'containers': containers,
            'spirals': spirals,
        }

    def draw(self, snapshot):
        self.canvas.delete('all')
        if snapshot is None:
            return

        global_vals = snapshot.get('global', {})
        grids_list = snapshot.get('grids', [])
        cleaning_grids_list = snapshot.get('cleaning_grids', [])
        washing_data_list = snapshot.get('washing_data', [])
        container_list = snapshot.get('containers', [])
        spirals_list = snapshot.get('spirals', [])

        if not global_vals:
            return

        if not (grids_list or cleaning_grids_list or washing_data_list or spirals_list or container_list):
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
        grey_w = float(global_vals.get('grey_square_x', 0))
        grey_h = float(global_vals.get('grey_square_y', 0))
        anchor_off_x = float(global_vals.get('anchor_offset_x', -30))
        anchor_off_y = float(global_vals.get('anchor_offset_y', -40))
        purple_size = 225

        # --- Collect points and grid extents ---
        points = []
        grid_extents = []
        washing_by_grid = {idx: vals for idx, vals in washing_data_list}
        cleaning_by_grid = {idx: vals for idx, vals in cleaning_grids_list}

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

            total_spots = max(0, int(rows) * int(cols))
            cycle_origins = []

            # Cleaning cycle counter starts at 0 per grid; first cleaning occurs before spots.
            cycle_index = 0
            cycle_origins.append((x_abs + first_x_off + offset_x + cycle_index * rel_x, y_abs + first_y_off + offset_y + cycle_index * rel_y, cycle_index))
            cycle_index += 1

            washing_vals = washing_by_grid.get(g_idx)
            if not washing_vals:
                return cycle_origins

            try:
                washing_after = int(float(washing_vals.get('washing_after_x_spots', 0)))
            except Exception:
                washing_after = 0

            if washing_after <= 0:
                return cycle_origins

            # Mirror generate_grid logic: increment counter each spot, trigger on modulo, then reset.
            washing_spot_counter = 0
            for _ in range(total_spots):
                washing_spot_counter += 1
                if washing_spot_counter % washing_after == 0:
                    cycle_origins.append((
                        x_abs + first_x_off + offset_x + cycle_index * rel_x,
                        y_abs + first_y_off + offset_y + cycle_index * rel_y,
                        cycle_index,
                    ))
                    cycle_index += 1
                    washing_spot_counter = 0

            return cycle_origins

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
            grid_extents.append({
                'grid_idx': g_idx,
                'x1': start_x,
                'y1': start_y,
                'x2': start_x + width,
                'y2': start_y + height
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
        # --- Determine canvas bounds ---
        purple_x1 = x_abs + anchor_off_x
        purple_y1 = y_abs + anchor_off_y
        purple_x2 = purple_x1 + purple_size
        purple_y2 = purple_y1 + purple_size

        xs = ([p[0] for p in points] if points else []) + ([p[0] for p in cleaning_preview_points] if cleaning_preview_points else []) + [x_abs, x_abs + rect_w, purple_x1, purple_x2] + [c[1] for c in container_list]
        ys = ([p[1] for p in points] if points else []) + ([p[1] for p in cleaning_preview_points] if cleaning_preview_points else []) + [y_abs, y_abs + rect_h, purple_y1, purple_y2] + [c[2] for c in container_list]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        c_w, c_h = int(self.canvas['width']), int(self.canvas['height'])
        margin = 10
        reserved_left_px, reserved_bottom_px = 100, 100
        content_margin_x = margin + reserved_left_px
        content_margin_y = margin + reserved_bottom_px
        range_x = maxx - minx or 1
        range_y = maxy - miny or 1
        fit_scale = min((c_w - 2 * margin) / range_x, (c_h - 2 * margin) / range_y)
        self._fit_scale = fit_scale
        if self._pan_x is None:
            self._pan_x = content_margin_x
        if self._pan_y is None:
            self._pan_y = content_margin_y
        self._origin_x, self._origin_y = minx, miny
        effective_scale = self._fit_scale * self._zoom_factor

        # --- Inner acceptance rectangle centered in black square ---
        inner_x1 = x_abs + (rect_w - inner_w) / 2
        inner_y1 = y_abs + (rect_h - inner_h) / 2
        inner_x2 = inner_x1 + inner_w
        inner_y2 = inner_y1 + inner_h

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
        if exceed and not getattr(self, '_last_exceed_state', False):
            self._show_exceed_popup()
        self._last_exceed_state = exceed

        # --- Canvas anchor ---
        anchor_px_base = content_margin_x + (x_abs - minx) * effective_scale
        anchor_px_base = (x_abs - self._origin_x) * effective_scale + self._pan_x
        anchor_py_base = c_h - ((y_abs - self._origin_y) * effective_scale + self._pan_y)

        # --- Background ---
        self.canvas.create_rectangle(0, 0, c_w, c_h, fill='white', outline='')

        # --- Draw fixed 250x250 orange square anchored by user offsets, labeled 0,0 (behind other overlays) ---
        orange_px1 = anchor_px_base + (purple_x1 - x_abs) * effective_scale
        orange_py1 = anchor_py_base - (purple_y1 - y_abs) * effective_scale
        orange_px2 = orange_px1 + purple_size * effective_scale
        orange_py2 = orange_py1 - purple_size * effective_scale
        self.canvas.create_rectangle(orange_px1, orange_py1, orange_px2, orange_py2, outline='orange', fill='orange', width=3)
        self.canvas.create_text(orange_px1 + 6, orange_py1 - 6, text="0,0", anchor='sw', fill='black', font=("Segoe UI", 10, 'bold'))

        # --- Draw grey rectangle (centered) ---
        grey_x = anchor_px_base + ((x_abs + (rect_w - grey_w)/2) - x_abs) * effective_scale
        grey_y = anchor_py_base - ((y_abs + (rect_h - grey_h)/2) - y_abs) * effective_scale
        self.canvas.create_rectangle(
            grey_x, grey_y,
            grey_x + grey_w * effective_scale,
            grey_y - grey_h * effective_scale,
            fill='grey', outline=''
        )

        # --- Draw inner acceptance rectangle ---
        inner_px = anchor_px_base + (inner_x1 - x_abs) * effective_scale
        inner_py = anchor_py_base - (inner_y1 - y_abs) * effective_scale
        self.canvas.create_rectangle(
            inner_px, inner_py,
            inner_px + inner_w * effective_scale,
            inner_py - inner_h * effective_scale,
            fill='white', outline='darkgreen', width=2
        )

        # --- Anchor guide lines ---
        def world_to_canvas(wx, wy):
            px = (wx - self._origin_x) * effective_scale + self._pan_x
            py = c_h - ((wy - self._origin_y) * effective_scale + self._pan_y)
            return px, py

        # primary anchors
        x_line = x_abs
        y_line = y_abs

        # vertical line for x_cord_of_y_line (green)
        px1, py1 = world_to_canvas(x_line, miny)
        px2, py2 = world_to_canvas(x_line, maxy)
        self.canvas.create_line(px1, py1, px2, py2, fill='green', width=2)

        # horizontal line for y_cord_of_x_line (red)
        px1, py1 = world_to_canvas(minx, y_line)
        px2, py2 = world_to_canvas(maxx, y_line)
        self.canvas.create_line(px1, py1, px2, py2, fill='red', width=2)

        # --- Draw outer black rectangle ---
        black_x1, black_y1 = anchor_px_base, anchor_py_base
        black_x1, black_y1 = anchor_px_base, anchor_py_base
        black_x2, black_y2 = black_x1 + rect_w * effective_scale, black_y1 - rect_h * effective_scale
        self.canvas.create_rectangle(black_x1, black_y1, black_x2, black_y2, outline='black', width=2)

        # --- Draw containers as circles with labels ---
        circle_mm_radius = 6.0
        for idx, cx, cy in container_list:
            px = (cx - self._origin_x) * effective_scale + self._pan_x
            py = c_h - ((cy - self._origin_y) * effective_scale + self._pan_y)
            rad_px = max(2, circle_mm_radius * effective_scale)
            self.canvas.create_oval(
                px - rad_px,
                py - rad_px,
                px + rad_px,
                py + rad_px,
                outline='black',
                width=2,
                fill='#f8f8f8'
            )
            self.canvas.create_text(px, py, text=str(idx), fill='black', font=("Segoe UI", 10, 'bold'))

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

        # --- Draw grid points ---
        for x, y, g_idx, dispense, grid_color in points:
            px = (x - self._origin_x) * effective_scale + self._pan_x
            py = c_h - ((y - self._origin_y) * effective_scale + self._pan_y)
            diam_mm = max(0, m * dispense + b)
            rad_px = min(max(1, int((diam_mm / 2) * effective_scale)), 80)
            self.canvas.create_oval(px - rad_px, py - rad_px, px + rad_px, py + rad_px,
                                    fill=grid_color, outline='')

        # --- Draw spiral previews ---
        def _spiral_points(center_x, center_y, start_radius, turns, spacing_mm, theta_offset=0.0):
            from math import cos, sin, pi
            b = max(1e-9, spacing_mm / (2.0 * pi))
            max_theta = 2.0 * pi * max(0.0, float(turns))
            step = 0.08
            pts = []
            theta = 0.0
            while theta <= max_theta + 1e-9:
                adjusted = theta + theta_offset
                radius = float(start_radius) + b * theta
                x = float(center_x) + radius * cos(adjusted)
                y = float(center_y) + radius * sin(adjusted)
                pts.append((x, y))
                theta += step
            return pts

        for s_idx, s_vals, s_color in spirals_list:
            try:
                # Interpret spiral center as coordinates relative to the XY anchor intersection
                # so that center (0,0) maps to the intersection at (x_abs, y_abs).
                cx = x_abs + float(s_vals.get('center_x', 0.0))
                cy = y_abs + float(s_vals.get('center_y', 0.0))
                start_radius = float(s_vals.get('start_radius', 0.0))
                turns = float(s_vals.get('turns', 5.0))
                spacing_mm = float(s_vals.get('spacing_mm', 1.5))
                num_starts = max(1, int(float(s_vals.get('num_starts', 1))))
                dispense = float(s_vals.get('dispense_vol', 0.003))
                mode = str(s_vals.get('spiral_mode', 'drop')).strip().lower()
                interleave = str(s_vals.get('interleave', False)).strip().lower() in ('1', 'true', 'yes', 'on', 'true')
            except Exception:
                continue

            # build point sets
            all_point_sets = []
            from math import pi
            for start_i in range(num_starts):
                theta_off = (2.0 * pi * start_i) / float(num_starts)
                all_point_sets.append(_spiral_points(cx, cy, start_radius, turns, spacing_mm, theta_offset=theta_off))

            if interleave:
                # interleave
                max_len = max((len(ps) for ps in all_point_sets), default=0)
                path = []
                for i in range(max_len):
                    for ps in all_point_sets:
                        if i < len(ps):
                            path.append(ps[i])
            else:
                path = [p for ps in all_point_sets for p in ps]

            if not path:
                continue

            # draw polyline
            last_px = None
            for px_world, py_world in path:
                px_canvas = (px_world - self._origin_x) * effective_scale + self._pan_x
                py_canvas = c_h - ((py_world - self._origin_y) * effective_scale + self._pan_y)
                if last_px is not None:
                    self.canvas.create_line(last_px[0], last_px[1], px_canvas, py_canvas, fill=s_color, width=2)
                last_px = (px_canvas, py_canvas)

            # for drop mode, mark spots as circles
            if mode == 'drop':
                for px_world, py_world in path:
                    px_canvas = (px_world - self._origin_x) * effective_scale + self._pan_x
                    py_canvas = c_h - ((py_world - self._origin_y) * effective_scale + self._pan_y)
                    diam_mm = max(0, m * dispense + b)
                    rad_px = max(2, int((diam_mm / 2) * effective_scale))
                    self.canvas.create_oval(px_canvas - rad_px, py_canvas - rad_px, px_canvas + rad_px, py_canvas + rad_px, fill=s_color, outline='')

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
                fill_color = '#7d3cb5' if cycle_index == 0 else '#cbb2e6'
                outline_color = '#3d255a' if cycle_index == 0 else '#8f7aa8'

                for r in range(c_rows):
                    for c in range(c_cols):
                        cx = start_x + c * c_pitch_x
                        cy = start_y + r * c_pitch_y
                        px = (cx - self._origin_x) * effective_scale + self._pan_x
                        py = c_h - ((cy - self._origin_y) * effective_scale + self._pan_y)
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

            px_left = (start_x_world - self._origin_x) * effective_scale + self._pan_x
            px_right = (end_x_world - self._origin_x) * effective_scale + self._pan_x
            py = c_h - ((y_world - self._origin_y) * effective_scale + self._pan_y)

            self.canvas.create_line(px_left, py, px_right, py, width=3, fill='cyan')

        # (Removed duplicate purple square draw; orange square is already drawn near the background layer.)

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
        c_h = int(self.canvas['height'])
        scale_old = self._fit_scale * self._zoom_factor
        if scale_old <= 0:
            return
        world_x = (focus_x - self._pan_x) / scale_old + self._origin_x
        world_y = (c_h - focus_y - self._pan_y) / scale_old + self._origin_y
        self._zoom_factor = max(0.1, min(10.0, self._zoom_factor * factor))
        scale_new = self._fit_scale * self._zoom_factor
        self._pan_x = focus_x - (world_x - self._origin_x) * scale_new
        self._pan_y = (c_h - focus_y) - (world_y - self._origin_y) * scale_new
        self.refresh()

    def _on_pan_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_pan_move(self, event):
        if not self._drag_start:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._pan_x += dx
        self._pan_y -= dy
        self._drag_start = (event.x, event.y)
        self.refresh()

    def _show_exceed_popup(self):
        popup = tk.Toplevel(self.gui)
        popup.title("Grid Dimension Alert")
        popup.attributes('-topmost', True)
        label = tk.Label(popup, text="GRID EXCEEDS DIMENSIONS", font=("Arial", 24, "bold"), fg="red", padx=20, pady=20)
        label.pack()
        close_btn = tk.Button(popup, text="OK", command=popup.destroy, font=("Arial", 14), padx=20, pady=10)
        close_btn.pack(pady=10)
        popup.update_idletasks()
        width, height = popup.winfo_width(), popup.winfo_height()
        x = popup.winfo_screenwidth() // 2 - width // 2
        y = popup.winfo_screenheight() // 2 - height // 2
        popup.geometry(f'{width}x{height}+{x}+{y}')
