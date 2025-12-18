import math
import tkinter as tk
from SpotterFunctions import read_entries_as_dict
from input_configs import GLOBAL_FIELDS, GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS

class CanvasDrawer:
    def __init__(self, gui, poll_interval=500):
        self.gui = gui
        self.canvas = gui.canvas
        self.poll_interval = poll_interval
        self._prev_snapshot = None
        self._last_exceed_state = False

    def start(self):
        self.gui.after(self.poll_interval, self._poll)

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

        for idx in range(1, 4):
            grid_obj = getattr(self.gui, f'grid_{idx}', None)
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                vals = read_entries_as_dict(grid_obj.grid_entry, GRID_FIELDS)
                grids.append((idx, vals))

                if getattr(grid_obj, 'cleaning_enabled', tk.BooleanVar()).get():
                    vals_clean = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
                    cleaning_grids.append((idx, vals_clean))

                if getattr(grid_obj, 'washing_enabled', tk.BooleanVar()).get():
                    vals_wash = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
                    washing_data.append((idx, vals_wash))

        return {
            'global': global_vals,
            'grids': grids,
            'cleaning_grids': cleaning_grids,
            'washing_data': washing_data
        }

    def draw(self, snapshot):
        self.canvas.delete('all')
        if snapshot is None:
            return

        global_vals = snapshot.get('global', {})
        grids_list = snapshot.get('grids', [])
        cleaning_grids_list = snapshot.get('cleaning_grids', [])
        washing_data_list = snapshot.get('washing_data', [])

        if not global_vals:
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

        # --- Collect points and grid extents ---
        points = []
        grid_extents = []
        for g_idx, vals in grids_list:
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
                    points.append((start_x + c * x_step, start_y + r * y_step, g_idx, dispense))

        if not points:
            return

        # --- Determine canvas bounds ---
        xs = [p[0] for p in points] + [x_abs, x_abs + rect_w]
        ys = [p[1] for p in points] + [y_abs, y_abs + rect_h]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        c_w, c_h = int(self.canvas['width']), int(self.canvas['height'])
        margin = 10
        reserved_left_px, reserved_bottom_px = 100, 100
        content_margin_x = margin + reserved_left_px
        content_margin_y = margin + reserved_bottom_px

        range_x = maxx - minx or 1
        range_y = maxy - miny or 1
        scale = min((c_w - 2 * margin) / range_x, (c_h - 2 * margin) / range_y)
        effective_scale = getattr(self.gui, 'px_per_mm', 0.0) or scale

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
        if exceed and not getattr(self, '_last_exceed_state', False):
            self._show_exceed_popup()
        self._last_exceed_state = exceed

        # --- Canvas anchor ---
        anchor_px_base = content_margin_x + (x_abs - minx) * effective_scale
        anchor_py_base = c_h - (content_margin_y + (y_abs - miny) * effective_scale)

        # --- Background ---
        self.canvas.create_rectangle(0, 0, c_w, c_h, fill='white', outline='')

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

        # --- Draw outer black rectangle ---
        black_x1, black_y1 = anchor_px_base, anchor_py_base
        black_x2, black_y2 = black_x1 + rect_w * effective_scale, black_y1 - rect_h * effective_scale
        self.canvas.create_rectangle(black_x1, black_y1, black_x2, black_y2, outline='black', width=2)

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
        color_map = {1: 'green', 2: 'orange', 3: 'blue'}
        for x, y, g_idx, dispense in points:
            px = anchor_px_base + (x - x_abs) * effective_scale
            py = anchor_py_base - (y - y_abs) * effective_scale
            diam_mm = max(0, m * dispense + b)
            rad_px = min(max(1, int((diam_mm / 2) * effective_scale)), 80)
            self.canvas.create_oval(px - rad_px, py - rad_px, px + rad_px, py + rad_px,
                                    fill=color_map.get(g_idx, 'black'), outline='')

        # --- Draw cleaning grids ---
        for g_idx, cvals in cleaning_grids_list:
            cleaning = {k: float(v) for k, v in cvals.items()}
            rows, cols = int(cleaning.get('rows_cleaning', 0)), int(cleaning.get('cols_cleaning', 0))
            if rows == 0 or cols == 0:
                continue
            pitch_x, pitch_y = cleaning.get('pitch_x_cleaning', 0), cleaning.get('pitch_y_cleaning', 0)
            offset_x, offset_y = cleaning.get('grid_offset_x_cleaning', 0), cleaning.get('grid_offset_y_cleaning', 0)

            main_grid = next((vals for idx, vals in grids_list if idx == g_idx), {})
            gx_off, gy_off = float(main_grid.get('grid_offset_x', 0)), float(main_grid.get('grid_offset_y', 0))
            start_x = x_abs + first_x_off + gx_off + offset_x
            start_y = y_abs + first_y_off + gy_off + offset_y

            for r in range(rows):
                for c in range(cols):
                    cx = start_x + c * pitch_x
                    cy = start_y + r * pitch_y
                    px = anchor_px_base + (cx - x_abs) * effective_scale
                    py = anchor_py_base - (cy - y_abs) * effective_scale
                    s = max(2, int(0.08 * effective_scale))
                    self.canvas.create_rectangle(px - s, py - s, px + s, py + s, fill='purple', outline='black')

        # --- Draw washing lines ---
        for g_idx, wvals in washing_data_list:
            wash = {k: float(v) for k, v in wvals.items()}
            upper, lower = wash.get('washing_upper_bound', 0), wash.get('washing_lower_bound', 0)
            col_offset = wash.get('washing_column_offset', 0)
            main_grid = next((vals for idx, vals in grids_list if idx == g_idx), {})
            gx_off, gy_off = float(main_grid.get('grid_offset_x', 0)), float(main_grid.get('grid_offset_y', 0))
            x_pos = x_abs + first_x_off + gx_off + col_offset
            y_top, y_bottom = y_abs + first_y_off + gy_off + upper, y_abs + first_y_off + gy_off + lower
            px = anchor_px_base + (x_pos - x_abs) * effective_scale
            py_top = anchor_py_base - (y_top - y_abs) * effective_scale
            py_bottom = anchor_py_base - (y_bottom - y_abs) * effective_scale
            self.canvas.create_line(px, py_top, px, py_bottom, width=3, fill='cyan')

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
