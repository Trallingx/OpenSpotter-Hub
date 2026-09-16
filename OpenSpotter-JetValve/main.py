"""
Klipper OpenSource Spotter - Main Application Entrypoint
Drop-on-Demand (DOD) Printing System GUI

A professional PyQt6 application with Obsidian-like dark theme design
for controlling precision liquid dispensing systems.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from views import MainWindow
from utils import AppSignals
from services import LoggerService


def setup_application():
    """Initialize and configure the application."""
    # Create QApplication
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Klipper OpenSource Spotter")
    app.setApplicationVersion("0.1.0")
    # QApplication in PyQt6 does not expose setApplicationAuthor; keep name/version only

    # High DPI scaling: Qt6 enables this by default and the AA_* attributes were
    # removed in newer Qt6 versions, so no manual attribute toggles are needed.

    return app


def main():
    """Main application entry point."""
    # Setup application
    app = setup_application()

    # Initialize logging
    logger = LoggerService("dod_system")
    logger.info("=" * 60)
    logger.info("Klipper OpenSource Spotter v0.1.0 Starting")
    logger.info("=" * 60)

    # Create global app signals
    app_signals = AppSignals()

    # Create main window
    logger.info("Initializing main window...")
    main_window = MainWindow(app_signals)

    # Show window (windowed fullscreen / maximized)
    main_window.showMaximized()
    logger.info("Main window displayed")
    logger.info("Application ready for use")

    app.aboutToQuit.connect(main_window.shutdown)

    # Connect some example signals for testing
    app_signals.status_message.emit("Application started successfully")

    # Run application event loop
    exit_code = app.exec()

    logger.info("Application shutting down...")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
