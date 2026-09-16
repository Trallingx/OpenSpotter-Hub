"""
Machine Config Window
A PyQt6 dialog to edit all parameters from machine_config.json
including machine, gantry, klipper, and valves.
Schema-driven for valve fields via valve.config.json.
"""

from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QScrollArea,
)

from utils import ConfigManager, AppSignals
from services.valve_macro_commands import build_shoot_command, build_valve_timing_command


class MachineConfigWindow(QDialog):
    """
    A dialog window that exposes all machine configuration parameters.
    """

    def __init__(self, app_signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Machine Configuration")
        # Dynamic sizing: let the window size to content, max 800x600
        self.setMaximumWidth(800)
        self.setMaximumHeight(600)

        self.app_signals = app_signals
        self.cm = ConfigManager.get_instance()

        self.tabs = QTabWidget()

        # Editors storage
        self.machine_name = QLineEdit()
        self.machine_type = QLineEdit()

        # Build tabs
        self._build_machine_tab()
        self._build_gantry_tab()
        self._build_klipper_tab()
        self._build_valves_tab()

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

    def _wrap_tab_with_scroll(self, widget: QWidget) -> QWidget:
        """
        Wrap a tab widget in a QScrollArea to enable mouse wheel scrolling.
        Returns the scroll area as a replacement for the tab content.
        """
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        return scroll

    # --- Machine tab ---
    def _build_machine_tab(self) -> None:
        machine = self.cm.get("machine", {})
        tab = QWidget()
        form = QFormLayout(tab)
        self.machine_name.setText(str(machine.get("name", "")))
        self.machine_type.setText(str(machine.get("type", "")))
        form.addRow("Name", self.machine_name)
        form.addRow("Type", self.machine_type)
        tab.setLayout(form)
        scroll_tab = self._wrap_tab_with_scroll(tab)
        self.tabs.addTab(scroll_tab, "Machine")

    # --- Gantry tab ---
    def _build_gantry_tab(self) -> None:
        gantry = self.cm.get("gantry", {})
        tab = QWidget()
        form = QFormLayout(tab)
        self.max_x = QDoubleSpinBox(); self.max_x.setRange(-10000, 10000); self.max_x.setValue(float(gantry.get("max_x", 200.0)))
        self.max_y = QDoubleSpinBox(); self.max_y.setRange(-10000, 10000); self.max_y.setValue(float(gantry.get("max_y", 200.0)))
        self.max_z = QDoubleSpinBox(); self.max_z.setRange(-10000, 10000); self.max_z.setValue(float(gantry.get("max_z", 10.0)))
        self.velocity = QDoubleSpinBox(); self.velocity.setRange(0, 10000); self.velocity.setValue(float(gantry.get("velocity", 50.0)))
        form.addRow("Max X (mm)", self.max_x)
        form.addRow("Max Y (mm)", self.max_y)
        form.addRow("Max Z (mm)", self.max_z)
        form.addRow("Velocity (mm/s)", self.velocity)
        tab.setLayout(form)
        scroll_tab = self._wrap_tab_with_scroll(tab)
        self.tabs.addTab(scroll_tab, "Gantry")

    # --- Klipper tab ---
    def _build_klipper_tab(self) -> None:
        klipper = self.cm.get("klipper", {})
        tab = QWidget()
        form = QFormLayout(tab)
        self.klipper_host = QLineEdit(str(klipper.get("host", "localhost")))
        self.klipper_port = QSpinBox(); self.klipper_port.setRange(1, 65535); self.klipper_port.setValue(int(klipper.get("port", 7125)))
        form.addRow("Host", self.klipper_host)
        form.addRow("Port", self.klipper_port)

        klipper_config = self.cm.get("klipper", {})
        dispatch_window_value = max(1, int(klipper_config.get("dispatch_window_spots", 25)))
        dispatch_refill_default = max(1, (dispatch_window_value + 1) // 2)
        dispatch_refill_value = max(
            1,
            min(
                int(klipper_config.get("dispatch_refill_threshold_spots", dispatch_refill_default)),
                dispatch_window_value,
            ),
        )

        dispatch_window_w = QSpinBox()
        dispatch_window_w.setRange(1, 100000)
        dispatch_window_w.setValue(dispatch_window_value)
        form.addRow("Send-Ahead Buffer (spots)", dispatch_window_w)
        self.dispatch_window_spots = dispatch_window_w

        dispatch_refill_w = QSpinBox()
        dispatch_refill_w.setRange(1, dispatch_window_value)
        dispatch_refill_w.setValue(dispatch_refill_value)
        form.addRow("Refill After Completed (spots)", dispatch_refill_w)
        self.dispatch_refill_threshold_spots = dispatch_refill_w
        self.dispatch_window_spots.valueChanged.connect(self._on_dispatch_window_changed)

        tolerance_w = QDoubleSpinBox()
        tolerance_w.setRange(0.0, 1000.0)
        tolerance_w.setSingleStep(0.005)
        tolerance_w.setDecimals(4)
        tolerance_w.setValue(float(klipper_config.get("spot_position_tolerance_mm", 0.05)))
        form.addRow("Spot Position Tolerance (mm)", tolerance_w)
        self.spot_position_tolerance = tolerance_w
        tab.setLayout(form)
        scroll_tab = self._wrap_tab_with_scroll(tab)
        self.tabs.addTab(scroll_tab, "Klipper")

    def _on_dispatch_window_changed(self, value: int) -> None:
        if not hasattr(self, "dispatch_refill_threshold_spots"):
            return
        self.dispatch_refill_threshold_spots.setMaximum(max(1, int(value)))

    # --- Valves tab ---
    def _build_valves_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.valve_widgets: List[Dict[str, Any]] = []

        schema_map = {f.get("name"): f for f in self.cm.valve_fields()}
        timing_max = 1_000_000.0

        valve_tabs = QTabWidget()

        for i, v in enumerate(self.cm.available_valves()):
            group = QWidget()
            group_layout = QVBoxLayout(group)
            form_widget = QWidget()
            form = QFormLayout(form_widget)

            # pin
            pin_w = QSpinBox(); pin_w.setRange(int(schema_map.get("pin", {}).get("min", 0)), int(schema_map.get("pin", {}).get("max", 100)))
            pin_w.setValue(int(v.get("pin", schema_map.get("pin", {}).get("default", 0))))
            form.addRow("Pin", pin_w)

            # name
            name_w = QLineEdit(str(v.get("name", schema_map.get("name", {}).get("default", "Valve"))))
            form.addRow("Name", name_w)

            # color (RGB spinboxes)
            color = v.get("color", [255, 0, 0])
            color_r = QSpinBox(); color_r.setRange(0, 255); color_r.setValue(int(color[0] if isinstance(color, list) and len(color) > 0 else 255))
            color_g = QSpinBox(); color_g.setRange(0, 255); color_g.setValue(int(color[1] if isinstance(color, list) and len(color) > 1 else 0))
            color_b = QSpinBox(); color_b.setRange(0, 255); color_b.setValue(int(color[2] if isinstance(color, list) and len(color) > 2 else 0))
            color_row = QHBoxLayout()
            color_row.addWidget(QLabel("R")); color_row.addWidget(color_r)
            color_row.addWidget(QLabel("G")); color_row.addWidget(color_g)
            color_row.addWidget(QLabel("B")); color_row.addWidget(color_b)
            color_widget = QWidget(); color_widget.setLayout(color_row)
            form.addRow("Color", color_widget)

            hold_w = QCheckBox("Hold"); hold_w.setChecked(bool(v.get("hold", schema_map.get("hold", {}).get("default", False))))
            form.addRow("Hold", hold_w)

            pre_wait_schema = schema_map.get("pre_fire_wait", {})
            pre_wait_w = QDoubleSpinBox(); pre_wait_w.setRange(float(pre_wait_schema.get("min", 0.0)), float(pre_wait_schema.get("max", timing_max)))
            pre_wait_w.setSingleStep(0.1); pre_wait_w.setValue(float(v.get("pre_fire_wait", pre_wait_schema.get("default", 0.0))))
            form.addRow("Pre Fire Wait (ms)", pre_wait_w)

            post_wait_schema = schema_map.get("post_fire_wait", {})
            post_wait_w = QDoubleSpinBox(); post_wait_w.setRange(float(post_wait_schema.get("min", 0.0)), float(post_wait_schema.get("max", timing_max)))
            post_wait_w.setSingleStep(0.1); post_wait_w.setValue(float(v.get("post_fire_wait", post_wait_schema.get("default", 0.0))))
            form.addRow("Post Fire Wait (ms)", post_wait_w)

            on_schema = schema_map.get("on_ms", {})
            on_w = QDoubleSpinBox(); on_w.setRange(float(on_schema.get("min", 0.0)), float(on_schema.get("max", timing_max)))
            on_w.setSingleStep(0.1); on_w.setValue(float(v.get("on_ms", on_schema.get("default", 5.0))))
            form.addRow("On Time (ms)", on_w)

            off_schema = schema_map.get("off_ms", {})
            off_w = QDoubleSpinBox(); off_w.setRange(float(off_schema.get("min", 0.0)), float(off_schema.get("max", timing_max)))
            off_w.setSingleStep(0.1); off_w.setValue(float(v.get("off_ms", off_schema.get("default", 0.0))))
            form.addRow("Off Time (ms)", off_w)

            cycles_schema = schema_map.get("cycles", {})
            cycles_w = QSpinBox(); cycles_w.setRange(int(cycles_schema.get("min", 1)), int(cycles_schema.get("max", 100)))
            cycles_w.setValue(int(v.get("cycles", cycles_schema.get("default", 1))))
            form.addRow("Cycles", cycles_w)

            # is_active
            active_w = QCheckBox("Active"); active_w.setChecked(bool(v.get("is_active", True)))
            form.addRow("Active", active_w)

            group_layout.addWidget(form_widget)

            fire_row = QHBoxLayout()
            fire_row.addStretch()
            fire_btn = QPushButton("Fire Valve")
            fire_btn.clicked.connect(lambda checked=False, valve_index=i: self._on_fire_valve(valve_index))
            fire_row.addWidget(fire_btn)
            group_layout.addLayout(fire_row)

            valve_tabs.addTab(group, str(v.get("name", f"Valve {v.get('id', i)}")))

            self.valve_widgets.append({
                "pin": pin_w,
                "name": name_w,
                "color": (color_r, color_g, color_b),
                "hold": hold_w,
                "pre_fire_wait": pre_wait_w,
                "post_fire_wait": post_wait_w,
                "on_ms": on_w,
                "off_ms": off_w,
                "cycles": cycles_w,
                "is_active": active_w,
                "id": v.get("id", i),
            })

        layout.addWidget(valve_tabs)

        # Add/Remove valves could be added later; keep current list editable
        layout.addStretch()
        tab.setLayout(layout)
        scroll_tab = self._wrap_tab_with_scroll(tab)
        self.tabs.addTab(scroll_tab, "Valves")

    def _on_fire_valve(self, valve_index: int) -> None:
        """Fire a valve using the current values in its config tab."""
        if valve_index < 0 or valve_index >= len(self.valve_widgets):
            return

        vw = self.valve_widgets[valve_index]
        params = self._collect_valve_params(vw)
        params["VALVE"] = int(vw["id"])
        command = self._build_shoot_command(params)
        trigger_mode = str(self.cm.get("klipper.valve_trigger_mode", "") or "").strip().lower()
        if trigger_mode == "mcu":
            timing_command = build_valve_timing_command(
                int(params["VALVE"]),
                params,
                self.cm.valve_fields(),
            )
            command = f"{timing_command}\n{command}"
        if self.app_signals:
            self.app_signals.macro_execute_requested.emit(command)

    def _collect_valve_params(self, vw: Dict[str, Any]) -> Dict[str, Any]:
        """Collect the current valve editor values into a SHOOT payload."""
        r, g, b = vw["color"]
        return {
            "pin": int(vw["pin"].value()),
            "name": vw["name"].text(),
            "color": [int(r.value()), int(g.value()), int(b.value())],
            "hold": bool(vw["hold"].isChecked()),
            "pre_fire_wait": float(vw["pre_fire_wait"].value()),
            "post_fire_wait": float(vw["post_fire_wait"].value()),
            "on_ms": float(vw["on_ms"].value()),
            "off_ms": float(vw["off_ms"].value()),
            "cycles": int(vw["cycles"].value()),
            "is_active": bool(vw["is_active"].isChecked()),
        }

    def _build_shoot_command(self, params: Dict[str, Any]) -> str:
        """Build a SHOOT command using wait and firing timing."""
        return build_shoot_command(
            int(params.get("VALVE", 0)),
            params,
            self.cm.valve_fields(),
            self.cm.get("klipper", {}),
        )

    # --- Save handler ---
    def _on_save(self) -> None:
        data: Dict[str, Any] = self.cm.machine_config()
        data["machine"] = {
            "name": self.machine_name.text(),
            "type": self.machine_type.text(),
        }
        data["gantry"] = {
            "max_x": float(self.max_x.value()),
            "max_y": float(self.max_y.value()),
            "max_z": float(self.max_z.value()),
            "velocity": float(self.velocity.value()),
        }

        klipper = dict(self.cm.get("klipper", {}))
        klipper["host"] = self.klipper_host.text()
        klipper["port"] = int(self.klipper_port.value())
        dispatch_window = int(self.dispatch_window_spots.value())
        klipper["dispatch_window_spots"] = dispatch_window
        klipper["dispatch_refill_threshold_spots"] = min(
            int(self.dispatch_refill_threshold_spots.value()),
            dispatch_window,
        )
        klipper["spot_position_tolerance_mm"] = float(self.spot_position_tolerance.value())
        data["klipper"] = klipper

        # Valves
        valves_out: List[Dict[str, Any]] = []
        for vw in self.valve_widgets:
            r, g, b = vw["color"]
            valves_out.append({
                "id": int(vw["id"]),
                "pin": int(vw["pin"].value()),
                "name": vw["name"].text(),
                "color": [int(r.value()), int(g.value()), int(b.value())],
                "hold": bool(vw["hold"].isChecked()),
                "pre_fire_wait": float(vw["pre_fire_wait"].value()),
                "post_fire_wait": float(vw["post_fire_wait"].value()),
                "on_ms": float(vw["on_ms"].value()),
                "off_ms": float(vw["off_ms"].value()),
                "cycles": int(vw["cycles"].value()),
                "is_active": bool(vw["is_active"].isChecked()),
            })
        data["valves"] = valves_out

        # Persist via ConfigManager
        if self.cm.persist_machine_config(data):
            # Emit signals for listeners
            if self.app_signals:
                self.app_signals.config_saved.emit()
            self.accept()
        else:
            # Simple feedback; could add a message box
            if self.app_signals:
                self.app_signals.error_occurred.emit("Failed to save machine configuration")
            self.reject()
