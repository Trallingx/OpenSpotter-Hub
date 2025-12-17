import math
import tkinter as tk
from tkinter import messagebox
from SpotterFunctions import read_entries, dict_to_list ,read_entries_as_dict
from input_configs import get_keys
from input_configs import GLOBAL_INPUT_LABELS, GRID_INPUT_LABELS, CLEANING_INPUT_LABELS, WASHING_INPUT_LABELS

class CanvasDrawer:
    def __init__(self, gui, poll_interval=500):
        self.gui = gui
        self.canvas = gui.canvas
        self.poll_interval = poll_interval
        self._prev_snapshot = None
        self._last_exceed_state = False

    def start(self):
        # start polling loop
        self.gui.after(self.poll_interval, self._poll)

    def refresh(self):
        """Force a redraw using current inputs (ignores snapshot equality)."""
        try:
            snapshot = self._collect_data()
        except Exception:
            snapshot = None
        try:
            self.draw(snapshot)
        except Exception:
            pass

    def _poll(self):
        try:
            snapshot = self._collect_data()
        except Exception:
            snapshot = None

        if snapshot != self._prev_snapshot:
            self._prev_snapshot = snapshot
            try:
                self.draw(snapshot)
            except Exception:
                pass

        # schedule next poll
        self.gui.after(self.poll_interval, self._poll)

    def _collect_data(self):
        # Collect global inputs
        global_vals = None
        try:
            global_vals = read_entries(self.gui.entry)
        except Exception:
            global_vals = None

        grids = []
        cleaning_grids = []
        washing_data = []
        for idx in range(1, 4):
            grid_attr = f'grid_{idx}'
            grid_obj = getattr(self.gui, grid_attr, None)
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                try:
                    vals = read_entries(grid_obj.grid_entry)
                    vals_cleaning = read_entries(grid_obj.cleaning_entry)
                    vals_washing = read_entries(grid_obj.washing_entry)
                    grids.append((idx, vals))
                    # Only include cleaning grid if enabled
                    if hasattr(grid_obj, 'cleaning_enabled') and grid_obj.cleaning_enabled.get():
                        cleaning_grids.append((idx, vals_cleaning))
                    # Only include washing data if enabled
                    if hasattr(grid_obj, 'washing_enabled') and grid_obj.washing_enabled.get():
                        washing_data.append((idx, vals_washing))
                except Exception:
                    pass

        return {'global': global_vals, 'grids': grids, 'cleaning_grids': cleaning_grids, 'washing_data': washing_data}

    def draw(self, snapshot):
        self.canvas.delete('all')
        if snapshot is None:
            return

        global_vals = snapshot.get('global')
        grids = snapshot.get('grids', [])
        cleaning_grids = snapshot.get('cleaning_grids', [])
        washing_data = snapshot.get('washing_data', [])

        
        points = []  # list of (x,y,grid_index, dispense_volume)

        # Global offsets: expect [x_abs, y_abs, x_offset, y_offset]
        if not global_vals or len(global_vals) < 4:
            # nothing to draw
            return
        #print("try to start")
        global_vals_dict = read_entries_as_dict(self.gui.entry, GLOBAL_INPUT_LABELS)
        #print(global_vals_dict)
        x_abs = float(global_vals_dict['x_cord_of_y_line'])
        #print("one read successss")
        y_abs = float(global_vals_dict['y_cord_of_x_line'])
        first_x_off = float(global_vals_dict['tuning_offset_x'])
        first_y_off = float(global_vals_dict['tuning_offset_y'])
        #print("reading success")
        # inner acceptance rectangle scaled proportionally
        # rectangle parameters (mm) - 200x133.3 mm (maintains 600x400 px aspect ratio from original 300x400)
        inner_w =   float(global_vals_dict['acceptance_square_x'])
        inner_h =   float(global_vals_dict['acceptance_square_y'])
        rect_w =    float(global_vals_dict['base_square_x'])
        rect_h =    float(global_vals_dict['base_square_y'])
        grey_w =    float(global_vals_dict['grey_square_x']) 
        grey_h =    float(global_vals_dict['grey_square_y'])

        # We'll collect per-grid extents to decide coloring
        # store (grid_idx, start_x_abs, start_y_abs, grid_width_mm, grid_height_mm)
        grid_extents = []
        grid_sizes = []

        for grid_idx, vals in grids:
            try:
                # vals expected: rows, cols, x_step, y_step, dispense, loading, leftovers, z_adj, droplet_time, x_offset, y_offset
                rows = int(vals[0])
                cols = int(vals[1])
                x_step = float(vals[2])
                y_step = float(vals[3])
                grid_x_off = float(vals[9]) if len(vals) > 9 else 0.0
                grid_y_off = float(vals[10]) if len(vals) > 10 else 0.0

                start_x = x_abs + first_x_off + grid_x_off
                start_y = y_abs + first_y_off + grid_y_off

                # compute physical grid span (mm) between first and last points: (n-1)*step
                grid_width_mm = (cols - 1) * x_step if cols > 0 else 0.0
                grid_height_mm = (rows - 1) * y_step if rows > 0 else 0.0
                #print(f"Grid {grid_idx}: start=({start_x}, {start_y}), size=({grid_width_mm}, {grid_height_mm})")
                # append absolute start positions and sizes
                grid_extents.append((grid_idx, start_x, start_y, grid_width_mm, grid_height_mm))
                # store rows/cols and physical sizes (mm) for display
                grid_sizes.append((grid_idx, cols, rows, grid_width_mm, grid_height_mm))

                # read dispense volume for this grid (if present)
                try:
                    dispense = float(vals[4]) if len(vals) > 4 else 0.0
                except Exception:
                    dispense = 0.0

                for r in range(rows):
                    for c in range(cols):
                        x = start_x + c * x_step
                        y = start_y + r * y_step
                        points.append((x, y, grid_idx, dispense))
            except Exception:
                continue

        if not points:
            return

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        # include rectangle corners so it's always visible and considered for scaling
        rect_x = x_abs + first_x_off
        rect_y = y_abs + first_y_off
        xs.extend([rect_x, rect_x + rect_w])
        ys.extend([rect_y, rect_y + rect_h])

        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        c_w = int(self.canvas['width'])
        c_h = int(self.canvas['height'])
        margin = 10
        # reserve some horizontal pixels on the left so content doesn't overlap the scale bar
        reserved_left_px = 100
        content_margin = margin + reserved_left_px
        # reserve some vertical pixels at the bottom so content doesn't not overlap bottom UI
        reserved_bottom_px = 100
        content_margin_y = margin + reserved_bottom_px

        range_x = maxx - minx
        range_y = maxy - miny
        if range_x == 0:
            range_x = 1
        if range_y == 0:
            range_y = 1

        scale_x = (c_w - 2 * margin) / range_x
        scale_y = (c_h - 2 * margin) / range_y
        scale = min(scale_x, scale_y)

        # Determine whether any grid exceeds inner acceptance rectangle
        # apply inset: require a minimum 0.5 mm inset from left/bottom for acceptance
        inset = 0.5
        # visual inner rectangle (centered)
        inner_vis_x = rect_x + (rect_w - inner_w) / 2.0
        inner_vis_y = rect_y + (rect_h - inner_h) / 2.0
        # logical inner origin for acceptance checks (shifted right/up by inset)
        inner_origin_x = inner_vis_x -0.1
        inner_origin_y = inner_vis_y -0.1

        exceed = False
        for (g_idx, s_x, s_y, gw_mm, gh_mm) in grid_extents:
            # grid absolute start/end positions
            start_abs_x = s_x #+0.5
            start_abs_y = s_y #+0.5
            #print(f"Grid {g_3idx} start: ({start_abs_x}, {start_abs_y}), size: ({gw_mm}, {gh_mm})")
            end_abs_x = start_abs_x + gw_mm
            end_abs_y = start_abs_y + gh_mm 
            # if grid starts before inner origin or ends beyond inner origin + inner size -> exceed
            if start_abs_x <= inner_origin_x or start_abs_y <= inner_origin_y or end_abs_x >= (inner_origin_x + inner_w + 0.1) or end_abs_y >= (inner_origin_y + inner_h + 0.15):
                exceed = True
                break

        # allow user override of pixels-per-mm via GUI slider: 0 => auto
        px_per_mm_override = getattr(self.gui, 'px_per_mm', 0.0) or 0.0

        # choose a readable mm scale (used for the general scale bar and the square-specific bar)
        def choose_scale_mm(scale_px):
            candidates = [1, 2, 5, 10, 20, 50, 100]
            for mm in candidates:
                if 50 <= mm * scale_px <= 150:
                    return mm
            return candidates[2]

        # effective scale: if user provided px/mm use that, else use computed fit scale
        effective_scale = px_per_mm_override if px_per_mm_override > 0 else scale

        chosen_mm = choose_scale_mm(effective_scale)
        px_len = chosen_mm * effective_scale

        # map and draw
        radius = max(3, int(min(6, effective_scale * 0.1)))

        color_map = {1: 'green', 2: 'orange', 3: 'blue'}

        # Background: always white
        bg_color = 'white'
        self.canvas.create_rectangle(0, 0, c_w, c_h, fill=bg_color, outline='')
        
        # Show popup if grid exceeds dimensions
        if exceed and not getattr(self, '_last_exceed_state', False):
            self._show_exceed_popup()
        self._last_exceed_state = exceed

        # draw outer allowed rectangle (20x40)
        # anchor scaling at bottom-left corner of the outer rectangle
        anchor_x = rect_x
        anchor_y = rect_y
        anchor_px_base = content_margin + (anchor_x - minx) * effective_scale
        anchor_py_base = c_h - (content_margin_y + (anchor_y - miny) * effective_scale)
        #print( minx, miny, maxx, maxy)
        #print(f"Anchor px: ({anchor_px_base}, {anchor_py_base}), effective scale: {effective_scale}")
        
        # draw grey square (40x70mm) centered on the black square, between red background and white inner rect
        
        grey_x = rect_x + (rect_w - grey_w) / 2.0
        grey_y = rect_y + (rect_h - grey_h) / 2.0
        gx1 = anchor_px_base + (grey_x - anchor_x) * effective_scale
        gy1 = anchor_py_base - (grey_y - anchor_y) * effective_scale
        gx2 = anchor_px_base + (grey_x + grey_w - anchor_x) * effective_scale
        gy2 = anchor_py_base - (grey_y + grey_h - anchor_y) * effective_scale
        grey_x1, grey_x2 = min(gx1, gx2), max(gx1, gx2)
        grey_y1, grey_y2 = min(gy1, gy2), max(gy1, gy2)
        self.canvas.create_rectangle(grey_x1, grey_y1, grey_x2, grey_y2, fill='grey', outline='')

        # draw inner acceptance rectangle (centered inside outer) (19x39)
        # visually keep it centered (inset is enforced logically only)
        inner_x = rect_x + (rect_w - inner_w) / 2.0
        inner_y = rect_y + (rect_h - inner_h) / 2.0
        ix1 = anchor_px_base + (inner_x - anchor_x) * effective_scale
        iy1 = anchor_py_base - (inner_y - anchor_y) * effective_scale
        ix2 = anchor_px_base + (inner_x + inner_w - anchor_x) * effective_scale
        iy2 = anchor_py_base - (inner_y + inner_h - anchor_y) * effective_scale
        i_x1, i_x2 = min(ix1, ix2), max(ix1, ix2)
        i_y1, i_y2 = min(iy1, iy2), max(iy1, iy2)
        # fill inner area with white so points are visible
        self.canvas.create_rectangle(i_x1, i_y1, i_x2, i_y2, fill='white', outline='darkgreen', width=2)
        
        # draw outer black border rectangle (20x40mm, centered above inner)
        # The black border is the outer 20x40mm rectangle
        outer_bx1 = anchor_px_base + (rect_x - anchor_x) * effective_scale
        outer_by1 = anchor_py_base - (rect_y - anchor_y) * effective_scale
        outer_bx2 = anchor_px_base + (rect_x + rect_w - anchor_x) * effective_scale
        outer_by2 = anchor_py_base - (rect_y + rect_h - anchor_y) * effective_scale
        black_x1, black_x2 = min(outer_bx1, outer_bx2), max(outer_bx1, outer_bx2)
        black_y1, black_y2 = min(outer_by1, outer_by2), max(outer_by1, outer_by2)


        # read mapping entries from GUI (linear mapping v -> diameter in mm)
        try:
            v1 = float(getattr(self.gui, 'disp_v1_entry').get())
            d1 = float(getattr(self.gui, 'disp_d1_entry').get())
            v2 = float(getattr(self.gui, 'disp_v2_entry').get())
            d2 = float(getattr(self.gui, 'disp_d2_entry').get())
            # compute slope/intercept
            if abs(v2 - v1) > 1e-9:
                m = (d2 - d1) / (v2 - v1)
                b = d1 - m * v1
            else:
                m = 0.0
                b = d1
        except Exception:
            # fallback to a small constant diameter
            m = 0.0
            b = 0.6

        # draw points on top; circle diameter derived from dispense via linear mapping
        for x, y, g, dispense in points:
            px = anchor_px_base + (x - anchor_x) * effective_scale
            py = anchor_py_base - (y - anchor_y) * effective_scale
            # diameter in mm
            diam_mm = m * dispense + b
            if diam_mm < 0:
                diam_mm = 0.0
            # px radius
            rad_px = max(1, int((diam_mm / 2.0) * effective_scale))
            # clamp radius for visibility
            rad_px = min(max(rad_px, 1), 80)
            color = color_map.get(g, 'black')
            self.canvas.create_oval(px - rad_px, py - rad_px, px + rad_px, py + rad_px, fill=color, outline='')
        
        # Draw cleaning grids with proper anchor-relative positioning
        for grid_idx, cvals in cleaning_grids:
            try:
                # cleaning_entry order: rows, cols, x_step, y_step, dispense, x_offset, y_offset, spots_before_cleaning
                crow = int(cvals[0]) if len(cvals) > 0 else 0
                ccol = int(cvals[1]) if len(cvals) > 1 else 0
                cxs = float(cvals[2]) if len(cvals) > 2 else 0.0  # x_step
                cys = float(cvals[3]) if len(cvals) > 3 else 0.0  # y_step
                # dispense at index 4 (not used for cleaning grid visualization currently)
                csx = float(cvals[5]) if len(cvals) > 5 else 0.0   # x_offset
                csy = float(cvals[6]) if len(cvals) > 6 else 0.0   # y_offset
                
                if crow == 0 or ccol == 0:
                    continue
                
                # Get the grid's start position (anchor point + offsets)
                # The cleaning grid should be positioned relative to the main grid
                for grid_i, grid_vals in grids:
                    if grid_i == grid_idx:
                        # Grid info: rows, cols, x_step, y_step, dispense, loading, leftovers, z_adj, droplet_time, x_offset, y_offset
                        grid_x_off = float(grid_vals[9]) if len(grid_vals) > 9 else 0.0
                        grid_y_off = float(grid_vals[10]) if len(grid_vals) > 10 else 0.0
                        
                        # Cleaning grid absolute start position
                        cstart_x = x_abs + first_x_off + grid_x_off + csx
                        cstart_y = y_abs + first_y_off + grid_y_off + csy
                        
                        # Draw cleaning points
                        for r in range(crow):
                            for c in range(ccol):
                                cx = cstart_x + c * cxs
                                cy = cstart_y + r * cys
                                cpx = anchor_px_base + (cx - anchor_x) * effective_scale
                                cpy = anchor_py_base - (cy - anchor_y) * effective_scale 
                                s = max(2, int(0.08 * effective_scale))
                                self.canvas.create_rectangle(cpx - s, cpy - s, cpx + s, cpy + s, fill='purple', outline='black')
                        
                        # Draw outline around the cleaning grid
                        cg_width = (ccol - 1) * cxs if ccol > 1 else 0.0
                        cg_height = (crow - 1) * cys if crow > 1 else 0.0
                        gx1 = anchor_px_base + (cstart_x - anchor_x) * effective_scale
                        gy1 = anchor_py_base - (cstart_y - anchor_y) * effective_scale
                        gx2 = anchor_px_base + (cstart_x + cg_width - anchor_x) * effective_scale
                        gy2 = anchor_py_base - (cstart_y + cg_height - anchor_y) * effective_scale
                        self.canvas.create_rectangle(min(gx1, gx2), min(gy1, gy2), max(gx1, gx2), max(gy1, gy2), outline='purple', width=2)
                        break
            except Exception as e:
                pass

        # Draw washing column line if washing data is available
        for grid_idx, wvals in washing_data:
            try:
                # washing_entry order: depth, speed, upper_bound, lower_bound, column_offset, after_x_spots, cycles
                washing_upper = float(wvals[2]) if len(wvals) > 2 else 0.0
                washing_lower = float(wvals[3]) if len(wvals) > 3 else 0.0
                washing_col_offset = float(wvals[4]) if len(wvals) > 4 else 0.0
                
                # Get the grid's x position for reference
                for grid_i, grid_vals in grids:
                    if grid_i == grid_idx:
                        grid_x_off = float(grid_vals[9]) if len(grid_vals) > 9 else 0.0
                        grid_y_off = float(grid_vals[10]) if len(grid_vals) > 10 else 0.0
                        
                        # Washing column x position: grid start x + column offset
                        wash_x = x_abs + first_x_off + grid_x_off + washing_col_offset
                        wash_y_top = y_abs + first_y_off + grid_y_off + washing_upper
                        wash_y_bottom = y_abs + first_y_off + grid_y_off + washing_lower
                        
                        # Convert to pixel coordinates
                        wash_px = anchor_px_base + (wash_x - anchor_x) * effective_scale
                        wash_py_top = anchor_py_base - (wash_y_top - anchor_y) * effective_scale
                        wash_py_bottom = anchor_py_base - (wash_y_bottom - anchor_y) * effective_scale
                        
                        # Draw vertical line from lower to upper bound
                        self.canvas.create_line(wash_px, wash_py_top, wash_px, wash_py_bottom, width=3, fill='cyan')
                        break
            except Exception as e:
                pass

        # draw scale bars (choose mm length that fits)
        mm_per_px = 1.0 / effective_scale

        # horizontal bar at bottom-left inside margin (keep using original margin so bar stays visible)
        bar_x = margin + 10
        bar_y = c_h - margin / 2
        self.canvas.create_line(bar_x, bar_y, bar_x + px_len, bar_y, width=4, fill='black')
        self.canvas.create_text(bar_x + px_len / 2, bar_y - 10, text=f"{chosen_mm} mm", fill='black')


        # vertical bar at bottom-left
        vbar_x = margin + 5
        vbar_y = c_h - margin - px_len
        self.canvas.create_line(vbar_x, c_h - margin, vbar_x, c_h - margin - px_len, width=4, fill='black')
        self.canvas.create_text(vbar_x + 20, c_h - margin - px_len / 2, text=f"{chosen_mm} mm", fill='black', angle=90)

        # Top-right: list grid sizes (cols x rows)
        if grid_sizes:
            # Show physical sizes in mm (cols * x_step, rows * y_step)
            lines = [f"Grid {g}: {w:.1f} mm x {h:.1f} mm ({cols}x{rows})" for (g, cols, rows, w, h) in grid_sizes]
            text_str = "\n".join(lines)
            tx = c_w - margin - 5
            ty = margin + 5
            # create text first to measure bbox
            text_id = self.canvas.create_text(tx, ty, text=text_str, anchor='ne', fill='black')
            bbox = self.canvas.bbox(text_id)
            if bbox:
                pad = 6
                x0, y0, x1, y1 = bbox
                # draw semi-opaque white rectangle behind text
                rect_id = self.canvas.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad, fill='white', outline='black')
                # raise text above rectangle
                self.canvas.tag_raise(text_id, rect_id)

        # Draw black border rectangle on top of everything (outer 20x40mm rectangle)
        self.canvas.create_rectangle(black_x1, black_y1, black_x2, black_y2, outline='black', width=2)

    def _show_exceed_popup(self):
        """Show a popup when grid exceeds 19x39mm dimensions."""
        popup = tk.Toplevel(self.gui)
        popup.title("Grid Dimension Alert")
        popup.attributes('-topmost', True)  # Keep on top
        
        # Create a label with large bold text
        label = tk.Label(
            popup,
            text="GRID EXCEEDS DIMENSIONS",
            font=("Arial", 24, "bold"),
            fg="red",
            padx=20,
            pady=20
        )
        label.pack()
        
        # Add a close button
        close_btn = tk.Button(
            popup,
            text="OK",
            command=popup.destroy,
            font=("Arial", 14),
            padx=20,
            pady=10
        )
        close_btn.pack(pady=10)
        
        # Center the popup on screen
        popup.update_idletasks()
        width = popup.winfo_width()
        height = popup.winfo_height()
        x = popup.winfo_screenwidth() // 2 - width // 2
        y = popup.winfo_screenheight() // 2 - height // 2
        popup.geometry(f'{width}x{height}+{x}+{y}')
