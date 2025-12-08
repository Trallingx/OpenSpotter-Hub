import os
from tkinter import *
from tkinter import filedialog
import tkinter as tk
from tkinter.ttk import *
from PIL import ImageTk, Image


from grid import *
from create_gcode import *
from canvas_drawer import CanvasDrawer

class DropletGui(tk.Tk):
    def __init__(self, config_dir):
        super(DropletGui, self).__init__()
        self.config_dir = config_dir
        self.global_input_frame = None
        self.grid_1 = None
        self.grid_2 = None
        self.grid_3 = None
        self.canvas_frame = None
        self.canvas = None

        self.entry = []
        self.grid_count = 0

        # Setting up basic UI structure
        self.title('SDU-Spotter')
        # start window in windowed-fullscreen (maximized) on Windows
        try:
            self.state('zoomed')
        except Exception:
            pass

        self.main_frame = tk.Frame(self)
        self.main_frame.grid()

        # left container holds the main UI (global inputs, pictures, canvas, buttons, grids)
        self.left_frame = tk.Frame(self.main_frame)
        self.left_frame.grid(row=0, column=0, sticky='nsew')

        # global setting (blue)
        self.global_frame = tk.Frame(self.left_frame)
        self.global_frame.grid(row=1, column=0)

        self.global_input_frame = tk.Frame(self.global_frame)
        self.global_input_frame.config(bg="lightblue", border=5)
        self.global_input_frame.grid(row=1, column=0)

        info_text = tk.Label(self.left_frame, text="Lorem ipsum dolor sit amet")
        info_text.grid(row=0, column=0, columnspan=3)

        # Adding Pictures, that define inputs
        self.picture_frame = tk.Frame(self.left_frame)
        self.picture_frame.grid(row=1, column=1)
        self.adding_pictures()

        # Canvas column on the right (inside left container)
        self.canvas_frame = tk.Frame(self.left_frame)
        self.canvas_frame.grid(row=0, column=2, rowspan=2, padx=10, pady=10)
        
        canvas_label = tk.Label(self.canvas_frame, text="Canvas Area")
        canvas_label.pack()
        
        self.canvas = tk.Canvas(self.canvas_frame, width=600, height=400, bg="white")
        self.canvas.pack()

        # px/mm control for canvas: 0 = auto, >0 overrides computed px/mm
        # default startup autoscale is 7 px/mm
        self.px_per_mm = 7.0
        def _on_px_per_mm(v):
            try:
                val = float(v)
            except Exception:
                val = 0.0
            # treat zero as auto
            self.px_per_mm = val if val > 0 else 0.0
            # trigger an immediate canvas update if the drawer exists
            try:
                if hasattr(self, 'canvas_drawer') and self.canvas_drawer is not None:
                    # call internal poll which will collect data and redraw if changed
                    self.canvas_drawer._poll()
            except Exception:
                pass

        self.px_scale = tk.Scale(self.canvas_frame, from_=0, to=200, orient='horizontal', label='px / mm (0=auto)', command=_on_px_per_mm)
        self.px_scale.set(7)
        self.px_scale.pack(fill='x', padx=5, pady=5)

        # Update canvas button for manual refresh (useful if slider release doesn't redraw)
        def _manual_refresh():
            try:
                if hasattr(self, 'canvas_drawer') and self.canvas_drawer is not None:
                    self.canvas_drawer.refresh()
            except Exception:
                pass

        update_btn = tk.Button(self.canvas_frame, text='Update canvas', command=_manual_refresh)
        update_btn.pack(fill='x', padx=5, pady=(0,6))

        # Dispense -> diameter mapping entries
        map_frame = tk.Frame(self.canvas_frame)
        map_frame.pack(fill='x', padx=5)

        lbl = tk.Label(map_frame, text='Dispense→Diameter mapping (volume ml -> diameter mm)')
        lbl.pack(anchor='w')

        rowf = tk.Frame(map_frame)
        rowf.pack(fill='x')
        tk.Label(rowf, text='v1:').pack(side='left')
        self.disp_v1_entry = tk.Entry(rowf, width=8)
        self.disp_v1_entry.insert(0, '0.04')
        self.disp_v1_entry.pack(side='left', padx=(2,8))
        tk.Label(rowf, text='d1 (mm):').pack(side='left')
        self.disp_d1_entry = tk.Entry(rowf, width=8)
        self.disp_d1_entry.insert(0, '0.6')
        self.disp_d1_entry.pack(side='left', padx=(2,8))

        rowf2 = tk.Frame(map_frame)
        rowf2.pack(fill='x', pady=(4,0))
        tk.Label(rowf2, text='v2:').pack(side='left')
        self.disp_v2_entry = tk.Entry(rowf2, width=8)
        self.disp_v2_entry.insert(0, '0.08')
        self.disp_v2_entry.pack(side='left', padx=(2,8))
        tk.Label(rowf2, text='d2 (mm):').pack(side='left')
        self.disp_d2_entry = tk.Entry(rowf2, width=8)
        self.disp_d2_entry.insert(0, '1.2')
        self.disp_d2_entry.pack(side='left', padx=(2,8))

        # start canvas drawer
        try:
            self.canvas_drawer = CanvasDrawer(self)
            self.canvas_drawer.start()
        except Exception:
            pass

        # Adding buttons (placed inside left container)
        self.button_frame = tk.Frame(self.left_frame)
        self.button_frame.grid(row=2, columnspan=3)
        self.create_buttons()

    def create_buttons(self):
        add_grid_button = Button(self.button_frame, text="create grid", command=self.instance_grid)
        add_grid_button.grid(row=3, column=1)

        remove_grid_button = Button(self.button_frame, text="remove grid", command=self.subtract_grid)
        remove_grid_button.grid(row=3, column=2)

        check_input_button = Button(self.button_frame, text="check input", command=self.check_inputs)
        check_input_button.grid(row=5, column=0)

        create_gcode_button = Button(self.button_frame, text="create G-code", command=self.save_file)
        create_gcode_button.grid(row=5, column=1)

        check_save_button = Button(self.button_frame, text="save defaults", command=self.check_saves)
        check_save_button.grid(row=5, column=2)

    def instance_grid(self):
        match self.grid_count:
            case 0:
                self.grid_count += 1
                self.grid_1 = Grid(self.left_frame, 4, 0, os.path.join(self.config_dir, "config_grid_1.json"), "lightgreen", self.config_dir)
            case 1:
                self.grid_count += 1
                self.grid_2 = Grid(self.left_frame, 4, 1, os.path.join(self.config_dir, "config_grid_2.json"), "orange", self.config_dir)
            case 2:
                self.grid_count += 1
                self.grid_3 = Grid(self.left_frame, 4, 2, os.path.join(self.config_dir, "config_grid_3.json"), "blue", self.config_dir)
            case 3:
                open_secondary_window("Cannot add more grids")

    def check_grid_state(self, states):
        match states:
            case ['0']:
                pass  # no grid
            case ['1']:
                self.instance_grid()
            case ['2']:
                self.instance_grid()
                self.instance_grid()
            case ['3']:
                self.instance_grid()
                self.instance_grid()
                self.instance_grid()

    def subtract_grid(self):
        match self.grid_count:
            case 0:
                open_secondary_window("No more grids available")
            case 1:
                open_secondary_window("One grid required")
            case 2:
                self.grid_count -= 1
                self.grid_2.master_input_frame.destroy()
                # remove any per-grid cleaning controls for grid 2
            case 3:
                self.grid_count -= 1
                self.grid_3.master_input_frame.destroy()

    def check_saves(self):
        # Write current grid count to state file
        write_state(self.grid_count, self.config_dir)

        # Always save global defaults
        save_defaults(self.entry, 0, 0, os.path.join(self.config_dir, "config_global.json"))

        # Save each grid config that exists (supports grid_1..grid_N)
        for i in range(1, self.grid_count + 1):
            grid_attr = f'grid_{i}'
            grid_obj = getattr(self, grid_attr, None)
            print("tried saving", grid_attr, grid_obj)
            if grid_obj and hasattr(grid_obj, 'grid_entry'):
                cfg_path = os.path.join(self.config_dir, f'config_grid_{i}.json')
                save_defaults(grid_obj.grid_entry, grid_obj.cleaning_entry, grid_obj.washing_entry, cfg_path)
                print(f"✅ Saved grid {i} defaults to {cfg_path}")

    def adding_pictures(self):
        picture_label = tk.Label(self.picture_frame, text="Build plate information")
        picture_label.grid()

        image = Image.open(os.path.join(self.config_dir, "buildplate.png"))
        resized_image = image.resize((359+20, 307+20))
        photo = ImageTk.PhotoImage(resized_image)

        label_picture = Label(self.picture_frame, image=photo)
        label_picture.image = photo
        label_picture.grid(padx=20, pady=5)

        image = Image.open(os.path.join(self.config_dir, "spots.png"))
        photo = ImageTk.PhotoImage(image)

        spots_picture = Label(self.global_frame, image=photo)
        spots_picture.image = photo
        spots_picture.grid(row=0, column=0)

    def save_file(self):
        save_file(self.grid_count, self)

    def check_inputs(self):
        check_input(self)


def open_secondary_window(text):
    secondary_window = tk.Toplevel()
    secondary_window.title("Secondary Window")
    secondary_window.config(width=400, height=200)
    # Create a button to close (destroy) this window.
    button_close = Button(
        secondary_window,
        text=text,
        command=secondary_window.destroy
    )
    button_close.place(x=75, y=75)


def check_input(gui):
    global_entry = read_entries(gui.entry)
    # Read global offsets (for positioning, not sizing)
    first_x_off = float(global_entry[2]) if len(global_entry) > 2 else 0.0
    first_y_off = float(global_entry[3]) if len(global_entry) > 3 else 0.0
    # absolute build plate origin (for rectangle positioning)
    x_abs = float(global_entry[0]) if len(global_entry) > 0 else 0.0
    y_abs = float(global_entry[1]) if len(global_entry) > 1 else 0.0

    # rectangle params (must match canvas_drawer)
    rect_w = 20.0
    rect_h = 40.0
    # inner acceptance rectangle dimensions (mm)
    inner_w = 19.0
    inner_h = 39.0
    # require minimum inset from left and bottom (mm)
    inset_lb = 0.5

    exceeded = []

    # Helper to check a grid safely
    def check_grid_obj(grid_obj, grid_idx):
        try:
            vals = read_entries(grid_obj.entry)
        except Exception:
            return
        # vals expected: rows, cols, x_step, y_step, ..., grid_offset_x, grid_offset_y
        try:
            rows = int(vals[0])
            cols = int(vals[1])
            x_step = float(vals[2])
            y_step = float(vals[3])
            grid_x_off = float(vals[9]) if len(vals) > 9 else 0.0
            grid_y_off = float(vals[10]) if len(vals) > 10 else 0.0
        except Exception:
            return

        # Compute grid physical span (independent per-grid): (n-1)*step between first and last
        grid_width = (cols - 1) * x_step if cols > 0 else 0.0
        grid_height = (rows - 1) * y_step if rows > 0 else 0.0

        # compute absolute rectangle inner origin (visual center, logical inset applied below)
        rect_x = x_abs + first_x_off
        rect_y = y_abs + first_y_off
        inner_vis_x = rect_x + (rect_w - inner_w) / 2.0
        inner_vis_y = rect_y + (rect_h - inner_h) / 2.0
        inner_origin_x = inner_vis_x + inset_lb
        inner_origin_y = inner_vis_y + inset_lb

        # grid absolute start/end positions
        start_abs_x = rect_x + grid_x_off
        start_abs_y = rect_y + grid_y_off
        end_abs_x = start_abs_x + grid_width
        end_abs_y = start_abs_y + grid_height

        # if grid starts before inner origin or ends beyond inner origin + inner size -> exceeded
        if start_abs_x < inner_origin_x or start_abs_y < inner_origin_y or end_abs_x > (inner_origin_x + inner_w) or end_abs_y > (inner_origin_y + inner_h):
            exceeded.append(grid_idx)

    # Check each existing grid independently
    if hasattr(gui, 'grid_1') and gui.grid_1 is not None:
        check_grid_obj(gui.grid_1, 1)
    if hasattr(gui, 'grid_2') and gui.grid_2 is not None:
        check_grid_obj(gui.grid_2, 2)
    if hasattr(gui, 'grid_3') and gui.grid_3 is not None:
        check_grid_obj(gui.grid_3, 3)

    if exceeded:
        if len(exceeded) == 1:
            open_secondary_window(f"Grid {exceeded[0]} exceeds acceptance size of 19x39 mm")
        else:
            open_secondary_window(f"Grids {', '.join(map(str, exceeded))} exceed acceptance size of 19x39 mm")
