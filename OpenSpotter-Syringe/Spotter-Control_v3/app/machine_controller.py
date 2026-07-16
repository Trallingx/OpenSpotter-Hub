"""Tk-thread coordinator for direct Moonraker machine control."""

from __future__ import annotations

import concurrent.futures
import hashlib
import math
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable, Optional, Sequence, Tuple

from .machine import (
    MachineState,
    MoonrakerCommandOutcomeUnknown,
    MoonrakerConfig,
    MoonrakerPrintQueuedError,
    MoonrakerRuntime,
)
from .manual_gcode import (
    CATEGORY_EMERGENCY,
    CATEGORY_FIRMWARE,
    CATEGORY_HOMING,
    CATEGORY_MOTION,
    ManualGcodeParseResult,
    parse_manual_gcode as inspect_manual_gcode,
)
from .runtime_job import (
    JobArtifact,
    capture_generation_snapshot,
    generate_job_artifact,
)
from .plugin_runtime import require_application_plugin
from .runtime_logging import get_logger, log_options


logger = get_logger("machine.controller")

REQUIRED_REMOTE_COMMANDS = frozenset(
    {
        "ADJUST_NEEDLE_SURFACE_OFFSET",
        "NEEDLE_TIP_OFFSETS_DISABLE",
        "NEEDLE_TIP_OFFSETS_ENABLE",
        "OPENSPOTTER_CONTRACT_V3",
        "OPENSPOTTER_HOME",
        "OPENSPOTTER_JOB_CLEANUP",
        "OPENSPOTTER_JOB_HOME",
        "OPENSPOTTER_JOB_REHOME_Z",
        "OPENSPOTTER_JOG",
        "OPENSPOTTER_SET_PROMPT",
        "RESET_NEEDLE_SURFACE_OFFSET",
    }
)


@dataclass(frozen=True)
class MachineView:
    revision: int
    connection_state: str
    connected: bool
    ready: bool
    klippy_state: str
    print_state: str
    filename: str
    progress: float
    file_position: int
    virtual_sd_active: bool
    position: Optional[Tuple[float, float, float]]
    live_position: Optional[Tuple[float, float, float]]
    live_position_fresh: bool
    gcode_position: Optional[Tuple[float, float, float]]
    homing_origin: Optional[Tuple[float, float, float]]
    absolute_coordinates: bool
    bed_mesh_profile: str
    homed_axes: str
    prompt: int
    display_message: str
    offsets_enabled: bool
    surface_z: float
    axis_minimum: Optional[Tuple[float, float, float]]
    axis_maximum: Optional[Tuple[float, float, float]]
    tcp_offset: Tuple[float, float, float]
    bltouch_state: str
    tcp_ready: bool
    tcp_coordinate_version: int
    gcode_commands: frozenset[str]
    last_error: Optional[str]


def _object_values(state: MachineState, name: str) -> Mapping:
    value = state.objects.get(name, {})
    return value if isinstance(value, Mapping) else {}


def _finite_float(value: Any, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return numeric if math.isfinite(numeric) else float(fallback)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return int(fallback)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coordinate_tuple(value: Any) -> Optional[Tuple[float, float, float]]:
    if isinstance(value, Mapping):
        source = (value.get("x"), value.get("y"), value.get("z"))
    elif isinstance(value, (tuple, list)) and len(value) >= 3:
        source = value[:3]
    else:
        return None
    values = tuple(_finite_float(item, float("nan")) for item in source)
    return values if all(math.isfinite(item) for item in values) else None


def machine_view_from_state(state: MachineState) -> MachineView:
    """Convert a Moonraker snapshot into the small UI/control contract."""
    toolhead = _object_values(state, "toolhead")
    gcode_move = _object_values(state, "gcode_move")
    motion = _object_values(state, "motion_report")
    print_stats = _object_values(state, "print_stats")
    pause_resume = _object_values(state, "pause_resume")
    virtual_sd = _object_values(state, "virtual_sdcard")
    bed_mesh = _object_values(state, "bed_mesh")
    display = _object_values(state, "display_status")
    runtime_macro = _object_values(state, "gcode_macro _OPENSPOTTER_RUNTIME")
    needle_macro = _object_values(state, "gcode_macro _NEEDLE_TIP_OFFSETS")
    save_variables = _object_values(state, "save_variables")
    capabilities = _object_values(state, "_openspotter_capabilities")
    live_motion = _object_values(state, "_openspotter_live_motion")
    saved = save_variables.get("variables", {})
    if not isinstance(saved, Mapping):
        saved = {}
    available_commands = capabilities.get("gcode_commands", ())
    if not isinstance(
        available_commands,
        (tuple, list, set, frozenset),
    ):
        available_commands = ()

    live_position = _coordinate_tuple(motion.get("live_position"))
    position_source = motion.get("live_position")
    if live_position is None:
        position_source = toolhead.get("position")
    position = _coordinate_tuple(position_source)
    live_position_fresh = bool(
        live_motion.get("fresh", False)
        and live_position is not None
    )

    print_state = str(print_stats.get("state", "standby") or "standby").lower()
    if bool(pause_resume.get("is_paused", False)):
        print_state = "paused"
    progress = _finite_float(virtual_sd.get("progress", 0.0))
    progress = max(0.0, min(progress, 1.0))
    klippy_state = state.klippy_state.strip().lower()

    return MachineView(
        revision=state.revision,
        connection_state=state.connection_state,
        connected=state.connected,
        ready=state.connected and klippy_state == "ready",
        klippy_state=klippy_state,
        print_state=print_state,
        filename=str(print_stats.get("filename", "") or ""),
        progress=progress,
        file_position=max(0, _safe_int(virtual_sd.get("file_position", 0))),
        virtual_sd_active=bool(virtual_sd.get("is_active", False)),
        position=position,
        live_position=live_position,
        live_position_fresh=live_position_fresh,
        gcode_position=_coordinate_tuple(gcode_move.get("gcode_position")),
        homing_origin=_coordinate_tuple(gcode_move.get("homing_origin")),
        absolute_coordinates=bool(
            gcode_move.get(
                "absolute_coordinates",
                True,
            )
        ),
        bed_mesh_profile=str(bed_mesh.get("profile_name", "") or "").strip(),
        homed_axes=str(toolhead.get("homed_axes", "") or "").lower(),
        prompt=max(0, _safe_int(runtime_macro.get("prompt", 0))),
        display_message=str(display.get("message", "") or ""),
        offsets_enabled=bool(_safe_int(needle_macro.get("enabled", 0))),
        surface_z=_finite_float(needle_macro.get("surface_z", 0.0)),
        axis_minimum=_coordinate_tuple(toolhead.get("axis_minimum")),
        axis_maximum=_coordinate_tuple(toolhead.get("axis_maximum")),
        tcp_offset=(
            _finite_float(saved.get("tcp_offset_x", 0.0)),
            _finite_float(saved.get("tcp_offset_y", 0.0)),
            _finite_float(saved.get("tcp_offset_z", 0.0)),
        ),
        bltouch_state=str(saved.get("bltouch_state", "unknown"))
        .strip()
        .strip("'\"")
        .lower(),
        tcp_ready=_safe_bool(saved.get("tcp_ready", False)),
        tcp_coordinate_version=_safe_int(
            saved.get("tcp_coordinate_version", 0)
        ),
        gcode_commands=frozenset(
            str(command).strip().upper()
            for command in available_commands
            if str(command).strip()
        ),
        last_error=state.last_error,
    )


def start_preflight_error(
    view: MachineView,
    *,
    parameters_locked: bool,
) -> Optional[str]:
    if not parameters_locked:
        return "Lock Global Machine Parameters before starting a machine job"
    if not view.connected:
        return "Moonraker is not connected"
    if not view.ready:
        return f"Klippy is not ready (state={view.klippy_state or 'unknown'})"
    contract_error = remote_control_contract_error(view)
    if contract_error:
        return f"Guarded firmware controls are not ready: {contract_error}"
    if view.virtual_sd_active:
        return "A virtual-SD job is already active"
    if view.print_state not in {"standby", "complete", "cancelled"}:
        return f"Machine is not idle (print state={view.print_state})"
    return None


def missing_remote_commands(view: MachineView) -> Tuple[str, ...]:
    """Return required guarded firmware entry points absent from Klipper."""
    return tuple(sorted(REQUIRED_REMOTE_COMMANDS - view.gcode_commands))


def remote_control_contract_error(view: MachineView) -> Optional[str]:
    missing = missing_remote_commands(view)
    if missing:
        return f"missing guarded command(s): {', '.join(missing)}"
    return None


_MOVE_COMMAND = re.compile(r"^\s*(G0|G1)(?=\s|$)", re.IGNORECASE)
_STANDARD_GCODE_PREFIX = re.compile(
    r"^\s*[GMT]\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_STANDARD_GCODE_PARAMETER = re.compile(
    r"([A-Za-z])\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))",
)
_MAX_MANUAL_EXECUTION_SECONDS = 60.0


def _strict_traditional_move_parameters(
    command: str,
    line_number: int,
) -> dict[str, float]:
    """Parse Klipper-native XYZ/F words without exponent or '=' ambiguity."""
    prefix = _MOVE_COMMAND.match(command)
    if prefix is None:
        return {}
    body = command[prefix.end() :]
    parameters: dict[str, float] = {}
    cursor = 0
    for match in _STANDARD_GCODE_PARAMETER.finditer(body):
        gap = body[cursor : match.start()]
        if gap.strip():
            raise ValueError(
                f"Line {line_number} contains malformed or ambiguous raw "
                f"G0/G1 parameter text near '{gap.strip()}'"
            )
        name = match.group(1).upper()
        if name not in {"X", "Y", "Z", "F"}:
            raise ValueError(
                f"Line {line_number} uses unsupported raw G0/G1 parameter "
                f"'{name}'. Only X, Y, Z, and F are allowed."
            )
        if name in parameters:
            raise ValueError(
                f"Line {line_number} repeats raw G0/G1 parameter '{name}'"
            )
        value = float(match.group(2))
        if not math.isfinite(value):
            raise ValueError(
                f"Line {line_number} raw G0/G1 parameter '{name}' "
                "must be finite"
            )
        parameters[name] = value
        cursor = match.end()
    tail = body[cursor:]
    if tail.strip():
        raise ValueError(
            f"Line {line_number} contains malformed or ambiguous raw "
            f"G0/G1 parameter text near '{tail.strip()}'"
        )
    if "F" in parameters and parameters["F"] <= 0:
        raise ValueError(
            f"Line {line_number} raw G0/G1 feed must be positive"
        )
    return parameters


def artifact_bounds_error(artifact: JobArtifact, view: MachineView) -> Optional[str]:
    """Validate rendered absolute XYZ targets against live Klipper limits."""
    minimum = view.axis_minimum
    maximum = view.axis_maximum
    if minimum is None or maximum is None:
        return (
            "Live toolhead axis limits are unavailable. Install/restart the "
            "supplied Klipper configuration before direct execution."
        )

    absolute = None
    offsets_enabled = bool(view.offsets_enabled)
    axis_index = {"X": 0, "Y": 1, "Z": 2}
    with Path(artifact.path).open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            command = raw_line.split(";", 1)[0].strip()
            upper = command.upper()
            if not upper:
                continue
            if re.match(r"^G90(?:\s|$)", upper):
                absolute = True
                continue
            if re.match(r"^G91(?:\s|$)", upper):
                absolute = False
                continue
            if upper.startswith("NEEDLE_TIP_OFFSETS_ENABLE"):
                offsets_enabled = True
                continue
            if upper.startswith("NEEDLE_TIP_OFFSETS_DISABLE"):
                offsets_enabled = False
                continue
            if not _MOVE_COMMAND.match(command):
                continue
            try:
                parameters = _strict_traditional_move_parameters(
                    command,
                    line_number,
                )
            except ValueError as exc:
                return str(exc)
            values = {
                axis: parameters[axis]
                for axis in ("X", "Y", "Z")
                if axis in parameters
            }
            if not values:
                continue
            if absolute is not True:
                return (
                    f"Line {line_number} contains XYZ motion before a known G90 "
                    "absolute-coordinate state, so bounds cannot be proven"
                )
            for axis, target in values.items():
                index = axis_index[axis]
                physical_target = target
                if offsets_enabled:
                    physical_target += view.tcp_offset[index]
                    if axis == "Z":
                        physical_target += view.surface_z
                if not (minimum[index] <= physical_target <= maximum[index]):
                    return (
                        f"Line {line_number} planned {axis}={target:.4f} mm "
                        f"(physical {physical_target:.4f} mm) outside live "
                        f"limits [{minimum[index]:.4f}, {maximum[index]:.4f}]"
                    )
    return None


def artifact_hardware_preflight_error(
    artifact: JobArtifact,
    view: MachineView,
) -> Optional[str]:
    uses_mesh = False
    enables_offsets = False
    with Path(artifact.path).open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            command = raw_line.split(";", 1)[0].strip().upper()
            if command == "MESH" or command.startswith("MESH "):
                uses_mesh = True
            elif command == "NEEDLE_TIP_OFFSETS_ENABLE" or command.startswith(
                "NEEDLE_TIP_OFFSETS_ENABLE "
            ):
                enables_offsets = True
            if uses_mesh and enables_offsets:
                break
    if uses_mesh and view.bltouch_state != "loaded":
        return (
            "The exact artifact uses MESH, but saved BLTouch state is "
            f"'{view.bltouch_state or 'unknown'}'. Load and verify the detachable "
            "probe before direct execution."
        )
    if enables_offsets and (
        not view.tcp_ready or view.tcp_coordinate_version != 2
    ):
        return (
            "The exact artifact enables needle TCP offsets, but saved TCP "
            f"calibration is not ready for coordinate version 2 "
            f"(tcp_ready={view.tcp_ready}, version={view.tcp_coordinate_version})."
        )
    return None


class MachineControlController:
    """Coordinate snapshots, artifact generation, Moonraker, and panel updates.

    Every method that touches Tk is called from the Tk thread.  Worker and
    network futures are observed with ``after`` polling instead of calling Tk
    from their completion threads.
    """

    POLL_MS = 50

    def __init__(
        self,
        root: Any,
        panel: Any,
        config_loader: Callable[[], MoonrakerConfig],
        *,
        runtime_factory: Callable[[MoonrakerConfig], MoonrakerRuntime] = MoonrakerRuntime,
        artifact_executor: Optional[concurrent.futures.Executor] = None,
        artifact_generator: Callable[..., JobArtifact] = generate_job_artifact,
        position_sink: Optional[
            Callable[[Optional[Tuple[float, float, float]], str], None]
        ] = None,
    ) -> None:
        self.root = root
        self.panel = panel
        self.config_loader = config_loader
        self.runtime_factory = runtime_factory
        self.artifact_generator = artifact_generator
        self.position_sink = position_sink
        self._executor = artifact_executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="OpenSpotterJob",
        )
        self._owns_executor = artifact_executor is None

        self.runtime: Optional[MoonrakerRuntime] = None
        self.bridge = None
        self.settings_window = None
        self.artifact: Optional[JobArtifact] = None
        self._operation_busy = False
        self._launch_pending = False
        self._launch_in_flight = False
        self._outcome_unknown = False
        self._closed = False
        self._operation_token = 0
        self._after_ids = set()
        self._last_view: Optional[MachineView] = None
        self._last_print_state = "standby"
        self._last_gcode_line = None
        self._reported_external_filename = None
        self._pending_job_summary = ""
        self._launch_baseline_revision = 0
        self._manual_parse_result: Optional[ManualGcodeParseResult] = None

        self.panel.bind_actions(
            start_job=self.start_current_job,
            pause_resume=self.pause_resume,
            cancel_job=self.cancel_job,
            emergency_stop=self.emergency_stop,
            home=self.home,
            jog=self.jog,
            adjust_z=self.adjust_live_z,
            reset_z=self.reset_live_z,
            connection_settings=self.show_connection_settings,
            reconnect=self.reconnect,
            parse_manual_gcode=self.parse_manual_gcode,
            send_manual_gcode=self.send_manual_gcode,
        )

    def set_settings_window(self, window: Any) -> None:
        self.settings_window = window

    def start(self) -> None:
        self.reconnect()

    @property
    def has_unresolved_operation(self) -> bool:
        return bool(
            self._operation_busy
            or self._launch_pending
            or self._launch_in_flight
            or self._outcome_unknown
        )

    def apply_config(self, config: MoonrakerConfig) -> None:
        """Apply newly saved settings unless monitoring an active job."""
        self.reconnect(config)

    def reconnect(self, config: Optional[MoonrakerConfig] = None) -> None:
        if self._closed:
            return
        current_view = self.current_view()
        active_print = (
            current_view.print_state in {"printing", "paused"}
            or current_view.virtual_sd_active
        )
        monitoring_reconnect = bool(
            active_print and self._outcome_unknown and self.runtime is not None
        )
        if active_print and not monitoring_reconnect:
            self.panel.set_operation(
                "Reconnect is blocked while a machine job is active",
                level="warning",
            )
            return
        if self.has_unresolved_operation and not self._outcome_unknown:
            self.panel.set_operation(
                "Reconnect is blocked while a machine operation is in flight",
                level="warning",
            )
            return

        try:
            selected_config = (
                self.runtime.config
                if monitoring_reconnect and self.runtime is not None
                else config or self.config_loader()
            )
            if not isinstance(selected_config, MoonrakerConfig):
                raise TypeError("Connection loader did not return MoonrakerConfig")
        except Exception as exc:
            self.panel.set_connection("disconnected")
            self._clear_position_sink()
            self._report_error("Moonraker connection settings", exc, popup=False)
            return

        self._clear_position_sink()
        self._operation_token += 1
        token = self._operation_token
        self._operation_busy = False
        self._launch_pending = False
        self._launch_in_flight = False
        self._outcome_unknown = False
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None
        self.panel.set_connection(
            "connecting",
            f"Connecting to {selected_config.host}:{selected_config.port}",
        )

        old_runtime = self.runtime
        if old_runtime is not None and not old_runtime.stop(timeout=0.0):
            self.panel.set_operation(
                "Stopping the existing Moonraker runtime before reconnecting...",
                level="info",
            )
            self._schedule(
                100,
                lambda: self._await_runtime_stop(
                    old_runtime,
                    selected_config,
                    token,
                    time.monotonic() + 4.0,
                ),
            )
            return
        self.runtime = None
        self._start_runtime(selected_config, token)

    def _await_runtime_stop(
        self,
        old_runtime: MoonrakerRuntime,
        config: MoonrakerConfig,
        token: int,
        deadline: float,
    ) -> None:
        if self._closed or token != self._operation_token:
            return
        if old_runtime.stop(timeout=0.0):
            if self.runtime is old_runtime:
                self.runtime = None
            self._start_runtime(config, token)
            return
        if time.monotonic() >= deadline:
            self.panel.set_connection("disconnected")
            self.panel.set_operation(
                "Reconnect aborted because the previous runtime did not stop; "
                "restart the application before creating another connection",
                level="error",
            )
            return
        self._schedule(
            100,
            lambda: self._await_runtime_stop(
                old_runtime,
                config,
                token,
                deadline,
            ),
        )

    def _start_runtime(self, selected_config: MoonrakerConfig, token: int) -> None:
        if self._closed or token != self._operation_token:
            return
        try:
            runtime = self.runtime_factory(selected_config)
            runtime.start()
            bridge = runtime.tk_bridge(
                self.root,
                self._on_runtime_events,
                interval_ms=self.POLL_MS,
                batch_limit=300,
            )
            bridge.start()
        except Exception as exc:
            self.runtime = None
            self.bridge = None
            self.panel.set_connection("disconnected")
            self._clear_position_sink()
            self._report_error("Moonraker connection", exc, popup=False)
            return

        self.runtime = runtime
        self.bridge = bridge
        log_options(
            logger,
            "moonraker.runtime_started",
            scheme=selected_config.scheme,
            host=selected_config.host,
            port=selected_config.port,
            route_prefix=selected_config.route_prefix,
        )
        self._refresh_state()

    def show_connection_settings(self) -> None:
        if self.settings_window is not None:
            self.settings_window.show()
        else:
            self.panel.set_operation(
                "Connection settings window is not available",
                level="error",
            )

    def current_view(self) -> MachineView:
        if self.runtime is None:
            return MachineView(
                revision=0,
                connection_state="stopped",
                connected=False,
                ready=False,
                klippy_state="unknown",
                print_state="standby",
                filename="",
                progress=0.0,
                file_position=0,
                virtual_sd_active=False,
                position=None,
                live_position=None,
                live_position_fresh=False,
                gcode_position=None,
                homing_origin=None,
                absolute_coordinates=True,
                bed_mesh_profile="",
                homed_axes="",
                prompt=0,
                display_message="",
                offsets_enabled=False,
                surface_z=0.0,
                axis_minimum=None,
                axis_maximum=None,
                tcp_offset=(0.0, 0.0, 0.0),
                bltouch_state="unknown",
                tcp_ready=False,
                tcp_coordinate_version=0,
                gcode_commands=frozenset(),
                last_error=None,
            )
        return machine_view_from_state(self.runtime.state_snapshot())

    def _on_runtime_events(self, events: Sequence[Any]) -> None:
        for event in events:
            if event.kind == "connected":
                contract_error = remote_control_contract_error(
                    self.current_view()
                )
                if contract_error:
                    self.panel.set_operation(
                        "Moonraker connected, but guarded firmware controls "
                        f"are unavailable: {contract_error}. Upload the current "
                        "remote_control.cfg and hardware.cfg, restart Klipper, "
                        "then reconnect.",
                        level="warning",
                    )
                else:
                    self.panel.set_operation(
                        "Moonraker connected; guarded machine controls are ready",
                        level="success",
                    )
            elif event.kind == "disconnected":
                payload = event.payload
                detail = getattr(payload, "last_error", None)
                self.panel.set_operation(
                    detail or "Moonraker connection lost; reconnecting",
                    level="error",
                )
            elif event.kind == "command_outcome_unknown":
                self._operation_busy = False
                self._launch_pending = False
                self._launch_in_flight = False
                self._outcome_unknown = True
                self.panel.set_operation(
                    "Command response timed out; printer-side outcome is unknown. "
                    "Inspect live state, then reconnect before issuing another command.",
                    level="warning",
                )
            elif event.kind == "subscription_unavailable":
                unavailable = ", ".join(str(name) for name in event.payload)
                self.panel.set_operation(
                    f"Klipper objects unavailable: {unavailable}",
                    level="warning",
                )
            elif event.kind == "gcode_capabilities_unavailable":
                self.panel.set_operation(
                    "Could not read Klipper G-code capabilities; guarded Home "
                    "and Jog controls remain disabled",
                    level="warning",
                )
        self._refresh_state()

    def _refresh_state(self) -> None:
        view = self.current_view()
        self._last_view = view
        artifact_filename = (
            str(self.artifact.remote_path).replace("\\", "/").lstrip("/")
            if self.artifact is not None
            else ""
        )
        observed_filename = str(view.filename).replace("\\", "/").lstrip("/")
        launch_state_is_fresh = (
            self._launch_pending
            and view.revision > self._launch_baseline_revision
            and bool(artifact_filename)
            and observed_filename == artifact_filename
        )
        if launch_state_is_fresh and (
            view.print_state in {"printing", "paused"}
            or view.virtual_sd_active
        ):
            self._launch_pending = False

        self.panel.set_connection(
            view.connection_state,
            view.last_error or "",
        )
        self.panel.set_job(
            state=view.print_state,
            filename=view.filename,
            progress=view.progress,
            prompt=view.prompt,
            display_message=view.display_message,
        )
        self.panel.set_position(view.position, view.homed_axes)
        canvas_position = (
            view.live_position
            if (
                view.connected
                and view.ready
                and view.live_position_fresh
                and set("xy") <= set(view.homed_axes)
            )
            else None
        )
        self._update_position_sink(canvas_position, view.homed_axes)
        self.panel.set_live_z(view.surface_z)
        self.panel.set_control_state(
            connected=view.connected,
            ready=view.ready,
            print_state=view.print_state,
            virtual_sd_active=view.virtual_sd_active,
            homed_axes=view.homed_axes,
            offsets_enabled=view.offsets_enabled,
            bed_mesh_active=bool(view.bed_mesh_profile),
            operation_busy=(
                self._operation_busy
                or self._launch_pending
                or self._launch_in_flight
                or self._outcome_unknown
            ),
            runtime_started=bool(self.runtime and self.runtime.started),
            gcode_commands=view.gcode_commands,
            remote_controls_ready=remote_control_contract_error(view) is None,
        )
        if self.runtime is not None and hasattr(self.panel, "show_console"):
            self.panel.show_console(self.runtime.console_snapshot())
        self._refresh_gcode_context(view)

        if (
            self._last_print_state in {"printing", "paused"}
            and view.print_state not in {"printing", "paused"}
            and not self._operation_busy
        ):
            if view.print_state == "complete":
                self.panel.set_operation(
                    "Virtual-SD job completed",
                    level="success",
                )
            elif view.print_state == "cancelled":
                self.panel.set_operation(
                    "Virtual-SD job cancelled",
                    level="warning",
                )
            elif view.print_state == "error":
                self.panel.set_operation(
                    "Virtual-SD job ended with an error",
                    level="error",
                )
        self._last_print_state = view.print_state

    def _refresh_gcode_context(self, view: MachineView) -> None:
        artifact = self.artifact
        if artifact is None:
            self.panel.show_gcode_context(None, 0, ())
            return
        expected_filename = str(artifact.remote_path).replace("\\", "/").lstrip("/")
        actual_filename = str(view.filename).replace("\\", "/").lstrip("/")
        if actual_filename and actual_filename != expected_filename:
            self._last_gcode_line = None
            self.panel.show_gcode_context(None, 0, ())
            if (
                view.print_state in {"printing", "paused"}
                and actual_filename != self._reported_external_filename
            ):
                self._reported_external_filename = actual_filename
                self.panel.set_operation(
                    "An external virtual-SD job is active; the local artifact "
                    "viewer is hidden to avoid showing the wrong file",
                    level="warning",
                )
            return
        try:
            current_line = artifact.line_index_for_file_position(
                view.file_position,
            )
        except (OSError, ValueError) as exc:
            self.panel.set_operation(
                f"Live G-code view failed: {exc}",
                level="error",
            )
            return
        if current_line == self._last_gcode_line:
            return
        try:
            _, rows = artifact.context_for_file_position(
                view.file_position,
                before=5,
                after=10,
            )
        except (OSError, ValueError) as exc:
            self.panel.set_operation(
                f"Live G-code view failed: {exc}",
                level="error",
            )
            return
        self._last_gcode_line = current_line
        self.panel.show_gcode_context(artifact, current_line, rows)

    def start_current_job(self) -> None:
        if self.has_unresolved_operation:
            return
        view = self.current_view()
        error = start_preflight_error(
            view,
            parameters_locked=bool(self.root.global_locked.get()),
        )
        if error:
            self._report_error("Start machine job", ValueError(error))
            return

        try:
            snapshot = capture_generation_snapshot(self.root)
        except Exception as exc:
            self._report_error("Start machine job", exc)
            return

        workflow_hash = hashlib.sha256(
            snapshot.workflow_json.encode("utf-8")
        ).hexdigest()[:12]
        recipes = getattr(snapshot, "recipes", None)
        if recipes is None:
            # Compatibility for callers still constructing pre-plugin
            # snapshots with a pluralized recipe attribute.
            recipes = getattr(snapshot, "{}s".format(snapshot.kind), ())
        item_count = len(recipes)
        plugin = require_application_plugin(snapshot.kind)
        item_label = plugin.manifest.display_name.lower()
        if item_count != 1:
            item_label += "s"
        self._pending_job_summary = (
            f"{snapshot.kind.upper()} / {item_count} {item_label} / "
            f"workflow {workflow_hash}"
        )

        token = self._begin_operation(
            f"Generating detached {snapshot.kind} G-code snapshot..."
        )
        future = self._executor.submit(self.artifact_generator, snapshot)
        self._watch_future(
            future,
            token=token,
            on_success=lambda artifact: self._upload_and_start(artifact, token),
            title="Generate machine job",
        )

    def _upload_and_start(self, artifact: JobArtifact, token: int) -> None:
        if token != self._operation_token or self._closed:
            return
        self.artifact = artifact
        self._last_gcode_line = None
        view = self.current_view()
        error = start_preflight_error(
            view,
            parameters_locked=bool(self.root.global_locked.get()),
        )
        if error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(f"Preflight changed during generation: {error}"),
            )
            return
        if self.runtime is None:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError("Moonraker runtime stopped during generation"),
            )
            return

        bounds_error = artifact_bounds_error(artifact, view)
        if bounds_error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(bounds_error),
            )
            return
        hardware_error = artifact_hardware_preflight_error(artifact, view)
        if hardware_error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(hardware_error),
            )
            return

        confirmed = messagebox.askyesno(
            "Start exact machine job",
            (
                f"{self._pending_job_summary}\n"
                f"Artifact SHA-256: {artifact.sha256}\n"
                f"Artifact size: {artifact.size:,} bytes / "
                f"{artifact.line_count:,} lines\n"
                f"Moonraker path: {artifact.remote_path}\n\n"
                "This is the detached snapshot captured before any later UI "
                "edits. The effective workflow/profile is executable machine "
                "code. Starting can home, probe, move, dispense, and pause for "
                "operator actions.\n\nStart this exact artifact now?"
            ),
            parent=self.root,
        )
        if not confirmed:
            self._finish_operation()
            self.panel.set_operation(
                "Machine start cancelled; the generated artifact was not uploaded",
                level="warning",
            )
            return

        self.panel.set_operation(
            f"Uploading exact {artifact.size:,}-byte artifact without queueing...",
            level="info",
        )
        future = self.runtime.upload_gcode(
            artifact.path,
            artifact.remote_path,
            checksum=artifact.sha256,
            start=False,
        )
        self._watch_future(
            future,
            token=token,
            on_success=lambda result: self._uploaded_artifact(result, token),
            title="Upload machine job",
        )

    def _uploaded_artifact(self, result: Any, token: int) -> None:
        if token != self._operation_token or self._closed:
            return
        view = self.current_view()
        error = start_preflight_error(
            view,
            parameters_locked=bool(self.root.global_locked.get()),
        )
        if error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(f"Fresh preflight after upload failed: {error}"),
            )
            return
        if self.runtime is None or self.artifact is None:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError("Moonraker runtime stopped after upload"),
            )
            return
        bounds_error = artifact_bounds_error(self.artifact, view)
        if bounds_error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(f"Fresh bounds preflight after upload failed: {bounds_error}"),
            )
            return
        hardware_error = artifact_hardware_preflight_error(
            self.artifact,
            view,
        )
        if hardware_error:
            self._finish_operation()
            self._report_error(
                "Start machine job",
                ValueError(
                    f"Fresh hardware preflight after upload failed: {hardware_error}"
                ),
            )
            return

        upload_ms = float(getattr(result, "elapsed_ms", 0.0))
        self._launch_in_flight = True
        self._launch_baseline_revision = view.revision
        self.panel.set_operation(
            f"Upload verified in {upload_ms:.0f} ms; sending immediate virtual-SD start...",
            level="info",
        )
        future = self.runtime.start_print(self.artifact.remote_path)
        self._watch_future(
            future,
            token=token,
            on_success=lambda command_result: self._job_start_accepted(
                command_result,
                token,
                upload_ms,
            ),
            title="Start machine job",
        )

    def _job_start_accepted(
        self,
        result: Any,
        token: int,
        upload_ms: float,
    ) -> None:
        if token != self._operation_token or self._closed:
            return
        self._operation_busy = False
        self._launch_in_flight = False
        self._launch_pending = True
        timing = getattr(result, "timing", None)
        start_ms = float(getattr(timing, "total_ms", 0.0))
        self.panel.set_operation(
            "Moonraker accepted the exact artifact start "
            f"(upload {upload_ms:.0f} ms + start RPC {start_ms:.0f} ms)",
            level="success",
        )
        self._refresh_state()
        self._schedule(
            8000,
            lambda: self._check_launch_confirmation(token),
        )

    def _check_launch_confirmation(self, token: int) -> None:
        if (
            self._closed
            or token != self._operation_token
            or not self._launch_pending
        ):
            return
        view = self.current_view()
        artifact_filename = (
            str(self.artifact.remote_path).replace("\\", "/").lstrip("/")
            if self.artifact is not None
            else ""
        )
        observed_filename = str(view.filename).replace("\\", "/").lstrip("/")
        if (
            view.revision > self._launch_baseline_revision
            and artifact_filename
            and observed_filename == artifact_filename
            and (
                view.print_state in {"printing", "paused"}
                or view.virtual_sd_active
            )
        ):
            self._launch_pending = False
            self._refresh_state()
            return
        self._launch_pending = False
        self._outcome_unknown = True
        self.panel.set_operation(
            "Moonraker accepted Start, but no print-state transition was observed. "
            "Inspect the machine and reconnect before issuing another command.",
            level="warning",
        )
        self._refresh_state()

    def pause_resume(self) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        view = self.current_view()
        if view.print_state == "printing":
            self._submit_control(
                self.runtime.pause(),
                "Pausing virtual-SD job...",
                "Pause machine job",
            )
        elif view.print_state == "paused":
            self._submit_control(
                self.runtime.resume(),
                "Resuming virtual-SD job...",
                "Resume machine job",
            )

    def cancel_job(self) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        view = self.current_view()
        if (
            view.print_state not in {"printing", "paused"}
            and not view.virtual_sd_active
        ):
            return
        if not messagebox.askyesno(
            "Cancel machine job",
            (
                "Cancel the active virtual-SD job?\n\n"
                "Klipper will run the OpenSpotter non-motion cleanup macro."
            ),
            parent=self.root,
        ):
            return
        self._submit_control(
            self.runtime.cancel(),
            "Cancelling virtual-SD job...",
            "Cancel machine job",
        )

    def emergency_stop(self) -> None:
        """Issue the independent HTTP E-stop immediately, without a dialog."""
        if self.runtime is None:
            return
        # An E-stop may race an operation whose outcome was already unknown.
        # Keep (and deliberately set) the interlock until the operator performs
        # an explicit reconnect after inspecting the stopped printer.
        self._outcome_unknown = True
        self._launch_in_flight = False
        self._launch_pending = False
        token = self._begin_operation("EMERGENCY STOP requested...", level="error")
        future = self.runtime.emergency()
        self._watch_future(
            future,
            token=token,
            on_success=lambda result: self._emergency_accepted(result, token),
            title="Emergency stop",
        )

    def _emergency_accepted(self, result: Any, token: int) -> None:
        if token != self._operation_token:
            return
        self._finish_operation()
        elapsed = float(getattr(result, "elapsed_ms", 0.0))
        self.panel.set_operation(
            "Emergency stop accepted by Moonraker "
            f"in {elapsed:.0f} ms. Controls remain interlocked; inspect the "
            "printer and reconnect before recovery.",
            level="error",
        )

    def home(self) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        view = self.current_view()
        if (
            not view.ready
            or view.virtual_sd_active
            or view.print_state in {"printing", "paused"}
        ):
            self._report_error(
                "Safe home XYZ",
                ValueError(
                    "Machine must be ready and no virtual-SD job may be active"
                ),
            )
            return
        contract_error = remote_control_contract_error(view)
        if contract_error:
            self._report_error(
                "Safe home XYZ",
                ValueError(
                    f"Guarded firmware controls are not ready: {contract_error}. "
                    "Upload the current remote_control.cfg and hardware.cfg, "
                    "keep the include in printer.cfg, restart Klipper, and reconnect."
                ),
            )
            return
        if not messagebox.askyesno(
            "Safe home XYZ",
            (
                "Run the reviewed OpenSpotter full homing sequence "
                "(settle, home/release Z, settle, home/release Y, move to "
                "Z clearance, then settle and home/release X)?"
            ),
            parent=self.root,
        ):
            return
        console_since = self._console_marker()
        future = self.runtime.send_gcode(
            "OPENSPOTTER_HOME",
            priority=self.runtime.PRIORITY_CONTROL,
            timeout=self.runtime.config.gcode_timeout,
        )
        self._submit_control(
            future,
            "Running safe full-home sequence...",
            "Home machine",
            console_since=console_since,
            interlock_on_error=True,
        )

    def jog(self, axis: str, distance: float, feed: float) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        selected_axis = str(axis).strip().upper()
        numeric_distance = _finite_float(distance, float("nan"))
        numeric_feed = _finite_float(feed, float("nan"))
        if selected_axis not in {"X", "Y", "Z"}:
            self._report_error("Jog machine", ValueError("Jog axis must be X, Y, or Z"))
            return
        limit = 5.0 if selected_axis == "Z" else 25.0
        feed_limit = 1500.0 if selected_axis == "Z" else 6000.0
        if not math.isfinite(numeric_distance) or not (0.0 < abs(numeric_distance) <= limit):
            self._report_error(
                "Jog machine",
                ValueError(f"{selected_axis} jog must be non-zero and at most {limit:g} mm"),
            )
            return
        minimum_feed = 30.0
        if not math.isfinite(numeric_feed) or not (
            minimum_feed <= numeric_feed <= feed_limit
        ):
            self._report_error(
                "Jog machine",
                ValueError(
                    f"{selected_axis} jog feed must be between "
                    f"{minimum_feed:g} and {feed_limit:g} mm/min"
                ),
            )
            return
        view = self.current_view()
        if (
            not view.ready
            or view.virtual_sd_active
            or view.print_state in {"printing", "paused"}
        ):
            self._report_error("Jog machine", ValueError("Machine must be ready and idle"))
            return
        if not set("xyz") <= set(view.homed_axes):
            self._report_error(
                "Jog machine",
                ValueError("All XYZ axes must be homed before manual jogging"),
            )
            return
        contract_error = remote_control_contract_error(view)
        if contract_error:
            self._report_error(
                "Jog machine",
                ValueError(
                    f"Guarded firmware controls are not ready: {contract_error}. "
                    "Upload the current remote_control.cfg and hardware.cfg, "
                    "restart Klipper, and reconnect."
                ),
            )
            return
        if view.offsets_enabled:
            self._report_error(
                "Jog machine",
                ValueError(
                    "Disable needle tip offsets before manual XYZ jogging"
                ),
            )
            return
        if view.bed_mesh_profile:
            self._report_error(
                "Jog machine",
                ValueError(
                    "Clear the active bed mesh profile "
                    f"'{view.bed_mesh_profile}' before manual XYZ jogging"
                ),
            )
            return
        if (
            view.position is None
            or view.axis_minimum is None
            or view.axis_maximum is None
        ):
            self._report_error(
                "Jog machine",
                ValueError("Live position and axis limits are required for jogging"),
            )
            return
        axis_index = {"X": 0, "Y": 1, "Z": 2}[selected_axis]
        target = view.position[axis_index] + numeric_distance
        minimum = view.axis_minimum[axis_index]
        maximum = view.axis_maximum[axis_index]
        if not (minimum <= target <= maximum):
            self._report_error(
                "Jog machine",
                ValueError(
                    f"{selected_axis} jog target {target:.4f} mm is outside "
                    f"live limits [{minimum:.4f}, {maximum:.4f}]"
                ),
            )
            return
        script = (
            f"OPENSPOTTER_JOG AXIS={selected_axis} "
            f"DISTANCE={numeric_distance:.5f} F={numeric_feed:.3f}"
        )
        motion_seconds = 60.0 * abs(numeric_distance) / numeric_feed
        jog_timeout = min(
            self.runtime.config.gcode_timeout,
            max(
                self.runtime.config.control_timeout,
                motion_seconds + 10.0,
            ),
        )
        console_since = self._console_marker()
        self._submit_control(
            self.runtime.send_gcode(
                script,
                priority=self.runtime.PRIORITY_CONTROL,
                timeout=jog_timeout,
            ),
            f"Jogging {selected_axis} {numeric_distance:+g} mm...",
            "Jog machine",
            console_since=console_since,
            interlock_on_error=True,
        )

    def adjust_live_z(self, adjustment: float) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        numeric = _finite_float(adjustment, float("nan"))
        if not math.isfinite(numeric) or not (0.0 < abs(numeric) <= 0.25):
            self._report_error(
                "Adjust live Z",
                ValueError("Live Z adjustment must be non-zero and at most 0.25 mm"),
            )
            return
        error = self._live_z_preflight()
        if error:
            self._report_error("Adjust live Z", ValueError(error))
            return
        script = (
            f"ADJUST_NEEDLE_SURFACE_OFFSET Z_ADJUST={numeric:.4f} "
            "MOVE=1 SAVE=0 F=300"
        )
        console_since = self._console_marker()
        self._submit_control(
            self.runtime.send_gcode(
                script,
                priority=self.runtime.PRIORITY_CONTROL,
                timeout=self.runtime.config.control_timeout,
            ),
            f"Applying live needle Z {numeric:+.4f} mm...",
            "Adjust live Z",
            console_since=console_since,
            interlock_on_error=True,
        )

    def reset_live_z(self) -> None:
        if self.runtime is None or self.has_unresolved_operation:
            return
        error = self._live_z_preflight()
        if error:
            self._report_error("Reset live Z", ValueError(error))
            return
        console_since = self._console_marker()
        self._submit_control(
            self.runtime.send_gcode(
                "RESET_NEEDLE_SURFACE_OFFSET MOVE=1 SAVE=0 F=300",
                priority=self.runtime.PRIORITY_CONTROL,
                timeout=self.runtime.config.control_timeout,
            ),
            "Resetting the live needle Z trim...",
            "Reset live Z",
            console_since=console_since,
            interlock_on_error=True,
        )

    def parse_manual_gcode(
        self,
        script: str,
    ) -> Optional[ManualGcodeParseResult]:
        """Inspect operator text and publish a non-executing parse preview."""
        try:
            result = inspect_manual_gcode(script)
        except Exception as exc:
            self._manual_parse_result = None
            self.panel.set_manual_parse(
                f"Parse failed: {str(exc) or exc.__class__.__name__}",
                (),
                valid=False,
            )
            return None

        self._manual_parse_result = result
        blocked_reasons = tuple(
            str(reason)
            for reason in getattr(result, "blocked_reasons", ())
            if str(reason)
        )
        self.panel.set_manual_parse(
            result.summary,
            tuple(result.warnings) + blocked_reasons,
            valid=bool(result.commands) and not blocked_reasons,
        )
        return result

    def send_manual_gcode(self, script: str) -> None:
        """Parse, confirm, and monitor one manual script while idle."""
        if self.runtime is None or self.has_unresolved_operation:
            return
        result = self.parse_manual_gcode(script)
        if result is None:
            return
        if not result.commands:
            self.panel.set_manual_parse(
                "No executable commands to send.",
                (),
                valid=False,
            )
            return

        blocked_reasons = tuple(
            str(reason)
            for reason in getattr(result, "blocked_reasons", ())
            if str(reason)
        )
        if blocked_reasons:
            self._report_error(
                "Send manual G-code",
                ValueError(
                    "The parser blocked this script:\n- "
                    + "\n- ".join(blocked_reasons)
                ),
            )
            return

        categories = {command.category for command in result.commands}
        if CATEGORY_EMERGENCY in categories:
            if len(result.commands) != 1 or categories != {CATEGORY_EMERGENCY}:
                self._report_error(
                    "Send manual G-code",
                    ValueError(
                        "Emergency stop must be the only executable command. "
                        "It cannot be mixed with another script."
                    ),
                )
                return
            # Console M112 is queued behind other G-code.  Use Moonraker's
            # independent HTTP endpoint, the same path as the E-stop button.
            self.emergency_stop()
            return

        view = self.current_view()
        if not view.connected or not view.ready:
            self._report_error(
                "Send manual G-code",
                ValueError("Machine must be connected and Klippy must be ready"),
            )
            return
        if view.virtual_sd_active or view.print_state in {"printing", "paused"}:
            self._report_error(
                "Send manual G-code",
                ValueError(
                    "Manual G-code is blocked while a virtual-SD job is active"
                ),
            )
            return

        preflight_error, estimated_seconds = self._manual_gcode_preflight(
            result,
            view,
        )
        if preflight_error:
            self._report_error(
                "Send manual G-code",
                ValueError(preflight_error),
            )
            return

        payload = result.normalized_script
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if result.requires_confirmation:
            warning_lines = list(result.warnings)
            high_risk = bool(
                categories
                & {
                    CATEGORY_FIRMWARE,
                    CATEGORY_HOMING,
                    CATEGORY_MOTION,
                }
            )
            heading = (
                "This script can cause immediate physical machine action."
                if high_risk
                else "This script changes printer state."
            )
            confirmed = messagebox.askyesno(
                "Send exact manual G-code",
                (
                    f"{heading}\n\n"
                    f"{result.summary}\n"
                    f"SHA-256: {digest}\n"
                    f"UTF-8 size: {len(payload.encode('utf-8')):,} bytes\n\n"
                    + "\n".join(warning_lines)
                    + "\n\nSend this exact parsed script now?"
                ),
                parent=self.root,
            )
            if not confirmed:
                self.panel.set_operation(
                    "Manual G-code send cancelled",
                    level="warning",
                )
                return

        nonce = secrets.token_hex(12).upper()
        begin_token = f"OPENSPOTTER_MANUAL_BEGIN_{nonce}"
        end_token = f"OPENSPOTTER_MANUAL_END_{nonce}"
        payload_body = payload.rstrip("\n")
        wire_payload = (
            f'RESPOND PREFIX=openspotter: MSG="{begin_token}"\n'
            f"{payload_body}\n"
            "M400\n"
            f'RESPOND PREFIX=openspotter: MSG="{end_token}"'
        )
        console_since = self._console_marker()
        log_options(
            logger,
            "manual_gcode.confirmed",
            sha256=digest,
            command_count=len(result.commands),
            byte_count=len(payload.encode("utf-8")),
            categories=sorted(categories),
        )
        token = self._begin_operation(
            f"Sending {len(result.commands)} parsed manual command(s)..."
        )
        manual_timeout = max(
            self.runtime.config.gcode_timeout,
            estimated_seconds + 15.0,
        )
        future = self.runtime.send_gcode(
            wire_payload,
            priority=self.runtime.PRIORITY_CONTROL,
            timeout=manual_timeout,
        )
        self._watch_future(
            future,
            token=token,
            on_success=lambda rpc_result: self._manual_rpc_accepted(
                token=token,
                rpc_result=rpc_result,
                console_since=console_since,
                begin_token=begin_token,
                end_token=end_token,
                command_count=len(result.commands),
                digest=digest,
            ),
            title="Send manual G-code",
            interlock_on_error=True,
        )

    def _manual_gcode_preflight(
        self,
        result: ManualGcodeParseResult,
        view: MachineView,
    ) -> Tuple[Optional[str], float]:
        commands = tuple(result.commands)
        names = {command.name for command in commands}
        guarded_motion_names = names & {
            "OPENSPOTTER_HOME",
            "OPENSPOTTER_JOG",
        }
        if guarded_motion_names and len(commands) != 1:
            return (
                "Reviewed OPENSPOTTER_HOME or OPENSPOTTER_JOG must be the "
                "only executable command in a manual send.",
                0.0,
            )
        physical = any(
            command.category in {CATEGORY_MOTION, CATEGORY_HOMING}
            for command in commands
        )
        manual_home_only = names <= {
            "OPENSPOTTER_HOME",
            "G90",
            "G91",
            "M400",
        }
        if physical and not manual_home_only:
            if not set("xyz") <= set(view.homed_axes):
                return (
                    "All XYZ axes must be homed before sending manual motion. "
                    "Use SAFE HOME XYZ first.",
                    0.0,
                )
            if view.offsets_enabled:
                return (
                    "Disable needle tip offsets before sending manual motion.",
                    0.0,
                )
            if view.bed_mesh_profile:
                return (
                    "Clear the active bed mesh profile "
                    f"'{view.bed_mesh_profile}' before sending manual motion.",
                    0.0,
                )

        explicit_coordinate_mode: Optional[bool] = None
        physical_position = (
            list(view.position)
            if view.position is not None
            else None
        )
        logical_position = (
            list(view.gcode_position)
            if view.gcode_position is not None
            else None
        )
        estimated_seconds = 0.0
        for command in commands:
            if command.name == "G90":
                explicit_coordinate_mode = True
                continue
            if command.name == "G91":
                explicit_coordinate_mode = False
                continue
            if command.name == "G4":
                try:
                    dwell = self._manual_standard_parameters(command)
                except ValueError as exc:
                    return str(exc), 0.0
                if set(dwell) - {"P", "S"}:
                    return (
                        f"Line {command.line_number}: manual G4 supports only "
                        "P milliseconds or S seconds.",
                        0.0,
                    )
                dwell_seconds = (
                    float(dwell.get("S", 0.0))
                    + float(dwell.get("P", 0.0)) / 1000.0
                )
                if not math.isfinite(dwell_seconds) or not (
                    0.0 <= dwell_seconds <= 5.0
                ):
                    return (
                        f"Line {command.line_number}: manual G4 dwell must be "
                        "between 0 and 5 seconds.",
                        0.0,
                    )
                estimated_seconds += dwell_seconds
                if estimated_seconds > _MAX_MANUAL_EXECUTION_SECONDS:
                    return (
                        "The parsed manual motion/dwell sequence is estimated "
                        f"to take more than "
                        f"{_MAX_MANUAL_EXECUTION_SECONDS:.0f} seconds. Split it "
                        "into smaller tests.",
                        0.0,
                    )
                continue
            if command.name not in {"G0", "G1"}:
                continue
            if explicit_coordinate_mode is None:
                return (
                    f"Line {command.line_number}: raw {command.name} motion "
                    "requires an explicit G90 or G91 earlier in the same script.",
                    0.0,
                )
            if (
                physical_position is None
                or logical_position is None
                or view.axis_minimum is None
                or view.axis_maximum is None
            ):
                return (
                    "Live physical/logical position and axis limits are "
                    "required before sending raw manual motion.",
                    0.0,
                )
            try:
                parameters = self._manual_standard_parameters(command)
            except ValueError as exc:
                return str(exc), 0.0
            unsupported = set(parameters) - {"X", "Y", "Z", "F"}
            if unsupported:
                return (
                    f"Line {command.line_number}: raw manual motion supports "
                    "only X, Y, Z, and F parameters; blocked "
                    f"{', '.join(sorted(unsupported))}.",
                    0.0,
                )
            axis_values = {
                axis: parameters[axis]
                for axis in ("X", "Y", "Z")
                if axis in parameters
            }
            if not axis_values:
                return (
                    f"Line {command.line_number}: raw {command.name} must "
                    "contain at least one X, Y, or Z target.",
                    0.0,
                )
            if "F" not in parameters:
                return (
                    f"Line {command.line_number}: raw {command.name} requires "
                    "an explicit F feed rate.",
                    0.0,
                )
            feed = float(parameters["F"])
            if not math.isfinite(feed) or not (30.0 <= feed <= 6000.0):
                return (
                    f"Line {command.line_number}: manual motion feed must be "
                    "between 30 and 6000 mm/min.",
                    0.0,
                )

            previous = tuple(physical_position)
            for axis, value in axis_values.items():
                if not math.isfinite(value):
                    return (
                        f"Line {command.line_number}: {axis} target must be finite.",
                        0.0,
                    )
                index = {"X": 0, "Y": 1, "Z": 2}[axis]
                if explicit_coordinate_mode:
                    frame_offset = (
                        physical_position[index] - logical_position[index]
                    )
                    physical_position[index] = value + frame_offset
                    logical_position[index] = value
                else:
                    physical_position[index] += value
                    logical_position[index] += value
                minimum = view.axis_minimum[index]
                maximum = view.axis_maximum[index]
                if not minimum <= physical_position[index] <= maximum:
                    return (
                        f"Line {command.line_number}: planned physical {axis} "
                        f"target {physical_position[index]:.4f} mm is outside "
                        f"live limits [{minimum:.4f}, {maximum:.4f}].",
                        0.0,
                    )
            distance = math.sqrt(
                sum(
                    (physical_position[index] - previous[index]) ** 2
                    for index in range(3)
                )
            )
            estimated_seconds += 60.0 * distance / feed
            if estimated_seconds > _MAX_MANUAL_EXECUTION_SECONDS:
                return (
                    "The parsed manual motion/dwell sequence is estimated to "
                    f"take more than {_MAX_MANUAL_EXECUTION_SECONDS:.0f} "
                    "seconds. Split it into smaller tests or increase feed.",
                    0.0,
                )

        guarded_names = names & REQUIRED_REMOTE_COMMANDS
        missing = tuple(sorted(guarded_names - view.gcode_commands))
        if missing:
            return (
                "The loaded Klipper configuration does not advertise required "
                f"guarded command(s): {', '.join(missing)}",
                0.0,
            )
        if names & {"OPENSPOTTER_HOME", "OPENSPOTTER_JOG"}:
            contract_error = remote_control_contract_error(view)
            if contract_error:
                return (
                    "Guarded firmware controls are not ready: "
                    f"{contract_error}",
                    0.0,
                )
        return None, estimated_seconds

    @staticmethod
    def _manual_standard_parameters(command: Any) -> dict[str, float]:
        prefix = _STANDARD_GCODE_PREFIX.match(str(command.text))
        if prefix is None:
            raise ValueError(
                f"Line {command.line_number}: could not parse "
                f"{command.name} parameters."
            )
        body = str(command.text)[prefix.end() :]
        parameters: dict[str, float] = {}
        cursor = 0
        for match in _STANDARD_GCODE_PARAMETER.finditer(body):
            if body[cursor : match.start()].strip():
                raise ValueError(
                    f"Line {command.line_number}: malformed parameter text "
                    f"near '{body[cursor:match.start()].strip()}'."
                )
            name = match.group(1).upper()
            if name in parameters:
                raise ValueError(
                    f"Line {command.line_number}: duplicate {name} parameter."
                )
            parameters[name] = float(match.group(2))
            cursor = match.end()
        if body[cursor:].strip():
            raise ValueError(
                f"Line {command.line_number}: malformed parameter text "
                f"near '{body[cursor:].strip()}'."
            )
        return parameters

    def _manual_rpc_accepted(
        self,
        *,
        token: int,
        rpc_result: Any,
        console_since: int,
        begin_token: str,
        end_token: str,
        command_count: int,
        digest: str,
    ) -> None:
        """Wait for unique Klipper sentinels before declaring manual success."""
        deadline = time.monotonic() + 5.0

        def inspect_console() -> None:
            if self._closed or token != self._operation_token:
                return
            entries = self._console_entries_since(console_since)
            begin_index = next(
                (
                    index
                    for index, entry in enumerate(entries)
                    if begin_token in str(getattr(entry, "text", ""))
                ),
                None,
            )
            end_index = next(
                (
                    index
                    for index, entry in enumerate(entries)
                    if end_token in str(getattr(entry, "text", ""))
                ),
                None,
            )
            if begin_index is not None:
                checked_end = (
                    len(entries)
                    if end_index is None
                    else max(begin_index + 1, end_index)
                )
                error_entry = next(
                    (
                        entry
                        for entry in entries[begin_index + 1 : checked_end]
                        if str(getattr(entry, "level", "")) == "error"
                    ),
                    None,
                )
                if error_entry is not None:
                    self._interlock_manual_execution(
                        "Klipper reported an error after manual execution "
                        "started, so partial execution cannot be excluded: "
                        f"{getattr(error_entry, 'text', '')}"
                    )
                    return
            if (
                begin_index is not None
                and end_index is not None
                and begin_index < end_index
            ):
                self._finish_operation()
                timing = getattr(rpc_result, "timing", None)
                total_ms = float(getattr(timing, "total_ms", 0.0))
                timing_text = f", RPC {total_ms:.0f} ms" if total_ms > 0 else ""
                self.panel.set_operation(
                    f"Manual G-code completed ({command_count} command(s), "
                    f"SHA-256 {digest[:12]}{timing_text})",
                    level="success",
                )
                return
            if time.monotonic() >= deadline:
                self._interlock_manual_execution(
                    "Moonraker accepted the manual script, but its unique "
                    "completion marker was not observed. Partial execution or "
                    "lost console output cannot be excluded."
                )
                return
            self._schedule(self.POLL_MS, inspect_console)

        inspect_console()

    def _interlock_manual_execution(self, detail: str) -> None:
        self._interlock_execution("Send manual G-code", detail)

    def _interlock_execution(self, title: str, detail: str) -> None:
        self._operation_busy = False
        self._launch_pending = False
        self._launch_in_flight = False
        self._outcome_unknown = True
        self._refresh_state()
        self._report_error(
            title,
            RuntimeError(
                f"{detail}\n\nControls are interlocked. Inspect the machine "
                "and reconnect before issuing another command."
            ),
        )

    def _live_z_preflight(self) -> Optional[str]:
        view = self.current_view()
        if not view.ready:
            return "Machine must be connected and ready"
        contract_error = remote_control_contract_error(view)
        if contract_error:
            return f"Guarded firmware controls are not ready: {contract_error}"
        if not view.virtual_sd_active:
            return "Live Z trim requires an active virtual-SD job"
        if view.print_state not in {"printing", "paused"}:
            return "Live Z trim is available only during an active job"
        if "z" not in set(view.homed_axes):
            return "Z must be homed before applying live Z trim"
        if not view.offsets_enabled:
            return "Needle tip offsets are not enabled"
        return None

    def _submit_control(
        self,
        future: Any,
        status: str,
        title: str,
        *,
        console_since: Optional[int] = None,
        success_message: Optional[str] = None,
        interlock_on_error: bool = False,
    ) -> None:
        marker = self._console_marker() if console_since is None else console_since
        token = self._begin_operation(status)
        self._watch_future(
            future,
            token=token,
            on_success=lambda result: self._control_accepted(
                token,
                title,
                marker,
                result,
                success_message,
                interlock_on_error,
            ),
            title=title,
            interlock_on_error=interlock_on_error,
        )

    def _control_accepted(
        self,
        token: int,
        title: str,
        console_since: int,
        result: Any,
        success_message: Optional[str],
        interlock_on_error: bool,
    ) -> None:
        if token != self._operation_token:
            return

        def finalize() -> None:
            if token != self._operation_token:
                return
            console_error = self._console_error_since(console_since)
            if console_error:
                if interlock_on_error:
                    self._interlock_execution(
                        title,
                        "Klipper reported an error after the physical command "
                        "was submitted, so partial execution cannot be excluded: "
                        f"{console_error}",
                    )
                else:
                    self._finish_operation()
                    self._report_error(
                        title,
                        RuntimeError(
                            f"Klipper rejected the command: {console_error}"
                        ),
                        popup=False,
                    )
                return
            self._finish_operation()
            timing = getattr(result, "timing", None)
            total_ms = float(getattr(timing, "total_ms", 0.0))
            text = success_message or (
                "Command accepted; live state will confirm the result"
            )
            if total_ms > 0:
                text = f"{text} ({total_ms:.0f} ms)"
            self.panel.set_operation(text, level="success")

        self._schedule(
            100,
            finalize,
        )

    def _console_marker(self) -> int:
        if self.runtime is None:
            return 0
        entries = self.runtime.console_snapshot()
        return int(getattr(entries[-1], "sequence", 0)) if entries else 0

    def _console_entries_since(self, marker: int) -> Tuple[Any, ...]:
        if self.runtime is None:
            return ()
        return tuple(
            entry
            for entry in self.runtime.console_snapshot()
            if int(getattr(entry, "sequence", 0)) > int(marker)
        )

    def _console_error_since(self, marker: int) -> Optional[str]:
        for entry in self._console_entries_since(marker):
            if entry.level == "error":
                return entry.text
        return None

    def _begin_operation(self, status: str, *, level: str = "info") -> int:
        self._operation_token += 1
        self._operation_busy = True
        self._launch_pending = False
        self._launch_in_flight = False
        self.panel.set_operation(status, level=level)
        self._refresh_state()
        return self._operation_token

    def _finish_operation(self) -> None:
        self._operation_busy = False
        self._launch_pending = False
        self._launch_in_flight = False
        self._refresh_state()

    def _watch_future(
        self,
        future: Any,
        *,
        token: int,
        on_success: Callable[[Any], None],
        title: str,
        interlock_on_error: bool = False,
    ) -> None:
        def poll() -> None:
            if self._closed or token != self._operation_token:
                return
            if not future.done():
                self._schedule(self.POLL_MS, poll)
                return
            try:
                result = future.result()
            except Exception as exc:
                if (
                    isinstance(exc, MoonrakerCommandOutcomeUnknown)
                    or interlock_on_error
                ):
                    self._operation_busy = False
                    self._launch_pending = False
                    self._launch_in_flight = False
                    self._outcome_unknown = True
                    self._refresh_state()
                else:
                    self._finish_operation()
                popup = not isinstance(exc, MoonrakerCommandOutcomeUnknown)
                if interlock_on_error and not isinstance(
                    exc,
                    MoonrakerCommandOutcomeUnknown,
                ):
                    exc = RuntimeError(
                        f"{exc}\n\nThe submitted machine command may have executed "
                        "partially. Controls are interlocked; inspect the "
                        "machine and reconnect before issuing another command."
                    )
                self._report_error(title, exc, popup=popup)
                return
            try:
                on_success(result)
            except Exception as exc:
                was_launching = self._launch_in_flight
                if was_launching or interlock_on_error:
                    self._operation_busy = False
                    self._launch_pending = False
                    self._launch_in_flight = False
                    self._outcome_unknown = True
                    self._refresh_state()
                else:
                    self._finish_operation()
                if interlock_on_error:
                    exc = RuntimeError(
                        f"{exc}\n\nMachine command execution status is unknown. "
                        "Controls are interlocked; inspect the machine and "
                        "reconnect before issuing another command."
                    )
                self._report_error(title, exc)

        self._schedule(self.POLL_MS, poll)

    def _schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if self._closed:
            return
        holder = {}

        def wrapped() -> None:
            after_id = holder.get("id")
            if after_id is not None:
                self._after_ids.discard(after_id)
            if not self._closed:
                callback()

        after_id = self.root.after(int(delay_ms), wrapped)
        holder["id"] = after_id
        self._after_ids.add(after_id)

    def _update_position_sink(
        self,
        position: Optional[Tuple[float, float, float]],
        homed_axes: str,
    ) -> None:
        if self.position_sink is None:
            return
        try:
            self.position_sink(position, str(homed_axes or ""))
        except Exception:
            logger.debug("canvas.toolhead_update_failed", exc_info=True)

    def _clear_position_sink(self) -> None:
        self._update_position_sink(None, "")

    def _report_error(
        self,
        title: str,
        error: BaseException,
        *,
        popup: bool = True,
    ) -> None:
        if isinstance(error, MoonrakerCommandOutcomeUnknown):
            text = (
                f"{error}\n\nControls are interlocked. Inspect the machine and "
                "reconnect before issuing another command."
            )
            level = "warning"
        elif isinstance(error, MoonrakerPrintQueuedError):
            text = (
                f"{error}\n\nInspect Moonraker immediately and cancel any queued "
                "job before leaving the machine unattended."
            )
            level = "error"
        else:
            text = str(error) or error.__class__.__name__
            level = "error"
        self.panel.set_operation(text, level=level)
        logger.warning(
            "machine.operation_failed | title=%s | error_type=%s | error=%s",
            title,
            error.__class__.__name__,
            text,
        )
        if popup:
            try:
                messagebox.showerror(title, text, parent=self.root)
            except Exception:
                logger.debug("machine.error_dialog_failed", exc_info=True)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._operation_token += 1
        self._clear_position_sink()
        for after_id in tuple(self._after_ids):
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None
        if self.runtime is not None:
            stopped = self.runtime.stop(timeout=2.0)
            log_options(logger, "moonraker.runtime_stopped", stopped=stopped)
            self.runtime = None
        if self._owns_executor:
            self._executor.shutdown(wait=False)


__all__ = [
    "MachineControlController",
    "MachineView",
    "machine_view_from_state",
    "missing_remote_commands",
    "remote_control_contract_error",
    "start_preflight_error",
]
