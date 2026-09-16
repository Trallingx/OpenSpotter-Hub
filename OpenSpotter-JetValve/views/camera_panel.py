"""
Camera Panel
Panel for displaying live camera feed (placeholder).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt

from utils import AppSignals


class CameraPanel(QWidget):
    """
    Panel for camera preview and controls.
    Placeholder for future OpenCV integration.
    """

    def __init__(self, app_signals: AppSignals = None, parent=None):
        """
        Initialize camera panel.

        Args:
            app_signals: Global application signals
            parent: Parent widget
        """
        super().__init__(parent)
        self.app_signals = app_signals or AppSignals()
        self.setMinimumHeight(150)
        self.setMaximumHeight(250)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("Camera Preview")
        title.setStyleSheet("font-size: 12px; font-weight: bold; color: #a6e3a1;")
        layout.addWidget(title)

        # Placeholder
        placeholder = QLabel("Camera feed placeholder\n(OpenCV integration pending)")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #6c7086; font-style: italic;")
        layout.addWidget(placeholder)

        # Controls
        button_layout = QVBoxLayout()
        
        start_btn = QPushButton("Start Camera")
        start_btn.clicked.connect(self._on_start_camera)
        button_layout.addWidget(start_btn)

        stop_btn = QPushButton("Stop Camera")
        stop_btn.clicked.connect(self._on_stop_camera)
        button_layout.addWidget(stop_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

        self.setLayout(layout)
        self.setStyleSheet(
            """
            QWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            """
        )

    def _on_start_camera(self) -> None:
        """Handle start camera button click."""
        self.app_signals.camera_started.emit()

    def _on_stop_camera(self) -> None:
        """Handle stop camera button click."""
        self.app_signals.camera_stopped.emit()
