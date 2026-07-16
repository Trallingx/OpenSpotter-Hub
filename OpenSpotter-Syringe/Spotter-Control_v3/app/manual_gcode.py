"""Parse and classify manual Klipper G-code without executing it.

This module is intentionally independent of Tk, Moonraker, and the machine
controller.  It normalizes and inspects operator-provided text only; callers
must make a separate, explicit decision before sending any returned script.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from typing import Optional, Tuple


MAX_MANUAL_GCODE_BYTES = 16 * 1024
MAX_MANUAL_GCODE_LINES = 100
MAX_MANUAL_GCODE_COMMANDS = 50

CATEGORY_MOTION = "motion"
CATEGORY_HOMING = "homing/probing"
CATEGORY_HEATER = "heater control"
CATEGORY_STATE = "offset/state change"
CATEGORY_FIRMWARE = "firmware restart/shutdown"
CATEGORY_EMERGENCY = "emergency stop"
CATEGORY_UNKNOWN_MACRO = "unknown macro"
CATEGORY_OTHER = "other"

_CATEGORY_ORDER = (
    CATEGORY_EMERGENCY,
    CATEGORY_FIRMWARE,
    CATEGORY_HOMING,
    CATEGORY_MOTION,
    CATEGORY_HEATER,
    CATEGORY_STATE,
    CATEGORY_UNKNOWN_MACRO,
    CATEGORY_OTHER,
)

_STANDARD_COMMAND_PREFIX = re.compile(
    r"^([GMT]\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_STANDARD_COMMAND_NAME = re.compile(
    r"^([GMT])(\d+)(?:\.(\d+))?$",
    re.IGNORECASE,
)
_COMPACT_PARAMETERS = re.compile(
    r"(?:[A-Za-z][-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[Ee][-+]?\d+)?)+$",
)
_MACRO_COMMAND = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)(?=\s|$)",
)
_HASH_COMMENT = re.compile(r"^(\s*)#")
_LINE_NUMBER_PREFIX = re.compile(
    r"^[Nn]\s*\d+(?:\s+|(?=[GMTgmt]\d))"
)
_CHECKSUM_SUFFIX = re.compile(r"\s*\*\s*[+-]?\d+\s*$")
_DISABLE_TCP_REQUIREMENT = re.compile(
    r"(?:^|\s)REQUIRE_TCP\s*=\s*[-+]?0+(?:\.0+)?(?=\s|$)",
    re.IGNORECASE,
)

_EMERGENCY_COMMANDS = {
    "M112",
    "EMERGENCY_STOP",
}
_FIRMWARE_COMMANDS = {
    "M999",
    "FIRMWARE_RESTART",
    "HOST_REBOOT",
    "HOST_SHUTDOWN",
    "REBOOT",
    "RESTART",
    "SAVE_CONFIG",
    "SHUTDOWN",
}
_HOMING_COMMANDS = {
    "G28",
    "G29",
    "G32",
    "BED_MESH_CALIBRATE",
    "BED_SCREWS_ADJUST",
    "DELTA_CALIBRATE",
    "ENDSTOP_PHASE_CALIBRATE",
    "HOME",
    "HOME_SYRINGE",
    "LOAD_BLTOUCH",
    "MESH",
    "OPENSPOTTER_HOME",
    "PARK_BLTOUCH",
    "PROBE",
    "PROBE_ACCURACY",
    "PROBE_CALIBRATE",
    "QUAD_GANTRY_LEVEL",
    "SCREWS_TILT_CALCULATE",
    "TCPSTART",
    "Z_ENDSTOP_CALIBRATE",
    "Z_TILT_ADJUST",
}
_MOTION_COMMANDS = {
    "G0",
    "G1",
    "G2",
    "G3",
    "G5",
    "G10",
    "G11",
    "ASPIRATE",
    "DISPENSE",
    "FORCE_MOVE",
    "LOAD_FILAMENT",
    "MANUAL_STEPPER",
    "OPENSPOTTER_JOG",
    "STEPPER_BUZZ",
    "SYRINGE_DISPENSE_01",
    "SYRINGE_DISPENSE_1",
    "SYRINGE_DISPENSE_10",
    "UNLOAD_FILAMENT",
    "_NEEDLE_CORRECTED_MOVE",
}
_HEATER_COMMANDS = {
    "M104",
    "M109",
    "M140",
    "M141",
    "M190",
    "M191",
    "PID_CALIBRATE",
    "SET_HEATER_TEMPERATURE",
    "TEMPERATURE_WAIT",
    "TURN_OFF_HEATERS",
}
_STATE_COMMANDS = {
    "G20",
    "G21",
    "G90",
    "G91",
    "G92",
    "M0",
    "M1",
    "M18",
    "M24",
    "M25",
    "M82",
    "M83",
    "M84",
    "M106",
    "M107",
    "M204",
    "M205",
    "M220",
    "M221",
    "M524",
    "M566",
    "ACTIVATE_EXTRUDER",
    "ADJUST_NEEDLE_SURFACE_OFFSET",
    "BED_MESH_CLEAR",
    "BED_MESH_PROFILE",
    "CANCEL_PRINT",
    "CLEAR_DEAD_ZONES",
    "MESH_CLEAR",
    "MESH_LOAD",
    "MOVEMENT_SAFETY_DISABLE",
    "MOVEMENT_SAFETY_ENABLE",
    "NEEDLE_TIP_OFFSETS_DISABLE",
    "NEEDLE_TIP_OFFSETS_ENABLE",
    "OPENSPOTTER_JOB_CLEANUP",
    "OPENSPOTTER_SET_PROMPT",
    "PAUSE",
    "REMOVE_DEAD_ZONE",
    "RESET_NEEDLE_SURFACE_OFFSET",
    "RESTORE_GCODE_STATE",
    "RESUME",
    "SAVE_GCODE_STATE",
    "SAVE_VARIABLE",
    "SDCARD_PRINT_FILE",
    "SDCARD_RESET_FILE",
    "SET_BLTOUCH_DOCK_STATE",
    "SET_DEAD_ZONE",
    "SET_EXTRUDER_ROTATION_DISTANCE",
    "SET_FAN_SPEED",
    "SET_GCODE_OFFSET",
    "SET_GCODE_VARIABLE",
    "SET_INPUT_SHAPER",
    "SET_KINEMATIC_POSITION",
    "SET_NEEDLE_SURFACE_OFFSET",
    "SET_PIN",
    "SET_PRESSURE_ADVANCE",
    "SET_SERVO",
    "SET_TMC_CURRENT",
    "SET_TMC_FIELD",
    "SET_TMC_HOLDCURRENT",
    "SET_VELOCITY_LIMIT",
    "SYNC_EXTRUDER_MOTION",
    "SYNC_STEPPER_TO_EXTRUDER",
    "TCPABORT",
    "TCPOFF",
    "TCPON",
}
_INFORMATIONAL_COMMANDS = {
    "G4",
    "M105",
    "M114",
    "M115",
    "M117",
    "M118",
    "M119",
    "M400",
    "DUMP_TMC",
    "GET_POSITION",
    "HELP",
    "MOVEMENT_SAFETY_STATUS",
    "NEEDLE_TIP_OFFSETS_STATUS",
    "OPENSPOTTER_RUNTIME_STATUS",
    "QUERY_ADC",
    "QUERY_ENDSTOPS",
    "QUERY_FILAMENT_SENSOR",
    "QUERY_PROBE",
    "RESPOND",
    "WAIT",
}

_SAFE_OPENSPOTTER_MACROS = {
    "OPENSPOTTER_HOME",
    "OPENSPOTTER_JOG",
    "OPENSPOTTER_RUNTIME_STATUS",
}
_ALLOWED_MANUAL_COMMANDS = frozenset(
    (_INFORMATIONAL_COMMANDS - {"WAIT"})
    | {
        "G0",
        "G1",
        "G90",
        "G91",
        "M112",
        "EMERGENCY_STOP",
        "OPENSPOTTER_HOME",
        "OPENSPOTTER_JOG",
    }
)
_BLOCKED_COMMAND_REASONS = {
    "G2": "arc motion bypasses the reviewed linear-move safety wrapper",
    "G3": "arc motion bypasses the reviewed linear-move safety wrapper",
    "G5": "spline motion bypasses the reviewed linear-move safety wrapper",
    "G28": "raw homing bypasses the reviewed OPENSPOTTER_HOME sequence",
    "G92": "raw coordinate reassignment can invalidate machine safety state",
    "FORCE_MOVE": "force moves bypass homing and normal kinematic safeguards",
    "MANUAL_STEPPER": "direct stepper control bypasses reviewed motion safeguards",
    "MOVEMENT_SAFETY_DISABLE": "movement safety may not be disabled manually",
    "SET_KINEMATIC_POSITION": "kinematic position spoofing bypasses homing safeguards",
    "SET_STEPPER_ENABLE": "direct stepper enable changes bypass reviewed controls",
    "SET_TMC_CURRENT": "direct driver-current changes are not permitted manually",
    "SET_TMC_FIELD": "direct TMC register changes are not permitted manually",
    "SET_TMC_HOLDCURRENT": "direct driver-current changes are not permitted manually",
    "SET_GCODE_VARIABLE": "arbitrary macro-state mutation is not permitted manually",
    "SET_GCODE_OFFSET": "raw coordinate offsets bypass reviewed needle-offset macros",
    "SET_PIN": "direct output-pin changes are not permitted manually",
    "SET_SERVO": "direct servo changes are not permitted manually",
    "CLEAR_DEAD_ZONES": "movement dead-zone protections may not be cleared manually",
    "REMOVE_DEAD_ZONE": "movement dead-zone protections may not be removed manually",
    "SET_DEAD_ZONE": "movement dead-zone protections may not be changed manually",
    "SDCARD_PRINT_FILE": "manual virtual-SD starts bypass detached-artifact preflight",
    "SDCARD_RESET_FILE": "manual virtual-SD resets bypass reviewed job controls",
    "M18": "manual motor disable can invalidate homing and position state",
    "M84": "manual motor disable can invalidate homing and position state",
    "SAVE_VARIABLE": "arbitrary persistent machine-state changes are not permitted",
    "WAIT": "the custom WAIT macro can delay execution indefinitely",
}
_KNOWN_STANDARD_COMMANDS = frozenset(
    command
    for command in (
        _EMERGENCY_COMMANDS
        | _FIRMWARE_COMMANDS
        | _HOMING_COMMANDS
        | _MOTION_COMMANDS
        | _HEATER_COMMANDS
        | _STATE_COMMANDS
        | _INFORMATIONAL_COMMANDS
    )
    if _STANDARD_COMMAND_NAME.fullmatch(command)
)

_WARNING_TEXT = {
    CATEGORY_MOTION: "can move machine axes or the syringe",
    CATEGORY_HOMING: "can home, probe, calibrate, or otherwise move the machine",
    CATEGORY_HEATER: "can change heater targets or wait on thermal state",
    CATEGORY_STATE: "changes offsets, coordinate modes, outputs, or printer state",
    CATEGORY_FIRMWARE: "can restart firmware or shut down the printer host",
    CATEGORY_EMERGENCY: "requests an immediate emergency stop",
}


class ManualGcodeValidationError(ValueError):
    """Raised when manual G-code text cannot be safely inspected."""


@dataclass(frozen=True)
class ManualGcodeCommand:
    """One executable line identified in a manual script."""

    line_number: int
    name: str
    text: str
    category: str
    warning: Optional[str]
    blocked_reason: Optional[str]


@dataclass(frozen=True)
class ManualGcodeParseResult:
    """Immutable inspection result; it does not provide an execution method."""

    normalized_script: str
    commands: Tuple[ManualGcodeCommand, ...]
    warnings: Tuple[str, ...]
    blocked_reasons: Tuple[str, ...]
    requires_confirmation: bool
    summary: str

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_reasons)


def _normalize_command_name(name: str) -> str:
    upper = name.upper()
    match = _STANDARD_COMMAND_NAME.fullmatch(upper)
    if match is None:
        return upper
    letter, whole, fraction = match.groups()
    normalized = f"{letter.upper()}{int(whole)}"
    if fraction is not None:
        normalized += f".{fraction.rstrip('0') or '0'}"
    return normalized


def _normalize_source_line(source_line: str, line_number: int) -> str:
    hash_comment = _HASH_COMMENT.match(source_line)
    if hash_comment is not None:
        return (
            hash_comment.group(1)
            + ";"
            + source_line[hash_comment.end() :]
        )

    code, separator, comment = source_line.partition(";")
    executable = code.strip()
    if not executable:
        return source_line
    framing_removed = False
    line_prefix = _LINE_NUMBER_PREFIX.match(executable)
    if line_prefix is not None:
        executable = executable[line_prefix.end() :].strip()
        framing_removed = True
    checksum = _CHECKSUM_SUFFIX.search(executable)
    if checksum is not None and (
        framing_removed or _STANDARD_COMMAND_PREFIX.match(executable)
    ):
        executable = executable[: checksum.start()].rstrip()
        framing_removed = True
    if not framing_removed:
        return source_line
    if not executable:
        raise ManualGcodeValidationError(
            f"Line {line_number} contains transport framing but no command"
        )
    if executable.startswith("#"):
        executable = ";" + executable[1:]
    if separator:
        return f"{executable} ;{comment}"
    return executable


def _command_name(executable: str, line_number: int) -> str:
    first_token = executable.split(None, 1)[0]
    full_standard = _STANDARD_COMMAND_NAME.fullmatch(first_token)
    if full_standard is not None:
        return _normalize_command_name(first_token)
    standard = _STANDARD_COMMAND_PREFIX.match(first_token)
    if (
        standard is not None
        and standard.end() < len(first_token)
        and _COMPACT_PARAMETERS.fullmatch(first_token[standard.end() :])
    ):
        return _normalize_command_name(standard.group(1))
    macro = _MACRO_COMMAND.match(executable)
    if macro is not None:
        return macro.group(1).upper()
    raise ManualGcodeValidationError(
        f"Line {line_number} does not start with a valid G-code or Klipper macro name"
    )


def _classify_command(name: str) -> str:
    standard_match = _STANDARD_COMMAND_NAME.fullmatch(name)
    standard_base = name.split(".", 1)[0] if standard_match is not None else name
    if standard_base in _EMERGENCY_COMMANDS:
        return CATEGORY_EMERGENCY
    if standard_base in _FIRMWARE_COMMANDS:
        return CATEGORY_FIRMWARE
    if standard_base in _HOMING_COMMANDS:
        return CATEGORY_HOMING
    if standard_base in _MOTION_COMMANDS:
        return CATEGORY_MOTION
    if standard_base in _HEATER_COMMANDS:
        return CATEGORY_HEATER
    if standard_base in _STATE_COMMANDS or name.startswith("SET_TMC_"):
        return CATEGORY_STATE
    if name in _INFORMATIONAL_COMMANDS or standard_base in _INFORMATIONAL_COMMANDS:
        return CATEGORY_OTHER
    if standard_match is not None:
        return CATEGORY_STATE
    return CATEGORY_UNKNOWN_MACRO


def _blocked_reason(
    command_name: str,
    executable: str,
    category: str,
) -> Optional[str]:
    if command_name.startswith(("G0.", "G1.")):
        return "renamed raw motion commands bypass the reviewed G0/G1 safety wrapper"
    explicit = _BLOCKED_COMMAND_REASONS.get(command_name)
    if explicit is not None:
        return explicit
    if command_name.startswith("_"):
        return "private firmware macros may not be called from manual G-code"
    if (
        command_name.startswith("OPENSPOTTER_")
        and command_name not in _SAFE_OPENSPOTTER_MACROS
    ):
        return "job-only OpenSpotter macros may not be called manually"
    if command_name.startswith("SET_TMC_"):
        return "direct TMC driver changes are not permitted manually"
    if category == CATEGORY_FIRMWARE:
        return (
            "firmware and host lifecycle commands can invalidate the active "
            "control session"
        )
    if (
        command_name == "NEEDLE_TIP_OFFSETS_ENABLE"
        and _DISABLE_TCP_REQUIREMENT.search(executable)
    ):
        return "REQUIRE_TCP=0 bypasses the required TCP calibration interlock"
    if command_name in _ALLOWED_MANUAL_COMMANDS:
        return None
    if (
        _STANDARD_COMMAND_NAME.fullmatch(command_name)
        and command_name not in _KNOWN_STANDARD_COMMANDS
    ):
        return (
            f"standard command '{command_name}' is outside the reviewed "
            "manual-command allowlist"
        )
    if category == CATEGORY_UNKNOWN_MACRO:
        return (
            f"macro '{command_name}' is not in the reviewed manual-command allowlist"
        )
    return (
        f"command '{command_name}' is outside the restricted manual-command "
        "allowlist"
    )


def _warning_for(
    category: str,
    *,
    line_number: int,
    command_name: str,
) -> Optional[str]:
    if category == CATEGORY_UNKNOWN_MACRO:
        return (
            f"Line {line_number}: unknown macro '{command_name}'; "
            "its configured behavior cannot be determined"
        )
    detail = _WARNING_TEXT.get(category)
    if detail is None:
        return None
    return f"Line {line_number}: {command_name} {detail}"


def _summary(
    commands: Tuple[ManualGcodeCommand, ...],
    blocked_reasons: Tuple[str, ...],
) -> str:
    if not commands:
        return "No executable commands."
    counts = Counter(command.category for command in commands)
    categories = ", ".join(
        f"{counts[category]} {category}"
        for category in _CATEGORY_ORDER
        if counts[category]
    )
    command_label = "command" if len(commands) == 1 else "commands"
    if blocked_reasons:
        reason_label = "reason" if len(blocked_reasons) == 1 else "reasons"
        status = (
            f"BLOCKED ({len(blocked_reasons)} {reason_label}); "
            "confirmation cannot override"
        )
    else:
        status = (
            "confirmation required"
            if any(command.warning for command in commands)
            else "no confirmation warnings"
        )
    return (
        f"{len(commands)} executable {command_label}: "
        f"{categories}; {status}."
    )


def _validate_text(script: str) -> None:
    if not isinstance(script, str):
        raise ManualGcodeValidationError("Manual G-code must be provided as text")
    try:
        encoded_size = len(script.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ManualGcodeValidationError(
            "Manual G-code contains invalid Unicode text"
        ) from exc
    if encoded_size > MAX_MANUAL_GCODE_BYTES:
        raise ManualGcodeValidationError(
            "Manual G-code exceeds the "
            f"{MAX_MANUAL_GCODE_BYTES:,}-byte safety limit"
        )
    for offset, character in enumerate(script):
        if character == "\x00":
            raise ManualGcodeValidationError(
                f"Manual G-code contains a NUL character at offset {offset}"
            )
        if (
            character not in {"\t", "\n", "\r"}
            and unicodedata.category(character) in {"Cc", "Cf"}
        ):
            raise ManualGcodeValidationError(
                "Manual G-code contains forbidden control character "
                f"U+{ord(character):04X} at offset {offset}"
            )


def parse_manual_gcode(script: str) -> ManualGcodeParseResult:
    """Normalize and inspect a manual Klipper script without executing it."""
    _validate_text(script)
    newline_normalized = script.replace("\r\n", "\n").replace("\r", "\n")
    line_count = (
        0
        if not newline_normalized
        else newline_normalized.count("\n")
        + (0 if newline_normalized.endswith("\n") else 1)
    )
    if line_count > MAX_MANUAL_GCODE_LINES:
        raise ManualGcodeValidationError(
            "Manual G-code exceeds the "
            f"{MAX_MANUAL_GCODE_LINES:,}-line safety limit"
        )
    normalized = "\n".join(
        _normalize_source_line(source_line, line_number)
        for line_number, source_line in enumerate(
            newline_normalized.split("\n"),
            start=1,
        )
    )

    commands = []
    for line_number, source_line in enumerate(normalized.split("\n"), start=1):
        stripped = source_line.strip()
        if (
            not stripped
            or stripped.startswith(";")
            or stripped.startswith("#")
            or (stripped.startswith("(") and stripped.endswith(")"))
        ):
            continue
        executable = source_line.split(";", 1)[0].strip()
        if (
            not executable
            or executable.startswith("#")
            or (executable.startswith("(") and executable.endswith(")"))
        ):
            continue
        name = _command_name(executable, line_number)
        category = _classify_command(name)
        warning = _warning_for(
            category,
            line_number=line_number,
            command_name=name,
        )
        blocked_reason = _blocked_reason(name, executable, category)
        if len(commands) >= MAX_MANUAL_GCODE_COMMANDS:
            raise ManualGcodeValidationError(
                "Manual G-code exceeds the "
                f"{MAX_MANUAL_GCODE_COMMANDS:,}-command safety limit"
            )
        command = ManualGcodeCommand(
            line_number=line_number,
            name=name,
            text=executable,
            category=category,
            warning=warning,
            blocked_reason=blocked_reason,
        )
        commands.append(command)

    if len(commands) > 1:
        mixed_emergency_reason = (
            "emergency stop must be the only executable command in its script"
        )
        for index, command in enumerate(commands):
            if command.category == CATEGORY_EMERGENCY:
                commands[index] = replace(
                    command,
                    blocked_reason=command.blocked_reason
                    or mixed_emergency_reason,
                )
    immutable_commands = tuple(commands)
    immutable_warnings = tuple(
        command.warning
        for command in immutable_commands
        if command.warning is not None
    )
    immutable_blocked_reasons = tuple(
        f"Line {command.line_number}: {command.blocked_reason}"
        for command in immutable_commands
        if command.blocked_reason is not None
    )
    return ManualGcodeParseResult(
        normalized_script=normalized,
        commands=immutable_commands,
        warnings=immutable_warnings,
        blocked_reasons=immutable_blocked_reasons,
        requires_confirmation=bool(
            immutable_warnings or immutable_blocked_reasons
        ),
        summary=_summary(
            immutable_commands,
            immutable_blocked_reasons,
        ),
    )


__all__ = [
    "MAX_MANUAL_GCODE_BYTES",
    "MAX_MANUAL_GCODE_LINES",
    "MAX_MANUAL_GCODE_COMMANDS",
    "CATEGORY_MOTION",
    "CATEGORY_HOMING",
    "CATEGORY_HEATER",
    "CATEGORY_STATE",
    "CATEGORY_FIRMWARE",
    "CATEGORY_EMERGENCY",
    "CATEGORY_UNKNOWN_MACRO",
    "CATEGORY_OTHER",
    "ManualGcodeValidationError",
    "ManualGcodeCommand",
    "ManualGcodeParseResult",
    "parse_manual_gcode",
]
