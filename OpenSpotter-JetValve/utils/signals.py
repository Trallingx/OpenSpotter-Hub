"""
Application Signals
PyQt6 signals for event-driven communication between views and controllers.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class AppSignals(QObject):
    """
    Global application signals.
    Provides event bus for decoupled communication between components.
    """

    # Print job signals
    print_job_loaded = pyqtSignal(str)  # job_id
    print_started = pyqtSignal()
    print_paused = pyqtSignal()
    print_stopped = pyqtSignal()
    print_progress_updated = pyqtSignal(int, int)  # current_line, total_lines

    # Valve signals
    valve_fired = pyqtSignal(int, float)  # valve_id, duration_ms

    # Klipper macro signals
    macro_execute_requested = pyqtSignal(str)  # macro_command
    macro_response_received = pyqtSignal(str)  # response_text
    gcode_script_queued = pyqtSignal(int, object)  # jsonrpc_id, metadata
    gcode_script_completed = pyqtSignal(int, bool, str)  # jsonrpc_id, ok, response_text

    # Connection signals
    connection_status_changed = pyqtSignal(bool, str)  # connected (True/False), message

    # Canvas signals
    canvas_updated = pyqtSignal()
    mode_changed = pyqtSignal(str)  # "buildplate" or "roll-to-roll"
    zoom_changed = pyqtSignal(float)  # zoom_factor
    spot_clicked = pyqtSignal(int, int)  # valve_id, spot_id
    grid_definitions_changed = pyqtSignal(object)  # list of grid definitions

    # Gantry signals
    gantry_position_updated = pyqtSignal(float, float, float)  # x, y, z
    gantry_position_sample_updated = pyqtSignal(float, float, float, float)  # x, y, z, sample_time
    gantry_status_changed = pyqtSignal(str)  # "idle", "moving", "error"

    # Configuration signals
    config_loaded = pyqtSignal()
    config_saved = pyqtSignal()

    # Spotting control signals (requests from UI)
    spotting_start_requested = pyqtSignal(object)  # dict settings
    spotting_pause_requested = pyqtSignal()
    spotting_stop_requested = pyqtSignal()

    # Spotting progress signals (from controller)
    spotting_started = pyqtSignal()
    spotting_paused = pyqtSignal()
    spotting_stopped = pyqtSignal()
    spotting_finished = pyqtSignal()
    spotting_progress_updated = pyqtSignal(object)  # list of finished spot keys or tuples

    # Camera signals
    camera_frame_captured = pyqtSignal(object)  # np.ndarray
    camera_started = pyqtSignal()
    camera_stopped = pyqtSignal()

    # Calibration signals
    calibration_offset_updated = pyqtSignal(int, int, float, float)  # valve_id, spot_id, offset_x, offset_y

    # Status signals
    status_message = pyqtSignal(str)  # message
    error_occurred = pyqtSignal(str)  # error_message

    def __repr__(self):
        return "AppSignals()"


# Global instance
app_signals = AppSignals()
