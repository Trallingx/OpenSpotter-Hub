import math
from SpotterFunctions import read_entries, dict_to_list


class CanvasDrawer:
    def __init__(self, gui, poll_interval=500):
        self.gui = gui
        self.canvas = gui.canvas
        self.poll_interval = poll_interval
        self._prev_snapshot = None

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
            #print("Global values:", global_vals)
        except Exception:
            global_vals = None

        grids = []
        cleaning_grids = []
        for idx in range(1, 4):
            grid_attr = f'grid_{idx}'
            grid_obj = getattr(self.gui, grid_attr, None)
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                try:
                    vals = read_entries(grid_obj.grid_entry)
                    vals_cleaning = read_entries(grid_obj.cleaning_entry)
                    grids.append((idx, vals))
                    cleaning_grids.append((idx, vals_cleaning))
                except Exception:
                    pass

        return {'global': global_vals, 'grids': grids}

    def draw(self, snapshot):
        self.canvas.delete('all')
        if snapshot is None:
            return

        global_vals = snapshot.get('global')
        grids = snapshot.get('grids', [])

        points = []  # list of (x,y,grid_index, dispense_volume)

        # Global offsets: expect [x_abs, y_abs, x_offset, y_offset]
        if not global_vals or len(global_vals) < 4:
            # nothing to draw
            return

        x_abs = float(global_vals[0])
        y_abs = float(global_vals[1])
        first_x_off = float(global_vals[2])
        first_y_off = float(global_vals[3])

        # rectangle parameters (mm) - 200x133.3 mm (maintains 600x400 px aspect ratio from original 300x400)
        rect_w = 20
        rect_h = 40
        # inner acceptance rectangle scaled proportionally
        inner_w = 19
        inner_h = 39

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
        reserved_left_px = 50
        content_margin = margin + reserved_left_px
        # reserve some vertical pixels at the bottom so content doesn't not overlap bottom UI
        reserved_bottom_px = 20
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

        # Background: green if all inside, red if any exceed
        bg_color = 'green' if not exceed else 'red'
        self.canvas.create_rectangle(0, 0, c_w, c_h, fill=bg_color, outline='')

        # draw outer allowed rectangle (20x40)
        # anchor scaling at bottom-left corner of the outer rectangle
        anchor_x = rect_x
        anchor_y = rect_y
        anchor_px_base = content_margin + (anchor_x - minx) * effective_scale
        anchor_py_base = c_h - (content_margin_y + (anchor_y - miny) * effective_scale)
        #print( minx, miny, maxx, maxy)
        #print(f"Anchor px: ({anchor_px_base}, {anchor_py_base}), effective scale: {effective_scale}")
        rx1 = anchor_px_base + (rect_x - anchor_x) * effective_scale
        ry1 = anchor_py_base - (rect_y - anchor_y) * effective_scale
        rx2 = anchor_px_base + (rect_x + rect_w - anchor_x) * effective_scale
        ry2 = anchor_py_base - (rect_y + rect_h - anchor_y) * effective_scale
        #print(f"Outer rect px: ({rx1}, {ry1}) to ({rx2}, {ry2})")
        # normalize coordinates
        x1, x2 = min(rx1, rx2), max(rx1, rx2)
        y1, y2 = min(ry1, ry2), max(ry1, ry2)
        self.canvas.create_rectangle(x1, y1, x2, y2, outline='black', width=2)

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

        # draw cleaning grid(s) if present
        self.canvas.create_oval(anchor_px_base -5, anchor_py_base -5, anchor_px_base + 5, anchor_py_base + 5, fill= color, outline='')
        try:
            # support multiple per-grid cleaning configs (preferred)
            cgs = getattr(self.gui, 'cleaning_grids', None)
            #if cgs and isinstance(cgs, dict):
            for _idx, cg in grids:
                    try:
                        crow = 10
                        ccol = 10
                        cxs = 1
                        cys = 1
                        csx = 15
                        csy = 15
                    except Exception:
                        continue
                    # draw points for cleaning grid (use purple color)
                    print("Drawing cleaning grid:", crow, ccol, cxs, cys, csx, csy)
                    for r in range(crow):
                        for c in range(ccol):
                            cx = csx + c * cxs
                            cy = csy + r * cys
                            cpx = anchor_px_base + (cx - anchor_x) * effective_scale
                            cpy = anchor_py_base - (cy - anchor_y) * effective_scale 
                            s = max(2, int(0.08 * effective_scale))
                            self.canvas.create_rectangle(cpx - s, cpy - s, cpx + s, cpy + s, fill='purple', outline='black')
                            print("painted cleaning point at:", cpx, cpy)
                    # draw an outline around the cleaning grid
                    cg_width = (ccol - 1) * cxs if ccol > 0 else 0.0
                    cg_height = (crow - 1) * cys if crow > 0 else 0.0
                    gx1 = anchor_px_base + (csx - anchor_x) * effective_scale
                    gy1 = anchor_py_base - (csy - anchor_y) * effective_scale
                    gx2 = anchor_px_base + (csx + cg_width - anchor_x) * effective_scale
                    gy2 = anchor_py_base - (csy + cg_height - anchor_y) * effective_scale
                    print("ANCHOR:", anchor_px_base, anchor_py_base, "CLEANING GRID BOX:", gx1, gy1, gx2, gy2, "--", csx, csy, cg_width, cg_height, effective_scale,"--", anchor_x, anchor_y)
                    self.canvas.create_rectangle(min(gx1,gx2), min(gy1,gy2), max(gx1,gx2), max(gy1,gy2), outline='purple', width=2)
                    
            else:
                # fallback to single cleaning_grid for backward compatibility
                cg = getattr(self.gui, 'cleaning_grid', None)
                if cg:
                    crow = int(cg.get('rows', 0))
                    ccol = int(cg.get('cols', 0))
                    cxs = float(cg.get('x_step', 1.0))
                    cys = float(cg.get('y_step', 1.0))
                    csx = float(cg.get('start_x', 0.0))
                    csy = float(cg.get('start_y', 0.0))
                    for r in range(crow):
                        for c in range(ccol):
                            cx = csx + c * cxs
                            cy = csy + r * cys
                            cpx = anchor_px_base + (cx - anchor_x) * effective_scale
                            cpy = anchor_py_base - (cy - anchor_y) * effective_scale
                            s = max(2, int(0.08 * effective_scale))
                            self.canvas.create_rectangle(cpx - s, cpy - s, cpx + s, cpy + s, fill='purple', outline='black')
                    cg_width = (ccol - 1) * cxs if ccol > 0 else 0.0
                    cg_height = (crow - 1) * cys if crow > 0 else 0.0
                    gx1 = anchor_px_base + (csx - anchor_x) * effective_scale
                    gy1 = anchor_py_base - (csy - anchor_y) * effective_scale
                    gx2 = anchor_px_base + (csx + cg_width - anchor_x) * effective_scale
                    gy2 = anchor_py_base - (csy + cg_height - anchor_y) * effective_scale
                    self.canvas.create_rectangle(min(gx1,gx2), min(gy1,gy2), max(gx1,gx2), max(gy1,gy2), outline='purple', width=2)
        except Exception:
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
