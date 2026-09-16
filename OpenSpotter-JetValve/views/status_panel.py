"""
Status Panel
Bottom panel with progress bar, gantry status, and logs.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
)
from PyQt6.QtCore import Qt

from utils import AppSignals


class StatusPanel(QWidget):
    """
    Bottom status panel with progress bar, gantry position, and logs.
    """

    def __init__(self, app_signals: AppSignals = None, parent=None):
        """
        Initialize status panel.

        Args:
            app_signals: Global application signals
            parent: Parent widget
        """
        super().__init__(parent)
        self.app_signals = app_signals or AppSignals()
        self.setMinimumHeight(200)
        self.setMaximumHeight(280)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Machine controls moved to right column; status frame keeps status/progress/log

        # Status line
        status_layout = QHBoxLayout()
        
        # Connection status indicator
        self.connection_label = QLabel("● Disconnected")
        self.connection_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
        status_layout.addWidget(self.connection_label)
        
        self.status_label = QLabel("Status: Ready")
        status_layout.addWidget(self.status_label)

        self.gantry_label = QLabel("Gantry: X=0.00 Y=0.00 Z=0.00")
        status_layout.addWidget(self.gantry_label)

        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Progress bar
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("Completed spots:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Log viewer
        log_label = QLabel("Activity Log")
        log_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(80)
        self.log_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e2e;
                color: #6c7086;
                border: 1px solid #45475a;
                border-radius: 4px;
                font-family: monospace;
                font-size: 9px;
            }
            """
        )
        layout.addWidget(self.log_text)

        self.setLayout(layout)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #313244;
                border-top: 1px solid #45475a;
            }
            QLabel {
                color: #cdd6f4;
            }
            """
        )

        # Connect signals
        if self.app_signals:
            self.app_signals.print_progress_updated.connect(self._on_progress_updated)
            self.app_signals.gantry_position_updated.connect(self._on_gantry_position_updated)
            self.app_signals.status_message.connect(self._on_status_message)
            self.app_signals.connection_status_changed.connect(self._on_connection_status_changed)

    def _on_progress_updated(self, current: int, total: int) -> None:
        """Handle progress update signal."""
        if total > 0:
            percent = (current / total) * 100
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"{current}/{total} completed ({percent:.1f}%)")

    def _on_gantry_position_updated(self, x: float, y: float, z: float) -> None:
        """Handle gantry position update signal."""
        self.gantry_label.setText(f"Gantry: X={x:.2f} Y={y:.2f} Z={z:.2f}")

    def _on_status_message(self, message: str) -> None:
        """Handle status message signal."""
        self.status_label.setText(f"Status: {message}")
        self.log_text.append(f"→ {message}")

        # Limit log size
        if self.log_text.document().blockCount() > 100:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()

    def _on_connection_status_changed(self, connected: bool, message: str = "") -> None:
        """Handle connection status change."""
        if connected:
            self.connection_label.setText("● Connected")
            self.connection_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            self.status_label.setText("Status: Connected to Moonraker")
            self.log_text.append(f"✓ Connected: {message}")
        else:
            self.connection_label.setText("● Disconnected")
            self.connection_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
            self.status_label.setText(f"Status: {message or 'Not connected'}")
            self.log_text.append(f"✗ Disconnected: {message}")

        # Scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        # Limit log size
        if self.log_text.document().blockCount() > 100:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()

    def add_log(self, message: str) -> None:
        """Add message to log viewer."""
        self.log_text.append(f"→ {message}")

        # Scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        # Limit log size
        if self.log_text.document().blockCount() > 100:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()

    def set_progress(self, current: int, total: int) -> None:
        """Set progress bar value."""
        if total > 0:
            percent = (current / total) * 100
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"{current}/{total} completed ({percent:.1f}%)")
