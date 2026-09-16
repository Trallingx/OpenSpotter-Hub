import sys
from PyQt5 import QtCore, QtWidgets, QtGui
from serial_client import SerialClient


TIME_MIN = 20
TIME_MAX = 20000


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arduino Timing Control")

        self.client: SerialClient | None = None
        self.connected = False
        self.pending_slider_target = None

        self._build_ui()
        self._wire_events()
        self._set_controls_enabled(False)

        self.slider_timer = QtCore.QTimer(self)
        self.slider_timer.setSingleShot(True)
        self.slider_timer.timeout.connect(self.flush_slider_target)

        self.refresh_ports()

    # UI construction -----------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        central.setLayout(layout)
        self.setCentralWidget(central)

        conn_layout = QtWidgets.QHBoxLayout()
        self.port_combo = QtWidgets.QComboBox()
        self.refresh_button = QtWidgets.QPushButton("Refresh ports")
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.status_label = QtWidgets.QLabel("Disconnected")
        conn_layout.addWidget(QtWidgets.QLabel("Port"))
        conn_layout.addWidget(self.port_combo)
        conn_layout.addWidget(self.refresh_button)
        conn_layout.addWidget(self.connect_button)
        conn_layout.addWidget(self.status_label, 1)
        layout.addLayout(conn_layout)

        pulse_layout = QtWidgets.QHBoxLayout()
        self.cycle_count = QtWidgets.QSpinBox()
        self.cycle_count.setRange(1, 10000)
        self.cycle_count.setValue(1)
        self.shot_button = QtWidgets.QPushButton("Send Cycles (K)")
        pulse_layout.addWidget(QtWidgets.QLabel("Cycles"))
        pulse_layout.addWidget(self.cycle_count)
        pulse_layout.addWidget(self.shot_button)
        pulse_layout.addStretch(1)
        layout.addLayout(pulse_layout)

        self.on_min = QtWidgets.QSpinBox()
        self.on_max = QtWidgets.QSpinBox()
        self.on_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.on_value_label = QtWidgets.QLabel(self._format_time_value(0))
        self.on_minus = QtWidgets.QPushButton("ON - (E)")
        self.on_plus = QtWidgets.QPushButton("ON + (R)")

        self._setup_spinbox(self.on_min)
        self._setup_spinbox(self.on_max)
        self.on_min.setValue(100)
        self.on_max.setValue(2000)
        self._setup_slider(self.on_slider, 100, 2000, 100)
        layout.addLayout(
            self._build_channel(
                "ON time",
                self.on_min,
                self.on_max,
                self.on_slider,
                self.on_value_label,
                self.on_minus,
                self.on_plus,
            )
        )

        self.off_min = QtWidgets.QSpinBox()
        self.off_max = QtWidgets.QSpinBox()
        self.off_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.off_value_label = QtWidgets.QLabel(self._format_time_value(0))
        self.off_minus = QtWidgets.QPushButton("OFF - (D)")
        self.off_plus = QtWidgets.QPushButton("OFF + (F)")

        self._setup_spinbox(self.off_min)
        self._setup_spinbox(self.off_max)
        self.off_min.setValue(100)
        self.off_max.setValue(2000)
        self._setup_slider(self.off_slider, 100, 2000, 900)
        layout.addLayout(
            self._build_channel(
                "OFF time",
                self.off_min,
                self.off_max,
                self.off_slider,
                self.off_value_label,
                self.off_minus,
                self.off_plus,
            )
        )

        self._sync_slider_with_range(is_on=True)
        self._sync_slider_with_range(is_on=False)

        layout.addStretch(1)

    def _setup_spinbox(self, spin: QtWidgets.QSpinBox):
        spin.setRange(TIME_MIN, TIME_MAX)
        spin.setSingleStep(1)
        spin.setKeyboardTracking(False)

    def _format_time_value(self, value: int) -> str:
        # Serial values are in 0.1 ms units (10^-4 s), display user-friendly ms.
        return f"{value / 10:.1f} ms"

    def _setup_slider(self, slider: QtWidgets.QSlider, lo: int, hi: int, val: int):
        slider.setRange(lo, hi)
        slider.setSingleStep(1)
        slider.setValue(val)

    def _compute_step(self, lo: int, hi: int) -> int:
        return max(1, (hi - lo) // 9 if hi > lo else 1)

    def _sync_slider_with_range(self, is_on: bool):
        slider = self.on_slider if is_on else self.off_slider
        label = self.on_value_label if is_on else self.off_value_label
        lo = self.on_min.value() if is_on else self.off_min.value()
        hi = self.on_max.value() if is_on else self.off_max.value()

        new_val = max(lo, min(hi, slider.value()))
        step = self._compute_step(lo, hi)

        slider.blockSignals(True)
        try:
            slider.setRange(lo, hi)
            slider.setSingleStep(step)
            slider.setPageStep(step)
            slider.setValue(new_val)
        finally:
            slider.blockSignals(False)

        label.setText(self._format_time_value(new_val))

    def _build_channel(self, title: str, spin_min, spin_max, slider, value_label, minus_btn, plus_btn):
        group = QtWidgets.QVBoxLayout()
        group.addWidget(QtWidgets.QLabel(title))

        range_layout = QtWidgets.QHBoxLayout()
        range_layout.addWidget(QtWidgets.QLabel("Min"))
        range_layout.addWidget(spin_min)
        range_layout.addWidget(QtWidgets.QLabel("Max"))
        range_layout.addWidget(spin_max)
        range_layout.addStretch(1)
        group.addLayout(range_layout)

        slider_layout = QtWidgets.QHBoxLayout()
        slider_layout.addWidget(slider, 1)
        slider_layout.addWidget(value_label)
        group.addLayout(slider_layout)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(minus_btn)
        button_layout.addWidget(plus_btn)
        button_layout.addStretch(1)
        group.addLayout(button_layout)

        return group

    # Wiring --------------------------------------------------------------
    def _wire_events(self):
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.shot_button.clicked.connect(self.trigger_shot)

        self.on_minus.clicked.connect(lambda: self.nudge(True, -1))
        self.on_plus.clicked.connect(lambda: self.nudge(True, 1))
        self.off_minus.clicked.connect(lambda: self.nudge(False, -1))
        self.off_plus.clicked.connect(lambda: self.nudge(False, 1))

        self.on_minus.setShortcut(QtGui.QKeySequence("E"))
        self.on_plus.setShortcut(QtGui.QKeySequence("R"))
        self.off_minus.setShortcut(QtGui.QKeySequence("D"))
        self.off_plus.setShortcut(QtGui.QKeySequence("F"))
        self.shot_button.setShortcut(QtGui.QKeySequence("K"))

        self.on_slider.valueChanged.connect(lambda v: self.on_slider_changed(v, is_on=True))
        self.off_slider.valueChanged.connect(lambda v: self.on_slider_changed(v, is_on=False))

        self.on_min.valueChanged.connect(self.queue_range_update)
        self.on_max.valueChanged.connect(self.queue_range_update)
        self.off_min.valueChanged.connect(self.queue_range_update)
        self.off_max.valueChanged.connect(self.queue_range_update)

    def _set_controls_enabled(self, enabled: bool):
        for widget in (
            self.shot_button,
            self.cycle_count,
            self.on_min,
            self.on_max,
            self.on_slider,
            self.on_minus,
            self.on_plus,
            self.off_min,
            self.off_max,
            self.off_slider,
            self.off_minus,
            self.off_plus,
        ):
            widget.setEnabled(enabled)

    # Connection handling -------------------------------------------------
    def refresh_ports(self):
        current = self.port_combo.currentText()
        ports = SerialClient.available_ports()
        best_port = SerialClient.find_best_port()

        self.port_combo.clear()
        self.port_combo.addItems(ports)

        if not ports:
            return

        chosen = current if current in ports else best_port
        if chosen:
            self.port_combo.setCurrentText(chosen)

    def toggle_connection(self):
        if self.client:
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self):
        port = self.port_combo.currentText()
        if not port:
            self.refresh_ports()
            port = self.port_combo.currentText()
        if not port:
            return

        try:
            self.client = SerialClient(port)
        except Exception as exc:
            self.client = None
            self.connected = False
            self._set_controls_enabled(False)
            self.status_label.setText(f"Open failed: {exc}")
            return

        self.connected = True
        self._set_controls_enabled(True)
        self.connect_button.setText("Disconnect")

    def disconnect_serial(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

        self.connected = False
        self._set_controls_enabled(False)
        self.connect_button.setText("Connect")

    # Command helpers -----------------------------------------------------
    def send_cmd(self, cmd: str):
        if not self.client or not self.client.is_open():
            return
        try:
            self.client.write_line(cmd)
        except Exception as exc:
            self.status_label.setText(f"Write failed: {exc}")
            self.disconnect_serial()

    def _commit_spinbox_edits(self):
        self.on_min.interpretText()
        self.on_max.interpretText()
        self.off_min.interpretText()
        self.off_max.interpretText()

    def _normalized_ranges(self) -> tuple[int, int, int, int]:
        on_lo = self.on_min.value()
        on_hi = max(on_lo + 1, self.on_max.value())
        off_lo = self.off_min.value()
        off_hi = max(off_lo + 1, self.off_max.value())
        return on_lo, on_hi, off_lo, off_hi

    def _push_current_config(self) -> bool:
        self._commit_spinbox_edits()
        on_lo, on_hi, off_lo, off_hi = self._normalized_ranges()

        self.on_max.setValue(on_hi)
        self.off_max.setValue(off_hi)
        self._sync_slider_with_range(is_on=True)
        self._sync_slider_with_range(is_on=False)

        self.send_cmd(f"S:{on_lo}:{on_hi}:{off_lo}:{off_hi}")
        self.send_cmd(f"O:{self.on_slider.value()}")
        self.send_cmd(f"P:{self.off_slider.value()}")
        return True

    # UI actions ----------------------------------------------------------
    def trigger_shot(self):
        if not self.connected:
            return
        if not self._push_current_config():
            return
        self.send_cmd(f"K:{self.cycle_count.value()}")

    def queue_range_update(self):
        if not self.connected:
            return
        self._commit_spinbox_edits()
        on_lo, on_hi, off_lo, off_hi = self._normalized_ranges()
        self.on_max.setValue(on_hi)
        self.off_max.setValue(off_hi)
        self._sync_slider_with_range(is_on=True)
        self._sync_slider_with_range(is_on=False)
        if self.client:
            self.send_cmd(f"S:{on_lo}:{on_hi}:{off_lo}:{off_hi}")

    def on_slider_changed(self, value: int, is_on: bool):
        if not self.connected:
            return
        label = self.on_value_label if is_on else self.off_value_label
        label.setText(self._format_time_value(value))
        self.pending_slider_target = (is_on, value)
        self.slider_timer.start(20)

    def flush_slider_target(self):
        if not self.pending_slider_target:
            return
        if not self.connected:
            self.pending_slider_target = None
            return
        is_on, value = self.pending_slider_target
        self.pending_slider_target = None
        self.send_cmd(f"{'O' if is_on else 'P'}:{value}")

    def current_step(self, is_on: bool) -> int:
        lo = self.on_min.value() if is_on else self.off_min.value()
        hi = self.on_max.value() if is_on else self.off_max.value()
        return self._compute_step(lo, hi)

    def nudge(self, is_on: bool, direction: int):
        if not self.connected:
            return
        slider = self.on_slider if is_on else self.off_slider
        label = self.on_value_label if is_on else self.off_value_label
        lo = self.on_min.value() if is_on else self.off_min.value()
        hi = self.on_max.value() if is_on else self.off_max.value()
        step = self.current_step(is_on)

        new_val = max(lo, min(hi, slider.value() + direction * step))
        slider.blockSignals(True)
        try:
            slider.setValue(new_val)
        finally:
            slider.blockSignals(False)
        label.setText(self._format_time_value(new_val))
        self.send_cmd(f"{'O' if is_on else 'P'}:{new_val}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.resize(640, 340)
    window.show()
    sys.exit(app.exec_())
