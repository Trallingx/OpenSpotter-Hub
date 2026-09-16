"""
Controls Panel
Right-side machine control suite: start/pause/stop, sequence settings
(lines per block / full grid), and speed.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QLineEdit,
    QGridLayout,
    QPlainTextEdit,
)
from PyQt6.QtCore import Qt

from utils import AppSignals, ConfigManager


class ControlsPanel(QWidget):
    def __init__(self, main_controller=None, app_signals: AppSignals = None, parent=None) -> None:
        super().__init__(parent)
        self.main_controller = main_controller
        self.signals = app_signals or AppSignals()
        self.cm = ConfigManager.get_instance()
        self._is_connected = False
        self._spotting_active = False
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        # Allow natural height so fields are readable

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Machine Controls")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #a6e3a1;")
        layout.addWidget(title)

        # Start/Pause/Stop
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.start_btn.clicked.connect(self._on_start)
        self.pause_btn.clicked.connect(lambda: self.signals.spotting_pause_requested.emit())
        self.stop_btn.clicked.connect(lambda: self.signals.spotting_stop_requested.emit())
        btn_row.addWidget(self.start_btn); btn_row.addWidget(self.pause_btn); btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        # Sequence settings
        seq_row = QHBoxLayout()
        seq_row.addWidget(QLabel("Lines/block:"))
        self.lines_spin = QSpinBox(); self.lines_spin.setRange(1, 100); self.lines_spin.setValue(1)
        seq_row.addWidget(self.lines_spin)
        self.full_grid_checkbox = QCheckBox("Full grid")
        self.full_grid_checkbox.stateChanged.connect(self._on_full_grid_toggled)
        seq_row.addWidget(self.full_grid_checkbox)
        seq_row.addStretch()
        layout.addLayout(seq_row)

        # Speed
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed (mm/s):"))
        self.speed_spin = QDoubleSpinBox(); self.speed_spin.setRange(1, 10000); self.speed_spin.setValue(1000.0); self.speed_spin.setSingleStep(10.0)
        speed_row.addWidget(self.speed_spin)
        speed_row.addStretch()
        layout.addLayout(speed_row)

        # Klipper Console (replaces macro field)
        console_group = QGroupBox("Klipper Console")
        console_layout = QVBoxLayout()
        
        # Console output display
        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMaximumHeight(120)
        self.console_output.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 9px;
                padding: 4px;
            }
            """
        )
        console_layout.addWidget(QLabel("Output:"))
        console_layout.addWidget(self.console_output)
        
        # Command input row
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Command:"))
        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText("e.g. GET_POSITION, SHOOT VALVE=0 HOLD=0, LED_BLINK")
        self.console_input.returnPressed.connect(self._on_console_send)
        input_row.addWidget(self.console_input)
        self.console_send_btn = QPushButton("Send")
        self.console_send_btn.setMaximumWidth(60)
        self.console_send_btn.clicked.connect(self._on_console_send)
        input_row.addWidget(self.console_send_btn)
        console_layout.addLayout(input_row)
        
        console_group.setLayout(console_layout)
        layout.addWidget(console_group)

        # Toolhead Position & Jog Controls
        toolhead_group = QGroupBox("Toolhead Position")
        toolhead_layout = QVBoxLayout()
        
        # Position display
        pos_layout = QHBoxLayout()
        self.pos_x = QLabel("X: 0.00")
        self.pos_y = QLabel("Y: 0.00")
        self.pos_z = QLabel("Z: 0.00")
        self.pos_x.setStyleSheet("font-family: monospace; color: #f38ba8; font-weight: bold;")
        self.pos_y.setStyleSheet("font-family: monospace; color: #a6e3a1; font-weight: bold;")
        self.pos_z.setStyleSheet("font-family: monospace; color: #89b4fa; font-weight: bold;")
        pos_layout.addWidget(self.pos_x)
        pos_layout.addWidget(self.pos_y)
        pos_layout.addWidget(self.pos_z)
        toolhead_layout.addLayout(pos_layout)
        
        # Home buttons
        home_btn_row = QHBoxLayout()
        self.btn_all = QPushButton("ALL")
        self.btn_all.setMinimumHeight(28)
        self.btn_all.clicked.connect(self._on_home)
        self.btn_home = QPushButton("⌂ HOME")
        self.btn_home.setMinimumHeight(28)
        self.btn_home.clicked.connect(self._on_home)
        home_btn_row.addWidget(self.btn_all)
        home_btn_row.addWidget(self.btn_home)
        home_btn_row.addStretch()
        toolhead_layout.addLayout(home_btn_row)
        
        # Jog controls
        jog_increments = [-100, -10, -1, 0, 1, 10, 100]
        axes = [("X", "#f38ba8"), ("Y", "#a6e3a1"), ("Z", "#89b4fa")]
        
        for axis, color in axes:
            axis_layout = QHBoxLayout()
            for inc in jog_increments:
                btn = QPushButton(str(inc) if inc != 0 else axis)
                btn.setMaximumWidth(35)
                btn.setMinimumHeight(28)
                if inc == 0:
                    btn.setStyleSheet(f"background-color: #ff9500; color: #1e1e2e; font-weight: bold; border-radius: 2px;")
                else:
                    btn.setStyleSheet(f"color: {color};")
                btn.clicked.connect(lambda checked, ax=axis, i=inc: self._on_jog(ax, i))
                if not hasattr(self, "jog_buttons"):
                    self.jog_buttons = []
                self.jog_buttons.append(btn)
                axis_layout.addWidget(btn)
            toolhead_layout.addLayout(axis_layout)
        
        toolhead_group.setLayout(toolhead_layout)
        layout.addWidget(toolhead_group)

        layout.addStretch()
        self.setLayout(layout)
        
        # Connect signals
        if self.signals:
            self.signals.gantry_position_updated.connect(self._on_position_updated)
            self.signals.macro_response_received.connect(self._on_console_response)
            self.signals.connection_status_changed.connect(self._on_connection_status_changed)
            self.signals.spotting_started.connect(self._on_spotting_started)
            self.signals.spotting_finished.connect(self._on_spotting_finished)
            self.signals.spotting_stopped.connect(self._on_spotting_finished)
            self.signals.spotting_paused.connect(self._on_spotting_paused)

        self._apply_control_state()
        
        self.setStyleSheet(
            """
            QGroupBox { color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #cdd6f4; }
            QPushButton:disabled {
                background-color: #f2b8b5;
                color: #7f1d1d;
                border: 1px solid #e07a7a;
            }
            """
        )

    def _on_full_grid_toggled(self, state):
        enabled = state == 0  # unchecked -> enabled
        self.lines_spin.setEnabled(enabled)

    def _apply_control_state(self) -> None:
        connected = self._is_connected
        active = self._spotting_active

        self.start_btn.setEnabled(connected and not active)
        self.pause_btn.setEnabled(connected and active)
        self.stop_btn.setEnabled(connected and active)

        for button in [self.btn_all, self.btn_home, self.console_send_btn, *getattr(self, "jog_buttons", [])]:
            button.setEnabled(connected)

    def _on_connection_status_changed(self, connected: bool, message: str = "") -> None:
        self._is_connected = connected
        if not connected:
            self._spotting_active = False
        self._apply_control_state()

    def _on_spotting_started(self) -> None:
        self._spotting_active = True
        self._apply_control_state()

    def _on_spotting_paused(self) -> None:
        self._spotting_active = True
        self._apply_control_state()

    def _on_spotting_finished(self) -> None:
        self._spotting_active = False
        self._apply_control_state()

    def _on_start(self):
        settings = {
            "lines_per_block": int(self.lines_spin.value()),
            "full_grid_mode": bool(self.full_grid_checkbox.isChecked()),
            "speed_mm_s": float(self.speed_spin.value()),
            # grids omitted: SpottingController uses live UI-provided grids via AppSignals
        }
        self.signals.spotting_start_requested.emit(settings)

    def _on_console_send(self):
        """Handle console command send."""
        cmd = self.console_input.text().strip()
        if cmd:
            self.console_output.appendPlainText(f"> {cmd}")
            # Send via signal
            self.signals.macro_execute_requested.emit(cmd)
            # Clear input
            self.console_input.clear()

    def _on_console_response(self, response_text: str) -> None:
        """Display console response."""
        self.console_output.appendPlainText(response_text)
        # Auto-scroll to bottom
        self.console_output.verticalScrollBar().setValue(
            self.console_output.verticalScrollBar().maximum()
        )

    def _on_position_updated(self, x: float, y: float, z: float) -> None:
        """Update position display."""
        self.pos_x.setText(f"X: {x:.2f}")
        self.pos_y.setText(f"Y: {y:.2f}")
        self.pos_z.setText(f"Z: {z:.2f}")

    def _on_jog(self, axis: str, increment: float) -> None:
        """Execute a jog movement."""
        if not self.main_controller or not self.main_controller.klipper_service.is_connected:
            return

        # Get current position
        current_pos = self.main_controller.klipper_service.get_position()
        if current_pos is None:
            return

        # Calculate new position
        if axis == "X":
            new_x = current_pos.x + increment
            new_y = current_pos.y
            new_z = current_pos.z
        elif axis == "Y":
            new_x = current_pos.x
            new_y = current_pos.y + increment
            new_z = current_pos.z
        else:  # Z
            new_x = current_pos.x
            new_y = current_pos.y
            new_z = current_pos.z + increment

        # Execute move
        self.main_controller.klipper_service.move_gantry(new_x, new_y, new_z)

    def _on_home(self) -> None:
        """Execute home command."""
        if not self.main_controller or not self.main_controller.klipper_service.is_connected:
            return
        # Send home command to all axes
        self.main_controller.klipper_service.send_gcode("G28")
