"""
Main Window
PyQt6 main application window with menu bar and layout.
Follows Obsidian-like dark theme design.
"""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QMenuBar,
    QMenu,
    QStatusBar,
    QLabel,
    QFileDialog,
    QDialog,
    QPlainTextEdit,
    QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt, QTimer

from pathlib import Path
import threading

from .grid_panel import GridPanel
from .canvas_view import CanvasView
from .camera_panel import CameraPanel
from .controls_panel import ControlsPanel
from .status_panel import StatusPanel
from utils import AppSignals, ConfigLoader, ConfigManager
from .machine_config_window import MachineConfigWindow
from .pi_file_editor_window import PiFileEditorWindow
from controllers.spotting_controller import SpottingController


class MainWindow(QMainWindow):
    """
    Main application window.
    Combines all views with menu bar and layout using Obsidian design guidelines.
    """

    def __init__(self, app_signals: AppSignals = None):
        """
        Initialize main window.

        Args:
            app_signals: Global application signals
        """
        super().__init__()
        self.app_signals = app_signals or AppSignals()
        self.current_mode = "buildplate"
        self.config_path = Path(__file__).parent.parent / "config" / "machine_config.json"

        # Window setup
        self.setWindowTitle("Klipper OpenSource Spotter - DOD Printing System")
        self.setGeometry(100, 100, 1400, 900)

        # Create menu bar
        self._create_menu_bar()

        # Mode display in top-right corner of the menu bar
        self._setup_mode_display()

        # Create central widget and layout FIRST so signal handlers are connected
        # before MainController tries to connect to Klipper
        # But we need main_controller for ControlsPanel, so create it without auto-connect
        from controllers.main_controller import MainController
        self.main_controller = MainController(self.app_signals, auto_connect=False)

        # Create central widget and layout (now can pass main_controller to ControlsPanel)
        self._create_layout()

        # Spotting controller
        self.spotting_controller = SpottingController(
            self.app_signals,
            self.main_controller.klipper_service,
            owns_klipper=False,
        )

        # Push initial grids to canvas so they render immediately
        if hasattr(self, "canvas_view") and hasattr(self, "grid_panel"):
            self.canvas_view.set_grids(self.grid_panel.get_grids_payload())

        # Create status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Not connected to Moonraker")

        # Keep mode label/status in sync with mode changes
        if self.app_signals:
            self.app_signals.mode_changed.connect(self._update_mode_display)
            self.app_signals.grid_definitions_changed.connect(
                self._on_grid_definitions_changed
            )
            # Reload UI from config when saved
            self.app_signals.config_saved.connect(self._on_config_saved)
            # Wire macro execution to main controller
            self.app_signals.macro_execute_requested.connect(self.main_controller.execute_macro)
            self.app_signals.connection_status_changed.connect(self._on_connection_status_changed)
            self.app_signals.connection_status_changed.emit(
                False,
                "Not connected to Moonraker",
            )
            self.app_signals.status_message.emit("Not connected to Moonraker")
        self._update_mode_display(self.current_mode)

        # Apply theme
        self._apply_obsidian_theme()

        # Connect after the window is visible so startup is not blocked by Moonraker.
        QTimer.singleShot(0, self._start_klipper_connection)

    def _create_menu_bar(self) -> None:
        """Create application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Load Config", self._on_load_config)
        file_menu.addAction("Save Config", self._on_save_config)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Config menu
        config_menu = menubar.addMenu("Config")
        config_menu.addAction("Machine Config", self._on_machine_config)
        config_menu.addAction("GUI Config", self._on_gui_config)

        # Calibration menu
        calibration_menu = menubar.addMenu("Calibration")
        calibration_menu.addAction("Calibration Editor", self._on_calibration_editor)
        calibration_menu.addAction("Reset Offsets", self._on_reset_offsets)

        # Mode menu
        mode_menu = menubar.addMenu("Mode")
        mode_menu.addAction("Buildplate", self._on_mode_buildplate)
        mode_menu.addAction("Roll-to-Roll", self._on_mode_roll_to_roll)

        self.start_gcode_action = QAction("Start_Gcode", self)
        self.start_gcode_action.triggered.connect(self._on_edit_start_gcode)
        menubar.addAction(self.start_gcode_action)

        self.end_gcode_action = QAction("End_Gcode", self)
        self.end_gcode_action.triggered.connect(self._on_edit_end_gcode)
        menubar.addAction(self.end_gcode_action)

        self.pi_files_action = QAction("Pi_Files", self)
        self.pi_files_action.setEnabled(False)
        self.pi_files_action.setStatusTip("Connect to Moonraker before opening Pi files")
        self.pi_files_action.triggered.connect(self._on_pi_file_editor)
        menubar.addAction(self.pi_files_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._on_about)
        help_menu.addAction("Documentation", self._on_documentation)

    def _setup_mode_display(self) -> None:
        """Place a mode label in the top-right corner of the menu bar."""
        self.mode_label = QLabel(self._format_mode_label(self.current_mode))
        self.mode_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.mode_label.setStyleSheet(
            "padding: 4px 10px; color: #cdd6f4; font-weight: bold;"
        )
        self.menuBar().setCornerWidget(self.mode_label, Qt.Corner.TopRightCorner)

    def _format_mode_label(self, mode: str) -> str:
        """Return display text for the current mode."""
        shorthand = "R2R" if mode == "roll-to-roll" else "Buildplate"
        return f"Mode: {shorthand}"

    def _update_mode_display(self, mode: str) -> None:
        """Update label and status bar when mode changes."""
        self.current_mode = mode
        if hasattr(self, "mode_label"):
            self.mode_label.setText(self._format_mode_label(mode))
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(self._format_mode_label(mode))

    def _on_connection_status_changed(self, connected: bool, message: str = "") -> None:
        """Mirror Moonraker connection state in the main status bar."""
        if hasattr(self, "pi_files_action"):
            self.pi_files_action.setEnabled(bool(connected))
        if connected:
            self.status_bar.showMessage("Connected to Moonraker")
            self.main_controller.logger.info("Pi file editor enabled after Moonraker connection")
        else:
            self.status_bar.showMessage(message or "Not connected to Moonraker")

    def _load_machine_config(self) -> dict:
        """Load the current machine config file, falling back to defaults."""
        try:
            return ConfigLoader.load_config(str(self.config_path))
        except FileNotFoundError:
            return ConfigLoader.get_default_machine_config()
        except Exception as exc:
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(f"Failed to load machine config: {exc}")
            return ConfigLoader.get_default_machine_config()

    def _save_machine_config(self, config: dict, message: str) -> None:
        """Persist the machine config and refresh the in-memory cache."""
        if ConfigLoader.save_config(str(self.config_path), config):
            ConfigManager.get_instance().reload()
            if self.app_signals:
                self.app_signals.config_saved.emit()
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(message)
        else:
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage("Failed to save machine config")

    def _edit_gcode_script(self, config_key: str, title: str) -> None:
        """Open a multiline editor for a configured G-code script."""
        config = self._load_machine_config()
        klipper = dict(config.get("klipper", {}))

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(700, 420)

        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setPlainText(str(klipper.get(config_key, "")))
        editor.setPlaceholderText("Enter one G-code command per line. Blank lines are ignored.")
        layout.addWidget(editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            klipper[config_key] = editor.toPlainText()
            config["klipper"] = klipper
            label = "Start G-code" if config_key == "start_gcode" else "End G-code"
            self._save_machine_config(config, f"Saved {label}")

    def _on_edit_start_gcode(self) -> None:
        self._edit_gcode_script("start_gcode", "Edit Start G-code")

    def _on_edit_end_gcode(self) -> None:
        self._edit_gcode_script("end_gcode", "Edit End G-code")

    def _on_pi_file_editor(self) -> None:
        """Open the Moonraker-backed Pi file editor."""
        service = self.main_controller.klipper_service
        self.main_controller.logger.info(
            f"Pi file editor requested; Moonraker connected={getattr(service, 'is_connected', False)} "
            f"host={getattr(service, 'host', '')}:{getattr(service, 'port', '')}"
        )
        if not getattr(service, "is_connected", False):
            self.main_controller.logger.warning("Pi file editor blocked: not connected to Moonraker")
            self.status_bar.showMessage("Cannot open Pi files: not connected to Moonraker")
            return
        try:
            self.main_controller.logger.info("Opening Pi file editor")
            dialog = PiFileEditorWindow(
                service,
                parent=self,
                logger=self.main_controller.logger.logger,
            )
            result = dialog.exec()
            self.main_controller.logger.info(f"Pi file editor closed with result={result}")
        except Exception as exc:
            self.main_controller.logger.logger.exception("Pi file editor crashed while opening or running")
            self.status_bar.showMessage(f"Pi file editor failed: {exc}")
            QMessageBox.critical(
                self,
                "Pi File Editor",
                f"Pi file editor failed:\n{exc}",
            )

    def _start_klipper_connection(self) -> None:
        """Connect to Moonraker in a background thread after the UI is ready."""
        worker = threading.Thread(
            target=self.main_controller._connect_to_klipper,
            daemon=True,
        )
        worker.start()

    def _create_layout(self) -> None:
        """Create main layout with panels."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar (Grid Control Panel)
        self.grid_panel = GridPanel(self.app_signals)
        main_layout.addWidget(self.grid_panel)

        # Center column: Canvas (top) and Camera controls (bottom)
        center_layout = QVBoxLayout()
        self.canvas_view = CanvasView(self.app_signals)
        center_layout.addWidget(self.canvas_view, 1)
        self.camera_panel = CameraPanel(self.app_signals)
        center_layout.addWidget(self.camera_panel)
        center_widget = QWidget()
        center_widget.setLayout(center_layout)
        main_layout.addWidget(center_widget, 1)

        # Right column: Machine controls (top) and Status/progress (bottom)
        right_layout = QVBoxLayout()
        self.controls_panel = ControlsPanel(self.main_controller, self.app_signals)
        right_layout.addWidget(self.controls_panel)
        self.status_panel = StatusPanel(self.app_signals)
        right_layout.addWidget(self.status_panel)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        main_layout.addWidget(right_widget)

    def _apply_obsidian_theme(self) -> None:
        """Apply Obsidian dark theme via stylesheet."""
        obsidian_theme = """
        QMainWindow {
            background-color: #1e1e2e;
            color: #cdd6f4;
        }
        
        QMenuBar {
            background-color: #313244;
            color: #cdd6f4;
            border-bottom: 1px solid #45475a;
        }
        
        QMenuBar::item:selected {
            background-color: #45475a;
        }
        
        QMenu {
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
        }
        
        QMenu::item:selected {
            background-color: #89b4fa;
            color: #1e1e2e;
        }
        
        QStatusBar {
            background-color: #313244;
            color: #cdd6f4;
            border-top: 1px solid #45475a;
        }
        
        QPushButton {
            background-color: #45475a;
            color: #cdd6f4;
            border: 1px solid #585b70;
            border-radius: 4px;
            padding: 5px 10px;
        }
        
        QPushButton:hover {
            background-color: #585b70;
        }
        
        QPushButton:pressed {
            background-color: #6c7086;
        }
        
        QLineEdit, QSpinBox, QDoubleSpinBox {
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 4px;
            padding: 5px;
        }
        
        QLabel {
            color: #cdd6f4;
        }
        
        QProgressBar {
            background-color: #313244;
            border: 1px solid #45475a;
            border-radius: 4px;
            text-align: center;
        }
        
        QProgressBar::chunk {
            background-color: #a6e3a1;
            border-radius: 3px;
        }
        
        QSlider::groove:horizontal {
            background-color: #45475a;
            height: 6px;
            border-radius: 3px;
        }
        
        QSlider::handle:horizontal {
            background-color: #89b4fa;
            width: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        
        QSlider::handle:horizontal:hover {
            background-color: #a6e3a1;
        }
        """
        self.setStyleSheet(obsidian_theme)

    def shutdown(self) -> None:
        """Stop background controllers and disconnect from Moonraker."""
        if hasattr(self, "spotting_controller") and self.spotting_controller:
            self.spotting_controller.shutdown()
        if hasattr(self, "main_controller") and self.main_controller:
            self.main_controller.shutdown()

    def closeEvent(self, event) -> None:
        """Ensure Moonraker subscriptions and worker threads are cleaned up."""
        self.shutdown()
        super().closeEvent(event)

    def _on_grid_definitions_changed(self, grids) -> None:
        """Push grid updates to the canvas for live redraws."""
        if hasattr(self, "canvas_view"):
            self.canvas_view.set_grids(grids)

    # Menu action handlers
    def _on_load_config(self) -> None:
        """Handle load config action."""
        self.status_bar.showMessage("Load config clicked")

    def _on_save_config(self) -> None:
        """Handle save config action (includes grids + valve links)."""
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save Machine Config",
            str(self.config_path),
            "JSON Files (*.json)",
        )
        if not target:
            return

        # Start from existing or defaults
        try:
            config = ConfigLoader.load_config(target)
        except FileNotFoundError:
            config = ConfigLoader.get_default_machine_config()
        except Exception as e:
            self.status_bar.showMessage(f"Failed to load existing config: {e}")
            config = ConfigLoader.get_default_machine_config()

        # Inject grids
        grids_payload = self.grid_panel.get_grids_payload()
        config["grids"] = grids_payload

        if ConfigLoader.save_config(target, config):
            self.status_bar.showMessage(f"Config saved: {Path(target).name}")
        else:
            self.status_bar.showMessage("Failed to save config")

    def _on_machine_config(self) -> None:
        """Handle machine config action."""
        dlg = MachineConfigWindow(self.app_signals, parent=self)
        dlg.exec()

    def _on_gui_config(self) -> None:
        """Handle GUI config action."""
        self.status_bar.showMessage("GUI config clicked")

    def _on_config_saved(self) -> None:
        """Reload config into UI after save."""
        cm = ConfigManager.get_instance()
        cm.reload()
        if hasattr(self, "grid_panel"):
            active_valves = [
                {"id": v.get("id", i), "name": v.get("name", f"Valve {v.get('id', i)}")}
                for i, v in enumerate(cm.available_valves())
                if bool(v.get("is_active", True))
            ] or [{"id": 0, "name": "Valve 0"}]
            self.grid_panel.set_available_valves(active_valves)
        # Notify canvas to redraw
        if self.app_signals:
            self.app_signals.canvas_updated.emit()
        # Update controls panel's config reference implicitly via ConfigManager

    def _on_calibration_editor(self) -> None:
        """Handle calibration editor action."""
        self.status_bar.showMessage("Calibration editor clicked")

    def _on_reset_offsets(self) -> None:
        """Handle reset offsets action."""
        self.status_bar.showMessage("Reset offsets clicked")

    def _on_mode_buildplate(self) -> None:
        """Handle buildplate mode selection."""
        self.app_signals.mode_changed.emit("buildplate")

    def _on_mode_roll_to_roll(self) -> None:
        """Handle roll-to-roll mode selection."""
        self.app_signals.mode_changed.emit("roll-to-roll")

    def _on_about(self) -> None:
        """Handle about action."""
        self.status_bar.showMessage("About clicked")

    def _on_documentation(self) -> None:
        """Handle documentation action."""
        self.status_bar.showMessage("Documentation clicked")
