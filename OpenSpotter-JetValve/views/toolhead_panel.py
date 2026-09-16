"""
Toolhead Jog Panel
Control panel for manual toolhead positioning with jog buttons.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGridLayout,
    QGroupBox,
    QSpinBox,
)
from PyQt6.QtCore import Qt

from utils import AppSignals


class ToolheadPanel(QWidget):
    """
    Toolhead jog control panel with position display and movement buttons.
    """

    def __init__(self, main_controller=None, app_signals: AppSignals = None, parent=None):
        """
        Initialize toolhead panel.

        Args:
            main_controller: MainController instance for executing moves
            app_signals: Global application signals
            parent: Parent widget
        """
        super().__init__(parent)
        self.main_controller = main_controller
        self.app_signals = app_signals or AppSignals()
        self.setMinimumWidth(280)
        self.setMaximumWidth(320)

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("Toolhead Position")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #a6e3a1;")
        layout.addWidget(title)

        # Position display
        pos_layout = QGridLayout()
        pos_layout.setSpacing(8)

        # Position labels
        self.pos_x = QLabel("X: 0.00")
        self.pos_y = QLabel("Y: 0.00")
        self.pos_z = QLabel("Z: 0.00")
        self.pos_x.setStyleSheet("font-family: monospace; color: #f38ba8;")
        self.pos_y.setStyleSheet("font-family: monospace; color: #a6e3a1;")
        self.pos_z.setStyleSheet("font-family: monospace; color: #89b4fa;")

        pos_layout.addWidget(self.pos_x, 0, 0)
        pos_layout.addWidget(self.pos_y, 0, 1)
        pos_layout.addWidget(self.pos_z, 0, 2)

        layout.addLayout(pos_layout)

        # Control buttons
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("ALL")
        btn_all.setMinimumHeight(30)
        btn_all.clicked.connect(self._on_all_home)
        btn_layout.addWidget(btn_all)

        btn_home = QPushButton("⌂ HOME")
        btn_home.setMinimumHeight(30)
        btn_home.clicked.connect(self._on_home)
        btn_layout.addWidget(btn_home)
        layout.addLayout(btn_layout)

        # Jog increments group
        jog_group = QGroupBox("Jog Controls")
        jog_layout = QVBoxLayout()

        # X-axis controls
        x_layout = self._create_jog_row("X", "f38ba8")
        jog_layout.addLayout(x_layout)

        # Y-axis controls
        y_layout = self._create_jog_row("Y", "a6e3a1")
        jog_layout.addLayout(y_layout)

        # Z-axis controls
        z_layout = self._create_jog_row("Z", "89b4fa")
        jog_layout.addLayout(z_layout)

        jog_group.setLayout(jog_layout)
        layout.addWidget(jog_group)

        layout.addStretch()
        self.setLayout(layout)

        # Connect position updates
        if self.app_signals:
            self.app_signals.gantry_position_updated.connect(self._on_position_updated)

    def _create_jog_row(self, axis: str, color: str) -> QHBoxLayout:
        """Create a row of jog buttons for an axis."""
        row = QHBoxLayout()
        row.setSpacing(2)

        increments = [-100, -10, -1, 0, 1, 10, 100]
        buttons = []

        for inc in increments:
            btn = QPushButton(str(inc) if inc != 0 else axis)
            btn.setMaximumWidth(35)
            btn.setMinimumHeight(28)

            # Highlight center button
            if inc == 0:
                btn.setStyleSheet(f"background-color: #ff9500; color: #1e1e2e; font-weight: bold;")
            else:
                btn.setStyleSheet(f"color: #{color};")

            btn.clicked.connect(lambda checked, ax=axis, i=inc: self._on_jog(ax, i))
            buttons.append(btn)
            row.addWidget(btn)

        return row

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

    def _on_all_home(self) -> None:
        """Same as home for ALL button."""
        self._on_home()
