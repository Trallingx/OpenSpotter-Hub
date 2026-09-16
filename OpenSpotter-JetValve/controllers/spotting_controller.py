"""
Spotting Controller
Runs spotting sequences across grids with snake-like motion and
configurable interleaving modes. Emits progress to AppSignals.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
import threading
import time
from typing import List, Dict, Tuple, Optional, Sequence, Iterator

from PyQt6.QtCore import QObject, QThread

from utils import AppSignals, ConfigManager
from services import KlipperService, LoggerService
from services.klipper_threads import KlipperPublisher, KlipperListener
from services.valve_macro_commands import build_shoot_command, build_valve_timing_command


@dataclass
class Spot:
    x: float
    y: float
    speed_mm_s: float
    valve_id: int
    grid_index: int
    row: int
    col: int


def spot_key(spot: Spot) -> str:
    return f"{spot.grid_index}:{spot.row}:{spot.col}:{spot.x:.3f},{spot.y:.3f},{spot.valve_id}"


@dataclass(frozen=True)
class _GridPlan:
    grid_index: int
    rows: int
    cols: int
    row_spacing: float
    col_spacing: float
    origin_x: float
    origin_y: float
    speed_mm_s: float
    valve_id: int


@dataclass(frozen=True)
class _RowSegment:
    start_index: int
    grid: _GridPlan
    row: int
    reverse: bool

    @property
    def end_index(self) -> int:
        return self.start_index + self.grid.cols


class SpotSequence(SequenceABC):
    """Indexed virtual spot plan that avoids materializing every spot."""

    def __init__(self, row_segments: Sequence[_RowSegment], total_spots: int) -> None:
        self._row_segments = list(row_segments)
        self._starts = [segment.start_index for segment in self._row_segments]
        self._total_spots = int(total_spots)
        self._rows_by_grid = {
            segment.grid.grid_index: segment.grid.rows for segment in self._row_segments
        }
        self._valve_ids = sorted({segment.grid.valve_id for segment in self._row_segments})

    def __len__(self) -> int:
        return self._total_spots

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(self._total_spots)
            return [self[i] for i in range(start, stop, step)]

        if index < 0:
            index += self._total_spots
        if index < 0 or index >= self._total_spots:
            raise IndexError(index)

        segment_index = bisect_right(self._starts, index) - 1
        segment = self._row_segments[segment_index]
        offset = index - segment.start_index
        col = segment.grid.cols - 1 - offset if segment.reverse else offset
        return Spot(
            x=segment.grid.origin_x + col * segment.grid.col_spacing,
            y=segment.grid.origin_y + segment.row * segment.grid.row_spacing,
            speed_mm_s=segment.grid.speed_mm_s,
            valve_id=segment.grid.valve_id,
            grid_index=segment.grid.grid_index,
            row=segment.row,
            col=col,
        )

    def __iter__(self) -> Iterator[Spot]:
        for index in range(self._total_spots):
            yield self[index]

    def valve_ids(self) -> List[int]:
        return list(self._valve_ids)

    def rows_for_grid(self, grid_index: int) -> int:
        return int(self._rows_by_grid.get(grid_index, 0))


class SpottingController(QObject):
    def __init__(
        self,
        app_signals: AppSignals,
        klipper_service: Optional[KlipperService] = None,
        parent=None,
        owns_klipper: bool = True,
    ) -> None:
        super().__init__(parent)
        self.signals = app_signals
        self.cm = ConfigManager.get_instance()
        self.logger = LoggerService()
        self.klipper = klipper_service or KlipperService(logger=self.logger.logger)
        self._owns_klipper = owns_klipper if klipper_service is not None else True
        self.worker: Optional[SpottingWorker] = None
        self.sequence: Sequence[Spot] = []
        self.finished_keys: List[str] = []
        self._finished_key_set: set[str] = set()
        self._latest_completed_row_by_grid: Dict[int, int] = {}
        self._current_complete_index = 0
        self._completion_event = threading.Event()
        self._dispatch_lock = threading.Lock()
        self._dispatch_window_size = 25
        self._dispatch_window_cap = 25
        self._dispatch_batch_size = 5
        self._dispatch_refill_threshold = 13
        self._next_refill_complete_index = 0
        self._next_dispatch_index = 0
        self.running = False
        self.lines_per_block = 1
        self.full_grid_mode = False
        self.speed_mm_s = 1000.0
        self._cursor = 0
        self._prev_pos: Optional[Tuple[float, float]] = None
        self.current_grids: List[Dict] = self.cm.get("grids", [])
        self.stop_requested: bool = False
        self._spotting_session_active = False
        self._end_gcode_sent = False
        self._spotting_completion_source = "position"
        self._pending_command_spots: Dict[int, str] = {}
        self._completed_command_ids: set[int] = set()
        self._completed_command_spot_keys: set[str] = set()
        self._position_completion_started_at = 0.0
        self._position_start_position: Tuple[float, float] = (0.0, 0.0)
        self._position_path_points: List[Tuple[float, float]] = []
        self._position_path_distances: List[float] = []
        self._position_spot_distances: List[float] = []
        self._position_completion_tolerance = 0.75
        self._last_position_completion_sample_time = 0.0
        self._canvas_mode = "buildplate"

        # Connect control requests
        self.signals.spotting_start_requested.connect(self.start)
        self.signals.spotting_pause_requested.connect(self.pause)
        self.signals.spotting_stop_requested.connect(self.stop)
        self.signals.error_occurred.connect(self._on_error_occurred)
        self.signals.macro_response_received.connect(self._on_macro_response_received)
        self.signals.gcode_script_queued.connect(self._on_gcode_script_queued)
        self.signals.gcode_script_completed.connect(self._on_gcode_script_completed)
        # Track live grid changes from UI
        self.signals.grid_definitions_changed.connect(self.set_grids)
        self.signals.mode_changed.connect(self._on_mode_changed)
        self.signals.gantry_position_sample_updated.connect(self._on_gantry_position_sample_updated)

    def set_grids(self, grids: List[Dict]) -> None:
        """Update current grids from UI changes."""
        self.current_grids = grids or []

    def _on_mode_changed(self, mode: str) -> None:
        self._canvas_mode = "roll-to-roll" if mode == "roll-to-roll" else "buildplate"

    def build_sequence(self, grids: List[Dict]) -> SpotSequence:
        """Build an indexed virtual spot sequence with snake row ordering."""
        row_segments: List[_RowSegment] = []
        cursor = 0
        row_parity = 0
        active_grids = [g for g in grids if bool(g.get("active", True))]
        grid_plans: List[_GridPlan] = []
        for gi, g in enumerate(active_grids):
            rows = max(0, int(g.get("rows", 0)))
            cols = max(0, int(g.get("cols", 0)))
            grid_plans.append(
                _GridPlan(
                    grid_index=gi,
                    rows=rows,
                    cols=cols,
                    row_spacing=float(g.get("row_spacing", 10.0)),
                    col_spacing=float(g.get("col_spacing", 10.0)),
                    origin_x=float(g.get("origin_x", 0.0)),
                    origin_y=float(g.get("origin_y", 0.0)),
                    speed_mm_s=float(g.get("speed_mm_s", self.speed_mm_s)),
                    valve_id=int(g.get("valve_id", 0)),
                )
            )

        def append_row(grid: _GridPlan, row: int) -> None:
            nonlocal cursor, row_parity
            if grid.cols <= 0:
                return
            row_segments.append(
                _RowSegment(
                    start_index=cursor,
                    grid=grid,
                    row=row,
                    reverse=bool(row_parity % 2),
                )
            )
            cursor += grid.cols
            row_parity += 1

        if self.full_grid_mode:
            for grid in grid_plans:
                for row in range(grid.rows):
                    append_row(grid, row)
        else:
            max_rows = max((grid.rows for grid in grid_plans), default=0)
            for row_start in range(0, max_rows, self.lines_per_block):
                for grid in grid_plans:
                    for row in range(row_start, min(row_start + self.lines_per_block, grid.rows)):
                        append_row(grid, row)

        return SpotSequence(row_segments, cursor)

    def _shoot_command_for_valve(self, valve_id: int) -> str:
        valves = ConfigManager.get_instance().available_valves()
        schema = {f.get("name"): f for f in ConfigManager.get_instance().valve_fields()}
        valve = next((vv for vv in valves if int(vv.get("id", -1)) == int(valve_id)), {})
        return build_shoot_command(valve_id, valve, schema, self.cm.get("klipper", {}))

    def start(self, settings: Dict) -> None:
        """Start spotting with given settings dict."""
        self.logger.info("Spotting start requested")
        self.lines_per_block = int(settings.get("lines_per_block", 1))
        self.full_grid_mode = bool(settings.get("full_grid_mode", False))
        self.speed_mm_s = float(settings.get("speed_mm_s", 1000.0))
        self.stop_requested = False

        # Use live UI grids first, then any provided, then config fallback
        grids = settings.get("grids") or self.current_grids or self.cm.get("grids", [])
        self.sequence = self.build_sequence(grids)
        if not self.sequence:
            self.logger.warning("Spotting aborted: no active grids configured")
            self.signals.error_occurred.emit("Spotting aborted: no active grids configured")
            self.signals.spotting_stopped.emit()
            return
        self.logger.info(f"Built spotting sequence with {len(self.sequence)} spots")
        self.finished_keys = []
        self._finished_key_set.clear()
        self._latest_completed_row_by_grid.clear()
        self._current_complete_index = 0
        self._completion_event.clear()
        self._dispatch_window_cap = self._configured_dispatch_window_cap()
        self._dispatch_refill_threshold = self._configured_dispatch_refill_threshold()
        self._dispatch_batch_size = self._configured_dispatch_batch_size()
        self._dispatch_window_size = self._resolve_dispatch_window_size(len(self.sequence))
        self._spotting_completion_source = self._resolve_spotting_completion_source()
        self._next_dispatch_index = 0
        self._next_refill_complete_index = 0
        self._pending_command_spots.clear()
        self._completed_command_ids.clear()
        self._completed_command_spot_keys.clear()
        self._position_completion_started_at = time.monotonic()
        self._position_path_points = []
        self._position_path_distances = []
        self._position_spot_distances = []
        self._position_completion_tolerance = self._configured_position_completion_tolerance()
        self._last_position_completion_sample_time = 0.0
        self._cursor = 0
        self._prev_pos = None
        self.running = True
        self._spotting_session_active = True
        self._end_gcode_sent = False
        self.signals.spotting_progress_updated.emit([])

        host = self.cm.get("klipper.host", "localhost")
        port = int(self.cm.get("klipper.port", 7125))
        self.logger.info(f"Using Moonraker connection at {host}:{port}")
        if not self.klipper.is_connected and not self.klipper.connect():
            self.logger.error("Spotting aborted: failed to connect to Moonraker")
            self.signals.error_occurred.emit("Spotting aborted: failed to connect to Moonraker")
            self.signals.spotting_stopped.emit()
            self.running = False
            self._spotting_session_active = False
            return
        if self.klipper.is_connected:
            self.logger.info("Reusing existing Moonraker connection")

        toolhead_status = self.klipper.get_cached_toolhead_status()
        if not toolhead_status.get("connected"):
            self.logger.error("Spotting aborted: Klippy is disconnected")
            self.signals.error_occurred.emit("Spotting aborted: Klippy is disconnected")
            self.signals.spotting_stopped.emit()
            self.running = False
            self._spotting_session_active = False
            return

        if not self._run_configured_gcode("start_gcode", "Start"):
            self._finalize_spotting(False)
            return

        try:
            homing_status_wait_s = max(
                0.0,
                float(self.cm.get("klipper.homing_status_wait_ms", 1000)) / 1000.0,
            )
        except (TypeError, ValueError):
            homing_status_wait_s = 1.0
        toolhead_status = self.klipper.wait_for_homed_axes({"x", "y"}, timeout=homing_status_wait_s)
        if not toolhead_status.get("connected"):
            self.logger.error("Spotting aborted: Klippy is disconnected")
            self.signals.error_occurred.emit("Spotting aborted: Klippy is disconnected")
            self._finalize_spotting(False)
            return

        homed_axes = str(toolhead_status.get("homed_axes", ""))
        if not ({"x", "y"} <= set(homed_axes.lower())):
            self.logger.error("Spotting aborted: toolhead must be homed on X and Y before sending synced SHOOT commands")
            self.signals.error_occurred.emit(
                "Spotting aborted: toolhead must be homed on X and Y before sending synced SHOOT commands"
            )
            self._finalize_spotting(False)
            return
        self.logger.info(f"Moonraker connected; toolhead homed axes: {homed_axes}")
        position = toolhead_status.get("position", {})
        try:
            start_position = (
                float(position.get("x", 0.0)),
                float(position.get("y", 0.0)),
            )
        except (TypeError, ValueError):
            start_position = (0.0, 0.0)
        self._build_position_completion_path(start_position)
        self._prev_pos = None

        if not self._prepare_valve_timing():
            self._finalize_spotting(False)
            return

        # Start publisher/listener threads
        self.logger.debug("Starting Klipper publisher and listener threads")
        self._klipper_publisher = KlipperPublisher(self.klipper, self.signals)
        try:
            listener_interval_ms = int(self.cm.get("klipper.position_poll_interval_ms", 100))
        except (TypeError, ValueError):
            listener_interval_ms = 100
        self._klipper_listener = KlipperListener(
            self.klipper,
            self.signals,
            interval_ms=listener_interval_ms,
        )
        self._klipper_publisher.start()
        self._klipper_listener.start()

        # Start worker thread to process sequence off the GUI thread
        self.signals.spotting_started.emit()
        self.signals.print_progress_updated.emit(0, len(self.sequence))
        self.worker = SpottingWorker(
            sequence=self.sequence,
            speed_mm_s=self.speed_mm_s,
            klipper_service=self.klipper,
            klipper_publisher=getattr(self, "_klipper_publisher", None),
            app_signals=self.signals,
            valve_configs=self.cm.available_valves(),
            valve_schema=self.cm.valve_fields(),
            completion_event=self._completion_event,
        )
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.safety_stopped.connect(self._on_safety_stopped)
        self.worker.start()
        self.logger.info(
            f"Spotting worker started; send-ahead {self._dispatch_window_size} "
            f"(configured {self._dispatch_window_cap}, refill after "
            f"{self._dispatch_refill_threshold} complete, request batch "
            f"{self._dispatch_batch_size}) "
            f"for {len(self.sequence)} planned spots"
        )
        self._pump_dispatch_window()

    def pause(self) -> None:
        if not self.running or not self.worker:
            return
        self.worker.request_pause()
        self.running = False
        self.logger.info("Spotting paused")
        self.signals.spotting_paused.emit()

    def stop(self) -> None:
        self.stop_requested = True
        self.logger.info("Spotting stop requested; stopping local dispatch without emergency stop")
        self.running = False
        if self.worker:
            self.worker.request_stop_safely()
            self._completion_event.set()
            self._stop_klipper_threads()
            return
        self._cursor = 0
        self._prev_pos = None
        self.finished_keys = []
        self._finished_key_set.clear()
        self._latest_completed_row_by_grid.clear()
        self.signals.spotting_stopped.emit()
        self._stop_klipper_threads()

    def _stop_klipper_threads(self) -> None:
        """Stop background Klipper publisher/listener threads if running."""
        if hasattr(self, "_klipper_publisher") and self._klipper_publisher:
            self._klipper_publisher.stop(clear_pending=True)
            self._klipper_publisher.wait(1000)
        if hasattr(self, "_klipper_listener") and self._klipper_listener:
            self._klipper_listener.stop()
            self._klipper_listener.wait(1000)

    def _run_configured_gcode(self, config_key: str, phase_name: str) -> bool:
        """Send configured G-code lines sequentially before or after spotting."""
        script = str(self.cm.get(f"klipper.{config_key}", "") or "")
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        if not lines:
            self.logger.debug(f"No {phase_name} G-code configured")
            return True

        self.logger.info(f"Running {phase_name} G-code with {len(lines)} line(s)")
        for line in lines:
            result = self.klipper.send_gcode(line)
            if isinstance(result, dict) and result.get("error"):
                self.logger.error(f"{phase_name} G-code failed on line '{line}': {result['error']}")
                return False
        return True

    def _valve_config(self, valve_id: int) -> Dict:
        return next(
            (vv for vv in self.cm.available_valves() if int(vv.get("id", -1)) == int(valve_id)),
            {},
        )

    def _valve_schema(self) -> Dict:
        return {f.get("name"): f for f in self.cm.valve_fields()}

    def _valve_trigger_mode(self) -> str:
        return str(self.cm.get("klipper.valve_trigger_mode", "usb") or "usb").strip().lower()

    def _resolve_spotting_completion_source(self) -> str:
        configured = str(self.cm.get("klipper.spotting_completion_source", "") or "").strip().lower()
        if configured in {"position", "command_response", "macro_response"}:
            return configured
        return "position" if self._valve_trigger_mode() == "mcu" else "macro_response"

    def _prepare_valve_timing(self) -> bool:
        """Preload Arduino timing before Pi-MCU edge-triggered spotting starts."""
        if self._valve_trigger_mode() != "mcu":
            return True

        valve_ids_for_sequence = getattr(self.sequence, "valve_ids", None)
        if callable(valve_ids_for_sequence):
            valve_ids = [int(valve_id) for valve_id in valve_ids_for_sequence()]
        else:
            valve_ids = sorted({int(spot.valve_id) for spot in self.sequence})
        unsupported = [valve_id for valve_id in valve_ids if valve_id not in {0, 1}]
        if unsupported:
            message = "Spotting aborted: MCU trigger mode currently supports only VALVE=0 and VALVE=1"
            self.logger.error(message)
            self.signals.error_occurred.emit(message)
            return False

        schema = self._valve_schema()
        for valve_id in valve_ids:
            command = build_valve_timing_command(valve_id, self._valve_config(valve_id), schema)
            self.logger.info(f"Preloading Arduino valve timing for VALVE={valve_id}")
            result = self.klipper.send_gcode(command)
            if isinstance(result, dict) and result.get("error"):
                self.logger.error(f"Valve timing preload failed: {result['error']}")
                self.signals.error_occurred.emit(f"Valve timing preload failed: {result['error']}")
                return False
        return True

    def _finalize_spotting(self, finished: bool) -> None:
        """Stop threads, run end G-code once, and emit the final spotting signal."""
        if not self._spotting_session_active:
            return

        if not self._end_gcode_sent:
            self._end_gcode_sent = True
            self._run_configured_gcode("end_gcode", "End")

        self.running = False
        self._spotting_session_active = False
        self._cursor = 0
        self._prev_pos = None
        self._pending_command_spots.clear()
        self._completed_command_ids.clear()
        self._completed_command_spot_keys.clear()
        self._stop_klipper_threads()

        if finished:
            self.signals.spotting_finished.emit()
        else:
            self.signals.spotting_stopped.emit()

    def shutdown(self) -> None:
        """Stop spotting workers and release the Moonraker client if owned here."""
        if self.running or self._spotting_session_active:
            self.stop_requested = True
        if self.worker:
            self.worker.request_stop_safely()
            self._completion_event.set()
            self._stop_klipper_threads()
            self.worker.wait(3000)
        if self._spotting_session_active:
            self._finalize_spotting(False)
        self._stop_klipper_threads()
        if self._owns_klipper and self.klipper:
            try:
                self.klipper.disconnect()
            except Exception as e:
                self.logger.debug(f"SpottingController shutdown cleanup failed: {e}")

    def _spot_key(self, spot: Spot) -> str:
        return spot_key(spot)

    def _mark_spot_complete(self, spot: Spot) -> None:
        key = self._spot_key(spot)
        if key in self._finished_key_set:
            return
        self._latest_completed_row_by_grid[int(spot.grid_index)] = int(spot.row)
        self._finished_key_set.add(key)
        self.finished_keys.append(key)
        total = len(self.sequence)
        if self._is_r2r_mode():
            self._trim_r2r_finished_keys()
        completed = min(total, max(self._current_complete_index, len(self._finished_key_set)))
        if completed == 1 or completed == total or completed % 25 == 0:
            self.logger.debug(f"Spot fire completed {completed}/{total}")
        self.signals.spotting_progress_updated.emit(list(self.finished_keys))
        self.signals.print_progress_updated.emit(completed, total)
        if completed >= total:
            self._completion_event.set()

    def _is_r2r_mode(self) -> bool:
        return self._canvas_mode == "roll-to-roll"

    def _trim_r2r_finished_keys(self) -> None:
        """Keep only the current display rows in R2R progress payloads."""
        keep_rows_by_grid: Dict[int, set[int]] = {}
        for grid_index, latest_row in self._latest_completed_row_by_grid.items():
            total_rows = self._rows_for_grid(grid_index)
            if total_rows > 0 and latest_row >= total_rows - 1:
                keep_rows_by_grid[grid_index] = {max(0, total_rows - 2), total_rows - 1}
            else:
                keep_rows_by_grid[grid_index] = {latest_row}

        kept: List[str] = []
        for key in self.finished_keys:
            parsed = self._parse_spot_key_parts(key)
            if parsed is None:
                continue
            grid_index, row, _ = parsed
            if row in keep_rows_by_grid.get(grid_index, set()):
                kept.append(key)

        self.finished_keys = kept
        self._finished_key_set = set(kept)

    def _rows_for_grid(self, grid_index: int) -> int:
        rows_for_grid = getattr(self.sequence, "rows_for_grid", None)
        if callable(rows_for_grid):
            return int(rows_for_grid(grid_index))

        rows = [
            int(spot.row)
            for spot in self.sequence
            if int(spot.grid_index) == int(grid_index)
        ]
        return max(rows) + 1 if rows else 0

    @staticmethod
    def _parse_spot_key_parts(key: str) -> Optional[Tuple[int, int, int]]:
        try:
            prefix = str(key).split(",", 1)[0]
            grid_index, row, col, _ = prefix.split(":", 3)
            return int(grid_index), int(row), int(col)
        except (TypeError, ValueError):
            return None

    def _configured_dispatch_window_cap(self) -> int:
        """Return the configured maximum not-yet-completed spots to keep queued."""
        try:
            return max(1, int(self.cm.get("klipper.dispatch_window_spots", 25)))
        except (TypeError, ValueError):
            return 25

    def _configured_dispatch_batch_size(self) -> int:
        """Return the configured maximum number of spots per Moonraker script request."""
        try:
            configured = int(self.cm.get("klipper.dispatch_batch_spots", 5))
        except (TypeError, ValueError):
            configured = 5
        return max(1, min(configured, self._dispatch_window_cap))

    def _configured_dispatch_refill_threshold(self) -> int:
        """Return how many completed spots trigger the next send-ahead burst."""
        default_threshold = max(1, (self._dispatch_window_cap + 1) // 2)
        try:
            configured = int(
                self.cm.get("klipper.dispatch_refill_threshold_spots", default_threshold)
            )
        except (TypeError, ValueError):
            configured = default_threshold
        return max(1, min(configured, self._dispatch_window_cap))

    def _configured_position_completion_tolerance(self) -> float:
        """Return a practical tolerance for matching realtime positions to the planned path."""
        try:
            configured = float(self.cm.get("klipper.spot_position_tolerance_mm", 0.75))
        except (TypeError, ValueError):
            configured = 0.75
        return max(0.75, configured)

    def _resolve_dispatch_window_size(self, total_spots: int) -> int:
        """Use the whole job for small grids, but never exceed the burst size."""
        if total_spots <= 0:
            return 0
        return min(total_spots, self._dispatch_window_cap)

    def _pump_dispatch_window(self) -> None:
        """Top up the send-ahead buffer once enough queued spots complete."""
        if not self.running or not self.worker or not self.sequence:
            return

        with self._dispatch_lock:
            if self._next_dispatch_index == 0:
                if self._dispatch_next_burst_locked():
                    self._next_refill_complete_index = min(
                        len(self.sequence),
                        self._dispatch_refill_threshold,
                )
                return

            if (
                self._next_dispatch_index >= len(self.sequence)
                or self._current_complete_index < self._next_refill_complete_index
            ):
                return

            if not self._dispatch_next_burst_locked():
                return
            self._next_refill_complete_index = min(
                len(self.sequence),
                self._current_complete_index + self._dispatch_refill_threshold,
            )

    def _dispatch_next_burst_locked(self) -> bool:
        """Dispatch enough spots to refill the send-ahead buffer."""
        remaining = len(self.sequence) - self._next_dispatch_index
        in_flight = max(0, self._next_dispatch_index - self._current_complete_index)
        available_window = max(0, self._dispatch_window_size - in_flight)
        burst_count = min(available_window, remaining)
        if burst_count <= 0:
            return False

        burst_limit = self._next_dispatch_index + burst_count
        if self._can_batch_dispatch() and hasattr(self.worker, "_dispatch_spots"):
            while self._next_dispatch_index < burst_limit:
                batch_count = min(
                    self._dispatch_batch_size,
                    burst_limit - self._next_dispatch_index,
                )
                batch_limit = self._next_dispatch_index + batch_count
                spots = self.sequence[self._next_dispatch_index:batch_limit]
                if not spots:
                    return False
                if len(spots) == 1:
                    self.worker._dispatch_spot(spots[0])
                else:
                    self.worker._dispatch_spots(spots)
                self._next_dispatch_index = batch_limit
            return True

        while self._next_dispatch_index < burst_limit:
            spot = self.sequence[self._next_dispatch_index]
            self.worker._dispatch_spot(spot)
            self._next_dispatch_index += 1
        return True

    def _can_batch_dispatch(self) -> bool:
        """Batch only the MCU position-completion path, where response ids are not used."""
        trigger_mode = str(self.cm.get("klipper.valve_trigger_mode", "mcu") or "").strip().lower()
        return self._spotting_completion_source == "position" and trigger_mode == "mcu"

    def _position_matches_spot(self, x: float, y: float, spot: Spot) -> bool:
        tolerance = 0.25
        return abs(x - spot.x) <= tolerance and abs(y - spot.y) <= tolerance

    def _position_crossed_spot(
        self,
        previous: Optional[Tuple[float, float]],
        current: Tuple[float, float],
        spot: Spot,
    ) -> bool:
        if previous is None:
            return False

        px, py = previous
        cx, cy = current
        dx = cx - px
        dy = cy - py
        length_sq = dx * dx + dy * dy
        if length_sq <= 0:
            return False

        projection = ((spot.x - px) * dx + (spot.y - py) * dy) / length_sq
        if projection < 0.0 or projection > 1.0:
            return False

        nearest_x = px + projection * dx
        nearest_y = py + projection * dy
        tolerance = 0.75
        return abs(nearest_x - spot.x) <= tolerance and abs(nearest_y - spot.y) <= tolerance

    def _build_position_completion_path(self, start_position: Tuple[float, float]) -> None:
        """Remember the path start; completion projects only the active window."""
        self._position_start_position = start_position
        self._position_path_points = [start_position]
        self._position_path_distances = [0.0]
        self._position_spot_distances = []

    def _progress_along_position_path(self, current: Tuple[float, float]) -> Optional[float]:
        """Project the current realtime position onto the planned spot path."""
        window_limit = min(self._next_dispatch_index, len(self.sequence))
        _, progress, _ = self._position_window_progress(current, window_limit)
        return progress

    def _position_window_progress(
        self,
        current: Tuple[float, float],
        window_limit: int,
    ) -> Tuple[int, Optional[float], List[float]]:
        """Project current position onto the dispatched, not-yet-completed path window."""
        base_index = self._current_complete_index
        if not self.sequence or base_index >= window_limit:
            return base_index, None, []

        if base_index == 0:
            start = self._position_start_position
        else:
            previous_spot = self.sequence[base_index - 1]
            start = (float(previous_spot.x), float(previous_spot.y))

        points = [start]
        for index in range(base_index, window_limit):
            spot = self.sequence[index]
            points.append((float(spot.x), float(spot.y)))

        distances = [0.0]
        for index in range(1, len(points)):
            px, py = points[index - 1]
            nx, ny = points[index]
            dx = nx - px
            dy = ny - py
            distances.append(distances[-1] + (dx * dx + dy * dy) ** 0.5)

        cx, cy = current
        best_distance_sq = None
        best_progress = None

        for index in range(0, len(points) - 1):
            px, py = points[index]
            nx, ny = points[index + 1]
            dx = nx - px
            dy = ny - py
            length_sq = dx * dx + dy * dy
            if length_sq <= 0:
                projection = 1.0
                nearest_x = nx
                nearest_y = ny
                segment_length = 0.0
            else:
                projection = ((cx - px) * dx + (cy - py) * dy) / length_sq
                if projection < 0.0 or projection > 1.0:
                    continue
                nearest_x = px + projection * dx
                nearest_y = py + projection * dy
                segment_length = length_sq ** 0.5

            distance_sq = (cx - nearest_x) ** 2 + (cy - nearest_y) ** 2
            if best_distance_sq is None or distance_sq < best_distance_sq:
                best_distance_sq = distance_sq
                best_progress = distances[index] + projection * segment_length

        if best_distance_sq is None:
            return base_index, None, distances[1:]
        if best_distance_sq > self._position_completion_tolerance * self._position_completion_tolerance:
            return base_index, None, distances[1:]
        return base_index, best_progress, distances[1:]

    def _segment_spot_progress(
        self,
        previous: Tuple[float, float],
        current: Tuple[float, float],
        spot: Spot,
    ) -> Optional[float]:
        """Return segment progress for a reached spot, or None when not reached."""
        px, py = previous
        cx, cy = current
        dx = cx - px
        dy = cy - py
        length_sq = dx * dx + dy * dy

        if length_sq <= 0:
            return 0.0 if self._position_matches_spot(cx, cy, spot) else None

        projection = ((spot.x - px) * dx + (spot.y - py) * dy) / length_sq
        if projection < 0.0 or projection > 1.0:
            return None

        nearest_x = px + projection * dx
        nearest_y = py + projection * dy
        tolerance = 0.75
        if abs(nearest_x - spot.x) <= tolerance and abs(nearest_y - spot.y) <= tolerance:
            return projection
        return None

    def _crossed_window_progress(
        self,
        previous: Tuple[float, float],
        current: Tuple[float, float],
        base_index: int,
        window_limit: int,
        spot_distances: Sequence[float],
    ) -> Optional[float]:
        """Return the farthest ordered spot crossed by a sparse position sample."""
        crossed_distance = None
        for index in range(base_index, window_limit):
            local_index = index - base_index
            if local_index < 0 or local_index >= len(spot_distances):
                break
            spot = self.sequence[index]
            if not (
                self._position_crossed_spot(previous, current, spot)
                or self._position_matches_spot(current[0], current[1], spot)
            ):
                break
            crossed_distance = spot_distances[local_index]
        return crossed_distance

    def _on_gantry_position_sample_updated(self, x: float, y: float, z: float, sample_time: float) -> None:
        self._on_gantry_position_updated(x, y, z, sample_time=sample_time)

    def _on_gantry_position_updated(
        self,
        x: float,
        y: float,
        z: float,
        sample_time: Optional[float] = None,
    ) -> None:
        if (
            self._spotting_completion_source != "position"
            or not self.running
            or not self.sequence
        ):
            self._prev_pos = (x, y)
            return
        if sample_time is not None and sample_time < self._position_completion_started_at:
            return
        if (
            sample_time is not None
            and sample_time <= self._last_position_completion_sample_time
        ):
            return
        if sample_time is not None:
            self._last_position_completion_sample_time = sample_time

        previous = self._prev_pos
        current = (x, y)
        self._prev_pos = current

        window_limit = min(self._next_dispatch_index, len(self.sequence))
        base_index, path_progress, spot_distances = self._position_window_progress(current, window_limit)
        if path_progress is None and previous is not None:
            crossed_distance = self._crossed_window_progress(previous, current, base_index, window_limit, spot_distances)
            if crossed_distance is not None:
                path_progress = crossed_distance
        if path_progress is None:
            return

        completed_any = False
        while self._current_complete_index < window_limit:
            index = self._current_complete_index
            local_index = index - base_index
            if local_index < 0 or local_index >= len(spot_distances):
                break
            spot_distance = spot_distances[local_index]
            if spot_distance > path_progress + self._position_completion_tolerance:
                break
            spot = self.sequence[index]
            self._current_complete_index += 1
            self._mark_spot_complete(spot)
            completed_any = True

        if completed_any and self._current_complete_index < len(self.sequence):
            self._pump_dispatch_window()

    def _on_macro_response_received(self, message: str) -> None:
        if not self.running or not self._spotting_session_active or not self.sequence:
            return

        text = str(message)
        if text.startswith("!!") or text.startswith("ERR arduino valve bridge"):
            self.logger.error(f"Spotting aborted after Klipper response: {text}")
            if self.worker:
                self.worker.request_stop_safely()
            self._completion_event.set()
            self._finalize_spotting(False)
            return

        if (
            self._spotting_completion_source != "macro_response"
            or "Command {arduino_valve_fire} finished" not in text
        ):
            return

        if self._current_complete_index >= len(self.sequence):
            return

        spot = self.sequence[self._current_complete_index]
        self._current_complete_index += 1
        self._mark_spot_complete(spot)

        if self._current_complete_index < len(self.sequence):
            self._pump_dispatch_window()

    def _on_gcode_script_queued(self, response_id: int, metadata: object) -> None:
        if (
            self._spotting_completion_source != "command_response"
            or not self.running
            or not self._spotting_session_active
        ):
            return

        key = str(metadata)
        if response_id in self._completed_command_ids:
            self._completed_command_ids.remove(response_id)
            self._completed_command_spot_keys.add(key)
            self._drain_completed_command_spots()
            return

        self._pending_command_spots[int(response_id)] = key

    def _on_gcode_script_completed(self, response_id: int, ok: bool, response_text: str) -> None:
        if (
            self._spotting_completion_source != "command_response"
            or not self.running
            or not self._spotting_session_active
        ):
            return

        response_id = int(response_id)
        if not ok:
            self.logger.error(f"Spotting aborted after Klipper command response: {response_text}")
            if self.worker:
                self.worker.request_stop_safely()
            self._completion_event.set()
            self._finalize_spotting(False)
            return

        key = self._pending_command_spots.pop(response_id, None)
        if key is None:
            self._completed_command_ids.add(response_id)
            return

        self._completed_command_spot_keys.add(key)
        self._drain_completed_command_spots()

    def _drain_completed_command_spots(self) -> None:
        while self._current_complete_index < len(self.sequence):
            spot = self.sequence[self._current_complete_index]
            spot_key = self._spot_key(spot)
            if spot_key not in self._completed_command_spot_keys:
                break
            self._completed_command_spot_keys.remove(spot_key)
            self._current_complete_index += 1
            self._mark_spot_complete(spot)

        if self._current_complete_index < len(self.sequence):
            self._pump_dispatch_window()

    def _on_error_occurred(self, message: str) -> None:
        if not self.running:
            return
        if "Klipper" in message or "Moonraker" in message:
            self.logger.error(f"Spotting error: {message}")
            self.stop_requested = True
            if self.worker:
                self.worker.request_stop_safely()
            self._completion_event.set()
            self._finalize_spotting(False)

    def _on_worker_finished(self) -> None:
        self._completion_event.set()
        self.logger.info("Spotting worker finished")
        completed_all = bool(self.sequence) and self._current_complete_index >= len(self.sequence)
        self._finalize_spotting(completed_all and not self.stop_requested)

    def _on_safety_stopped(self) -> None:
        self.logger.warning("Spotting safety stop triggered")
        self._finalize_spotting(False)


class SpottingWorker(QThread):
    """Runs the spotting sequence off the GUI thread with safe stop behavior."""

    from PyQt6.QtCore import pyqtSignal

    progress_key = pyqtSignal(str)
    safety_stopped = pyqtSignal()

    def __init__(
        self,
        sequence: Sequence[Spot],
        speed_mm_s: float,
        klipper_service: KlipperService,
        klipper_publisher: Optional[KlipperPublisher],
        app_signals: AppSignals,
        valve_configs: List[Dict],
        valve_schema: List[Dict],
        completion_event: threading.Event,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sequence = sequence
        self.speed_mm_s = speed_mm_s
        self.klipper = klipper_service
        self.publisher = klipper_publisher
        self.signals = app_signals
        self.valve_configs = valve_configs or []
        self.valve_schema = {f.get("name"): f for f in (valve_schema or [])}
        self.completion_event = completion_event
        self._paused = False
        self._abort = False
        self._safe_stop = False

    def request_pause(self) -> None:
        self._paused = True

    def request_resume(self) -> None:
        self._paused = False

    def request_abort(self) -> None:
        self._abort = True

    def request_stop_safely(self) -> None:
        self._safe_stop = True
        self._paused = False

    def _valve_config(self, valve_id: int) -> Dict:
        return next(
            (vv for vv in self.valve_configs if int(vv.get("id", -1)) == int(valve_id)),
            {},
        )

    def _build_shoot_command(self, valve_id: int) -> str:
        return build_shoot_command(
            valve_id,
            self._valve_config(valve_id),
            self.valve_schema,
            ConfigManager.get_instance().get("klipper", {}),
        )

    def _build_shoot_command_with_position(
        self,
        valve_id: int,
        x: float,
        y: float,
        speed_mm_s: float,
    ) -> str:
        return build_shoot_command(
            valve_id,
            self._valve_config(valve_id),
            self.valve_schema,
            ConfigManager.get_instance().get("klipper", {}),
            x=x,
            y=y,
            speed_mm_s=speed_mm_s,
        )

    def _dispatch_spot(self, spot: Spot) -> None:
        shoot_command = self._shoot_command_for_spot(spot)

        if self.publisher:
            self.publisher.enqueue_script(shoot_command, completion_key=spot_key(spot))
        else:
            result = self.klipper.send_gcode(shoot_command)
            if (
                self.signals
                and isinstance(result, dict)
                and isinstance(result.get("id"), int)
            ):
                self.signals.gcode_script_queued.emit(int(result["id"]), spot_key(spot))

    def _dispatch_spots(self, spots: Sequence[Spot]) -> None:
        commands = [self._shoot_command_for_spot(spot) for spot in spots]
        if not commands:
            return

        script = "\n".join(commands)
        if self.publisher:
            self.publisher.enqueue_script(script)
        else:
            self.klipper.send_gcode(script)

    def _shoot_command_for_spot(self, spot: Spot) -> str:
        speed_mm_s = float(getattr(spot, "speed_mm_s", self.speed_mm_s))
        return self._build_shoot_command_with_position(
            spot.valve_id,
            spot.x,
            spot.y,
            speed_mm_s,
        )

    def run(self) -> None:
        if not self.klipper.is_connected:
            self.signals.error_occurred.emit("Spotting aborted: Klipper is not connected")
            self.safety_stopped.emit()
            return

        while not self.completion_event.is_set():
            if self._abort:
                self.safety_stopped.emit()
                return

            while self._paused:
                if self._abort:
                    self.safety_stopped.emit()
                    return
                if self._safe_stop or self.completion_event.is_set():
                    return
                self.msleep(50)

            if self._safe_stop:
                self.safety_stopped.emit()
                return

            self.msleep(10)
