"""
Main Controller
Orchestrates the entire application, coordinates between views, models, and services.
"""

import threading
from typing import Optional
from models import PrintJob, Valve
from services import KlipperService, CameraService, LoggerService
from utils import ConfigManager, AppSignals


class MainController:
    """
    Main application controller.
    Handles high-level orchestration, app state, and sequencing.
    """

    def __init__(self, app_signals: AppSignals = None, auto_connect: bool = True):
        """
        Initialize the main controller with services and state.
        
        Args:
            app_signals: AppSignals instance for event communication
            auto_connect: If True, attempt to connect to Klipper immediately.
                         If False, call connect() manually later.
        """
        self.logger = LoggerService()
        self.app_signals = app_signals
        
        # Load Klipper configuration
        self.cm = ConfigManager.get_instance()
        klipper_config = self.cm.get("klipper", {})
        host = klipper_config.get("host", "localhost")
        port = klipper_config.get("port", 7125)
        
        # Initialize Klipper service with app_signals for connection logging
        self.klipper_service = KlipperService(
            host=host,
            port=port,
            app_signals=app_signals,
            logger=self.logger.logger,
        )
        self.camera_service = CameraService()
        self.print_job: Optional[PrintJob] = None
        self.is_running = False
        
        # Auto-connect to Klipper on startup (unless deferred)
        if auto_connect:
            self._connect_to_klipper()
    
    def _connect_to_klipper(self):
        """Attempt to connect to Klipper via Moonraker."""
        if self.klipper_service.connect():
            self.logger.info("Successfully connected to Klipper")
            self._run_connect_gcode()
        else:
            self.logger.warning("Failed to connect to Klipper - check configuration and that Moonraker is running on the Pi")

    def _run_connect_gcode(self) -> bool:
        """Run configured G-code once after Moonraker connects."""
        script = str(self.cm.get("klipper.connect_gcode", "START_ARDUINO_VALVE_BRIDGE") or "")
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        if not lines:
            self.logger.debug("No connect G-code configured")
            return True

        self.logger.info(f"Running connect G-code with {len(lines)} line(s)")
        ok = True
        for line in lines:
            result = self.klipper_service.send_gcode(line)
            if isinstance(result, dict) and result.get("error"):
                self.logger.warning(f"Connect G-code failed on line '{line}': {result['error']}")
                ok = False
        return ok

    def initialize(self, print_job: PrintJob) -> bool:
        """
        Initialize the application with a print job.

        Args:
            print_job: PrintJob instance to run

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self.print_job = print_job
            self.logger.info(f"Initialized with print job: {print_job.job_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            return False

    def start_print(self) -> bool:
        """
        Start the print job.

        Returns:
            True if started successfully, False otherwise
        """
        if self.print_job is None:
            self.logger.error("No print job loaded")
            return False

        self.is_running = True
        self.logger.info("Print job started")
        return True

    def pause_print(self) -> bool:
        """Pause the current print job."""
        self.is_running = False
        self.logger.info("Print job paused")
        return True

    def stop_print(self) -> bool:
        """Stop and reset the current print job."""
        self.is_running = False
        if self.print_job:
            self.print_job.reset_progress()
        self.logger.info("Print job stopped")
        return True

    def shutdown(self) -> None:
        """Release controller-owned services and disconnect from Moonraker."""
        try:
            self.klipper_service.disconnect()
        except Exception as e:
            self.logger.debug(f"MainController shutdown cleanup failed: {e}")

    def fire_valve(self, valve_id: int, duration_ms: float = None) -> bool:
        """
        Fire a specific valve.

        Args:
            valve_id: ID of valve to fire
            duration_ms: Optional override duration

        Returns:
            True if successful, False otherwise
        """
        if self.print_job is None:
            self.logger.error("No print job loaded")
            return False

        try:
            valve = self.print_job.get_valve(valve_id)
            valve.fire(duration_ms)
            self.logger.info(
                f"Valve {valve_id} fired with configured valve timing"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to fire valve {valve_id}: {e}")
            return False

    def execute_macro(self, macro_command: str) -> bool:
        """
        Execute a Klipper gcode macro.

        Args:
            macro_command: Gcode macro command (e.g., 'SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0 POST_FIRE_WAIT=0 ON_MS=5.0 OFF_MS=2.0 CYCLES=1')

        Returns:
            True if the command was queued successfully, False otherwise
        """
        try:
            worker = threading.Thread(
                target=self._execute_macro_worker,
                args=(macro_command,),
                daemon=True,
            )
            worker.start()
            self.logger.info(f"Queued command: {macro_command}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to execute macro '{macro_command}': {e}")
            if self.app_signals:
                self.app_signals.macro_response_received.emit(f"ERROR: {e}")
            return False

    def _execute_macro_worker(self, macro_command: str) -> None:
        """Run macro execution in a background thread and emit console response."""
        try:
            command = macro_command.strip()

            # Keep GET_POSITION as a console alias for M114 so the response comes
            # from Moonraker/Klipper as raw console output.
            if command.upper() == "GET_POSITION":
                command = "M114"

            result = self.klipper_service.send_gcode(command)

            # Only emit fallback text for non-websocket paths; websocket messages
            # are forwarded directly by the service as raw console output.
            if isinstance(result, dict) and "queued" not in result and self.app_signals:
                self.app_signals.macro_response_received.emit(str(result))

            self.logger.info(f"Command completed: {macro_command}")
        except Exception as e:
            self.logger.error(f"Failed to execute macro '{macro_command}': {e}")
            if self.app_signals:
                self.app_signals.macro_response_received.emit(f"ERROR: {e}")

    def advance_line(self) -> bool:
        """
        Advance to the next print line.

        Returns:
            True if advanced, False if at end
        """
        if self.print_job is None:
            return False

        result = self.print_job.advance_line()
        if result:
            self.logger.info(
                f"Advanced to line {self.print_job.current_line}/"
                f"{self.print_job.num_lines}"
            )
        return result

    def get_status(self) -> dict:
        """Get current application status."""
        if self.print_job is None:
            return {"status": "idle", "is_running": False}

        return {
            "status": "running" if self.is_running else "idle",
            "is_running": self.is_running,
            "job_summary": self.print_job.get_summary(),
        }

    def __repr__(self):
        return f"MainController(running={self.is_running}, job={self.print_job})"
