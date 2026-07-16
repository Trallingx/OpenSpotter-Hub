"""Detached job snapshots and exact runtime G-code artifacts.

Tk widgets are captured on the GUI thread, then converted into small value
adapters so the existing planner and workflow generator can run safely in a
worker thread without touching Tk.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
import uuid
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .gcode_workflow import load_workflow
from .grid_gcode import save_grid_gcode
from .input_configs import (
    CLEANING_FIELDS,
    GLOBAL_FIELDS,
    GRID_FIELDS,
    SPIRAL_FIELDS,
    WASHING_FIELDS,
)
from .paths import GCODE_DIR, WORKFLOW_CONFIG
from .runtime_logging import get_logger, log_options
from .spiral_gcode import save_spiral_gcode


logger = get_logger("machine.runtime_job")

MAX_PATTERN_COUNT = 64
MAX_GRID_AXIS_POINTS = 500
MAX_GRID_POINTS_PER_PATTERN = 25_000
MAX_TOTAL_PATTERN_POINTS = 100_000
MAX_MAINTENANCE_CYCLES = 100
MAX_SPIRAL_POINTS = 100_000
MAX_RUNTIME_ARTIFACT_BYTES = 50 * 1024 * 1024
MAX_RECIPE_TEXT_LENGTH = 120
RUNTIME_ARTIFACT_RETENTION = 20


class FrozenDict(MappingABC):
    """Small immutable mapping for detached scalar input snapshots."""

    def __init__(self, values: Mapping[str, Any]):
        self._data = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __deepcopy__(self, _memo):
        return self


@dataclass(frozen=True)
class GridJobSnapshot:
    number: int
    grid: Mapping[str, Any]
    cleaning: Mapping[str, Any]
    washing: Mapping[str, Any]
    flags: Mapping[str, bool]


@dataclass(frozen=True)
class SpiralJobSnapshot:
    number: int
    spiral: Mapping[str, Any]


@dataclass(frozen=True)
class GenerationSnapshot:
    kind: str
    config_dir: str
    global_values: Mapping[str, Any]
    workflow_json: str
    grids: Tuple[GridJobSnapshot, ...] = ()
    spirals: Tuple[SpiralJobSnapshot, ...] = ()


@dataclass(frozen=True)
class JobArtifact:
    kind: str
    path: Path
    settings_path: Path
    sha256: str
    size: int
    remote_path: str
    line_offsets: Tuple[int, ...]

    @property
    def line_count(self) -> int:
        return max(1, len(self.line_offsets))

    def line_index_for_file_position(self, file_position: int) -> int:
        """Map Moonraker's virtual-SD byte position to a zero-based line."""
        position = max(0, min(int(file_position), self.size))
        index = bisect.bisect_right(self.line_offsets, position) - 1
        return max(0, min(index, self.line_count - 1))

    def context_for_file_position(
        self,
        file_position: int,
        before: int = 4,
        after: int = 8,
    ) -> Tuple[int, Tuple[Tuple[int, str], ...]]:
        current = self.line_index_for_file_position(file_position)
        start = max(0, current - max(0, int(before)))
        stop = min(self.line_count, current + max(0, int(after)) + 1)
        rows: List[Tuple[int, str]] = []
        with self.path.open("rb") as handle:
            handle.seek(self.line_offsets[start])
            for index in range(start, stop):
                line = handle.readline().decode("utf-8", errors="replace")
                rows.append((index, line.rstrip("\r\n")))
        return current, tuple(rows)


class _ValueSource:
    def __init__(self, value: Any):
        self._value = value

    def get(self) -> str:
        return str(self._value)


class _BooleanSource:
    def __init__(self, value: Any):
        self._value = bool(value)

    def get(self) -> bool:
        return self._value


def _entries(fields: Sequence[Any], values: Mapping[str, Any]) -> List[_ValueSource]:
    return [_ValueSource(values.get(field.key, field.default)) for field in fields]


class _GridAdapter:
    def __init__(self, snapshot: GridJobSnapshot):
        self.grid_entry = _entries(GRID_FIELDS, snapshot.grid)
        self.cleaning_entry = _entries(CLEANING_FIELDS, snapshot.cleaning)
        self.washing_entry = _entries(WASHING_FIELDS, snapshot.washing)
        self.cleaning_enabled = _BooleanSource(snapshot.flags.get("cleaning_enabled"))
        self.washing_enabled = _BooleanSource(snapshot.flags.get("washing_enabled"))
        self.wash_after_loading_enabled = _BooleanSource(
            snapshot.flags.get("wash_after_loading")
        )
        self.final_rinse_enabled = _BooleanSource(
            snapshot.flags.get("final_rinse_enabled")
        )
        self.final_rinse_add_cleaning_grid = _BooleanSource(
            snapshot.flags.get("final_rinse_add_cleaning_grid")
        )
        self._name = str(snapshot.grid.get("name", f"Grid {snapshot.number}"))
        self._color = str(snapshot.grid.get("color", "green"))

    def get_grid_name(self) -> str:
        return self._name

    def get_grid_color(self) -> str:
        return self._color


class _SpiralAdapter:
    def __init__(self, snapshot: SpiralJobSnapshot):
        self.spiral_entry = _entries(SPIRAL_FIELDS, snapshot.spiral)
        self._name = str(snapshot.spiral.get("name", f"Spiral {snapshot.number}"))
        self._color = str(snapshot.spiral.get("color", "orange"))

    def get_grid_name(self) -> str:
        return self._name

    def get_grid_color(self) -> str:
        return self._color


class _GenerationAdapter:
    def __init__(self, snapshot: GenerationSnapshot):
        self.config_dir = snapshot.config_dir
        self.workflow_data = json.loads(snapshot.workflow_json)
        self.entry = _entries(GLOBAL_FIELDS, snapshot.global_values)
        self.grid_tab_dict = {
            item.number: _GridAdapter(item) for item in snapshot.grids
        }
        self.spiral_tab_dict = {
            item.number: _SpiralAdapter(item) for item in snapshot.spirals
        }


def _strict_entries_to_dict(
    entries: Sequence[Any],
    fields: Sequence[Any],
    context: str,
) -> Dict[str, Any]:
    if len(entries) < len(fields):
        raise ValueError(
            f"{context} is missing {len(fields) - len(entries)} required input field(s)"
        )

    result: Dict[str, Any] = {}
    errors: List[str] = []
    true_values = {"1", "true", "yes", "on"}
    false_values = {"0", "false", "no", "off"}
    for entry, field in zip(entries, fields):
        try:
            raw = entry.get()
            unit = str(field.unit).strip().lower()
            if unit == "bool" or isinstance(field.default, bool):
                if isinstance(raw, bool):
                    value = raw
                else:
                    normalized = str(raw).strip().lower()
                    if normalized in true_values:
                        value = True
                    elif normalized in false_values:
                        value = False
                    else:
                        raise ValueError("expected true or false")
            elif unit == "int" or (
                isinstance(field.default, int) and not isinstance(field.default, bool)
            ):
                numeric = float(raw)
                if not math.isfinite(numeric) or not numeric.is_integer():
                    raise ValueError("expected a finite whole number")
                value = int(numeric)
            elif unit == "str" or isinstance(field.default, str):
                value = str(raw)
            else:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("expected a finite number")
            result[field.key] = value
        except Exception as exc:
            errors.append(f"{field.label}: {exc}")
    if errors:
        raise ValueError(f"{context} contains invalid values:\n- " + "\n- ".join(errors))
    return result


def _require_range(
    values: Mapping[str, Any],
    key: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    nonzero: bool = False,
    label: Optional[str] = None,
) -> None:
    value = float(values[key])
    display = label or key
    if minimum is not None and value < minimum:
        raise ValueError(f"{display} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{display} must be at most {maximum}")
    if nonzero and abs(value) < 1e-12:
        raise ValueError(f"{display} must be non-zero")


def _validated_recipe_text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > MAX_RECIPE_TEXT_LENGTH:
        raise ValueError(
            f"{label} must be at most {MAX_RECIPE_TEXT_LENGTH} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(
            f"{label} must not contain newlines or control characters"
        )
    return text


def _validate_global(values: Mapping[str, Any]) -> None:
    for key in ("base_square_x", "base_square_y", "acceptance_square_x", "acceptance_square_y"):
        _require_range(values, key, minimum=0.000001)
    _require_range(values, "mesh_points", minimum=3, maximum=10)
    _require_range(
        values,
        "max_grid_count",
        minimum=1,
        maximum=MAX_PATTERN_COUNT,
    )
    for key in (
        "movement_speed",
        "decent_speed",
        "adcent_speed",
        "dispensing_speed",
        "refilling_speed",
        "probe_feed_rate",
        "calibration_feed_rate",
        "present_plate_speed",
    ):
        _require_range(values, key, minimum=0.000001)
    for key in (
        "priming_vol",
        "drop_extra_aspirate",
        "row_start_wait",
        "emptying_wait",
        "rinse_aspiration_wait",
        "rinse_final_wait",
        "syringe_aspirate_wait",
        "syringe_prime_wait",
    ):
        _require_range(values, key, minimum=0)
    _require_range(values, "max_syringe_vol", minimum=0.000001)
    if float(values["priming_vol"]) > float(values["max_syringe_vol"]):
        raise ValueError("Priming Volume cannot exceed Maximum Syringe Volume")
    if float(values["max_syringe_mm"]) <= float(values["min_syringe_mm"]):
        raise ValueError("Max Syringe MM must be greater than Min Syringe MM")


def _validate_container_ids(values: Mapping[str, Any], context: str) -> None:
    for key in ("loading_from", "leftovers_into"):
        value = int(values[key])
        if value < 1 or value > 6:
            raise ValueError(f"{context} {key.replace('_', ' ')} must be between 1 and 6")


def _validate_grid(
    grid: Mapping[str, Any],
    cleaning: Mapping[str, Any],
    washing: Mapping[str, Any],
    flags: Mapping[str, bool],
    context: str,
) -> None:
    _require_range(grid, "rows", minimum=1, label=f"{context} rows")
    _require_range(grid, "cols", minimum=1, label=f"{context} columns")
    _require_range(
        grid,
        "rows",
        maximum=MAX_GRID_AXIS_POINTS,
        label=f"{context} rows",
    )
    _require_range(
        grid,
        "cols",
        maximum=MAX_GRID_AXIS_POINTS,
        label=f"{context} columns",
    )
    grid_points = int(grid["rows"]) * int(grid["cols"])
    if grid_points > MAX_GRID_POINTS_PER_PATTERN:
        raise ValueError(
            f"{context} has {grid_points:,} spots; the direct-run limit is "
            f"{MAX_GRID_POINTS_PER_PATTERN:,}"
        )
    _require_range(grid, "pitch_x", nonzero=True, label=f"{context} X pitch")
    _require_range(grid, "pitch_y", nonzero=True, label=f"{context} Y pitch")
    _require_range(grid, "dispense_vol", minimum=0.000000001)
    _require_range(grid, "row_add_volume", minimum=0)
    _require_range(grid, "droplet_forming_time", minimum=0)
    _validate_container_ids(grid, context)

    cleaning_required = bool(
        flags.get("cleaning_enabled") or flags.get("final_rinse_add_cleaning_grid")
    )
    if cleaning_required:
        _require_range(cleaning, "rows_cleaning", minimum=1)
        _require_range(cleaning, "cols_cleaning", minimum=1)
        _require_range(
            cleaning,
            "rows_cleaning",
            maximum=MAX_GRID_AXIS_POINTS,
        )
        _require_range(
            cleaning,
            "cols_cleaning",
            maximum=MAX_GRID_AXIS_POINTS,
        )
        cleaning_points = int(cleaning["rows_cleaning"]) * int(
            cleaning["cols_cleaning"]
        )
        if cleaning_points > MAX_GRID_POINTS_PER_PATTERN:
            raise ValueError(
                f"{context} cleaning grid has {cleaning_points:,} spots; "
                f"the direct-run limit is {MAX_GRID_POINTS_PER_PATTERN:,}"
            )
        _require_range(cleaning, "pitch_x_cleaning", nonzero=True)
        _require_range(cleaning, "pitch_y_cleaning", nonzero=True)
        _require_range(cleaning, "dispense_vol_cleaning", minimum=0.000000001)
        _require_range(cleaning, "droplet_forming_time_cleaning", minimum=0)
    _require_range(cleaning, "spots_before_cleaning", minimum=0)
    _require_range(
        cleaning,
        "final_rinse_cycles",
        minimum=0,
        maximum=MAX_MAINTENANCE_CYCLES,
    )

    if flags.get("washing_enabled"):
        _require_range(washing, "washing_speed", minimum=0.000001)
        _require_range(washing, "washing_line_lenght", minimum=0.000001)
        _require_range(
            washing,
            "washing_cycles",
            minimum=1,
            maximum=MAX_MAINTENANCE_CYCLES,
        )
    _require_range(washing, "washing_after_x_spots", minimum=0)


def _validate_spiral(values: Mapping[str, Any], context: str) -> None:
    _require_range(values, "turns", minimum=0, maximum=1000)
    _require_range(values, "num_starts", minimum=1, maximum=64)
    _require_range(values, "spacing_mm", minimum=0.000001)
    _require_range(values, "dispense_vol", minimum=0.000000001)
    _require_range(values, "droplet_forming_time", minimum=0)
    if str(values["spiral_mode"]) not in {"drop", "continuous"}:
        raise ValueError(f"{context} spiral mode must be 'drop' or 'continuous'")
    _validate_container_ids(values, context)


def _workflow_custom_number(
    workflow: Mapping[str, Any],
    name: str,
) -> float:
    for item in workflow.get("custom_variables", []):
        if isinstance(item, Mapping) and str(item.get("name", "")) == name:
            value = float(item.get("value"))
            if math.isfinite(value):
                return value
    raise ValueError(f"Workflow custom variable '{name}' is missing or invalid")


def _estimate_grid_work(
    global_values: Mapping[str, Any],
    grid: Mapping[str, Any],
    cleaning: Mapping[str, Any],
    washing: Mapping[str, Any],
    flags: Mapping[str, bool],
) -> int:
    """Conservatively bound repeated maintenance before generation."""
    rows = int(grid["rows"])
    cols = int(grid["cols"])
    main_points = rows * cols
    cleaning_points = int(cleaning["rows_cleaning"]) * int(
        cleaning["cols_cleaning"]
    )
    cleaning_interval = int(cleaning["spots_before_cleaning"])
    washing_interval = int(washing["washing_after_x_spots"])

    washing_triggers = (
        int(math.ceil(float(main_points) / washing_interval))
        if flags.get("washing_enabled") and washing_interval > 0
        else 0
    )
    scheduled_cleaning_runs = 0
    if flags.get("cleaning_enabled"):
        if cleaning_interval > 0:
            scheduled_cleaning_runs += int(
                math.ceil(float(main_points) / cleaning_interval)
            )
        scheduled_cleaning_runs += washing_triggers
    if flags.get("final_rinse_add_cleaning_grid"):
        scheduled_cleaning_runs += 1

    base_ul = (
        main_points * float(grid["dispense_vol"])
        + max(0, rows - 1) * float(grid["row_add_volume"])
    )
    cleaning_ul = cleaning_points * float(
        cleaning["dispense_vol_cleaning"]
    )
    capacity_ul = float(global_values["max_syringe_vol"])
    fixed_ul = base_ul + scheduled_cleaning_runs * cleaning_ul
    refill_count = max(1, int(math.ceil(fixed_ul / capacity_ul)))
    if flags.get("cleaning_enabled") and cleaning_ul > 0:
        effective_capacity = capacity_ul - cleaning_ul
        if effective_capacity <= 0:
            refill_count = main_points + 1
        else:
            refill_count = min(
                main_points + 1,
                max(1, int(math.ceil(fixed_ul / effective_capacity))),
            )

    cleaning_runs = scheduled_cleaning_runs
    if flags.get("cleaning_enabled"):
        cleaning_runs += refill_count

    washing_runs = 0
    if flags.get("washing_enabled"):
        washing_runs = washing_triggers + 1
        if flags.get("wash_after_loading"):
            washing_runs += refill_count
    washing_work = washing_runs * (
        int(washing["washing_cycles"]) + 2
    )
    rinse_work = (
        2 * int(cleaning["final_rinse_cycles"])
        if flags.get("final_rinse_enabled")
        else 0
    )
    return (
        main_points
        + cleaning_runs * cleaning_points
        + washing_work
        + rinse_work
    )


def capture_generation_snapshot(gui: Any, kind: Optional[str] = None) -> GenerationSnapshot:
    """Capture the current GUI inputs. Call this only from the Tk thread."""
    selected_kind = str(kind or gui._current_workspace_mode()).strip().lower()
    if selected_kind not in {"grid", "spiral"}:
        raise ValueError("Job kind must be 'grid' or 'spiral'")

    config_dir = str(getattr(gui, "config_dir", WORKFLOW_CONFIG.parent))
    workflow_path = Path(config_dir) / WORKFLOW_CONFIG.name
    workflow = load_workflow(workflow_path)
    global_values = _strict_entries_to_dict(
        gui.entry,
        GLOBAL_FIELDS,
        "Global machine parameters",
    )
    _validate_global(global_values)

    grids: List[GridJobSnapshot] = []
    spirals: List[SpiralJobSnapshot] = []
    total_pattern_points = 0
    if selected_kind == "grid":
        for number, grid_obj in sorted(getattr(gui, "grid_tab_dict", {}).items()):
            grid_values = _strict_entries_to_dict(
                grid_obj.grid_entry,
                GRID_FIELDS,
                f"Grid {number}",
            )
            grid_values.update(
                {
                    "name": _validated_recipe_text(
                        grid_obj.get_grid_name()
                        if hasattr(grid_obj, "get_grid_name")
                        else f"Grid {number}",
                        f"Grid {number} name",
                    ),
                    "color": _validated_recipe_text(
                        grid_obj.get_grid_color()
                        if hasattr(grid_obj, "get_grid_color")
                        else "green",
                        f"Grid {number} color",
                    ),
                }
            )
            cleaning_values = _strict_entries_to_dict(
                grid_obj.cleaning_entry,
                CLEANING_FIELDS,
                f"Grid {number} cleaning",
            )
            washing_values = _strict_entries_to_dict(
                grid_obj.washing_entry,
                WASHING_FIELDS,
                f"Grid {number} washing",
            )
            flags = {
                "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
                "washing_enabled": bool(grid_obj.washing_enabled.get()),
                "wash_after_loading": bool(grid_obj.wash_after_loading_enabled.get()),
                "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
                "final_rinse_add_cleaning_grid": bool(
                    grid_obj.final_rinse_add_cleaning_grid.get()
                ),
            }
            _validate_grid(
                grid_values,
                cleaning_values,
                washing_values,
                flags,
                f"Grid {number}",
            )
            estimated_work = _estimate_grid_work(
                global_values,
                grid_values,
                cleaning_values,
                washing_values,
                flags,
            )
            if estimated_work > MAX_TOTAL_PATTERN_POINTS:
                raise ValueError(
                    f"Grid {number} estimates {estimated_work:,} pattern and "
                    f"maintenance operations; the direct-run limit is "
                    f"{MAX_TOTAL_PATTERN_POINTS:,}"
                )
            total_pattern_points += estimated_work
            grids.append(
                GridJobSnapshot(
                    number=number,
                    grid=FrozenDict(grid_values),
                    cleaning=FrozenDict(cleaning_values),
                    washing=FrozenDict(washing_values),
                    flags=FrozenDict(flags),
                )
            )
        if not grids:
            raise ValueError("Add at least one grid before starting a grid job")
        if len(grids) > int(global_values["max_grid_count"]):
            raise ValueError(
                "Active grid count exceeds the configured Maximum Grid Count"
            )
    else:
        spiral_resolution = _workflow_custom_number(
            workflow,
            "spiral_resolution_radians",
        )
        if spiral_resolution <= 0:
            raise ValueError("Spiral resolution must be positive")
        for number, spiral_obj in sorted(getattr(gui, "spiral_tab_dict", {}).items()):
            spiral_values = _strict_entries_to_dict(
                spiral_obj.spiral_entry,
                SPIRAL_FIELDS,
                f"Spiral {number}",
            )
            spiral_values.update(
                {
                    "name": _validated_recipe_text(
                        spiral_obj.get_grid_name()
                        if hasattr(spiral_obj, "get_grid_name")
                        else f"Spiral {number}",
                        f"Spiral {number} name",
                    ),
                    "color": _validated_recipe_text(
                        spiral_obj.get_grid_color()
                        if hasattr(spiral_obj, "get_grid_color")
                        else "orange",
                        f"Spiral {number} color",
                    ),
                }
            )
            _validate_spiral(spiral_values, f"Spiral {number}")
            estimated_points = (
                int(
                    math.floor(
                        (2.0 * math.pi * float(spiral_values["turns"]))
                        / spiral_resolution
                    )
                )
                + 1
            ) * int(spiral_values["num_starts"])
            if estimated_points > MAX_SPIRAL_POINTS:
                raise ValueError(
                    f"Spiral {number} estimates {estimated_points:,} points; "
                    f"the direct-run limit is {MAX_SPIRAL_POINTS:,}"
                )
            total_pattern_points += estimated_points
            spirals.append(
                SpiralJobSnapshot(
                    number=number,
                    spiral=FrozenDict(spiral_values),
                )
            )
        if not spirals:
            raise ValueError("Add at least one spiral before starting a spiral job")
        if len(spirals) > int(global_values["max_grid_count"]):
            raise ValueError(
                "Active spiral count exceeds the configured Maximum Grid Count"
            )

    if total_pattern_points > MAX_TOTAL_PATTERN_POINTS:
        raise ValueError(
            f"The job estimates {total_pattern_points:,} pattern/maintenance "
            f"points; the direct-run limit is {MAX_TOTAL_PATTERN_POINTS:,}"
        )

    snapshot = GenerationSnapshot(
        kind=selected_kind,
        config_dir=config_dir,
        global_values=FrozenDict(global_values),
        workflow_json=json.dumps(workflow, sort_keys=True, separators=(",", ":")),
        grids=tuple(grids),
        spirals=tuple(spirals),
    )
    log_options(
        logger,
        "runtime_job.snapshot_captured",
        kind=selected_kind,
        grid_count=len(grids),
        spiral_count=len(spirals),
        global_options=global_values,
        workflow=workflow,
    )
    return snapshot


def _hash_and_line_index(path: Path) -> Tuple[str, int, Tuple[int, ...]]:
    size = path.stat().st_size
    digest = hashlib.sha256()
    offsets = [0]
    absolute_offset = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            search_from = 0
            while True:
                newline = chunk.find(b"\n", search_from)
                if newline < 0:
                    break
                next_offset = absolute_offset + newline + 1
                if next_offset < size:
                    offsets.append(next_offset)
                search_from = newline + 1
            absolute_offset += len(chunk)
    return digest.hexdigest(), size, tuple(offsets)


def _prune_runtime_artifacts(
    directory: Path,
    kind: str,
    keep: int = RUNTIME_ARTIFACT_RETENTION,
) -> None:
    root = directory.resolve()
    candidates = sorted(
        directory.glob(f"openspotter_{kind}_*.gcode"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_path in candidates[max(1, int(keep)) :]:
        try:
            if old_path.resolve().parent != root:
                continue
            old_path.unlink()
        except OSError:
            continue
        old_settings = old_path.with_name(f"{old_path.stem}_settings.json")
        try:
            if old_settings.resolve().parent == root:
                old_settings.unlink()
        except OSError:
            pass


def generate_job_artifact(
    snapshot: GenerationSnapshot,
    output_dir: Optional[os.PathLike] = None,
) -> JobArtifact:
    """Generate one exact runtime artifact from a detached snapshot."""
    destination_dir = Path(output_dir or (GCODE_DIR / "runtime"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    path = destination_dir / f"openspotter_{snapshot.kind}_{stamp}_{unique}.gcode"
    adapter = _GenerationAdapter(snapshot)

    if snapshot.kind == "grid":
        generated = save_grid_gcode(adapter, str(path))
    elif snapshot.kind == "spiral":
        generated = save_spiral_gcode(adapter, str(path))
    else:
        raise ValueError(f"Unsupported job kind: {snapshot.kind}")
    if not generated:
        raise ValueError(f"No {snapshot.kind} G-code was generated")
    generated_size = path.stat().st_size
    if generated_size > MAX_RUNTIME_ARTIFACT_BYTES:
        try:
            path.unlink()
        except OSError:
            pass
        settings_candidate = path.with_name(f"{path.stem}_settings.json")
        try:
            settings_candidate.unlink()
        except OSError:
            pass
        raise ValueError(
            f"Generated artifact is {generated_size:,} bytes; the direct-run "
            f"limit is {MAX_RUNTIME_ARTIFACT_BYTES:,} bytes"
        )

    digest, size, line_offsets = _hash_and_line_index(path)
    settings_path = path.with_name(f"{path.stem}_settings.json")
    remote_name = f"{digest}.gcode"
    remote_path = str(
        PurePosixPath("openspotter") / snapshot.kind / remote_name
    )
    artifact = JobArtifact(
        kind=snapshot.kind,
        path=path,
        settings_path=settings_path,
        sha256=digest,
        size=size,
        remote_path=remote_path,
        line_offsets=line_offsets,
    )
    log_options(
        logger,
        "runtime_job.artifact_generated",
        kind=artifact.kind,
        path=artifact.path,
        settings_path=artifact.settings_path,
        sha256=artifact.sha256,
        size=artifact.size,
        remote_path=artifact.remote_path,
        line_count=artifact.line_count,
    )
    _prune_runtime_artifacts(destination_dir, snapshot.kind)
    return artifact


__all__ = [
    "GenerationSnapshot",
    "GridJobSnapshot",
    "JobArtifact",
    "SpiralJobSnapshot",
    "capture_generation_snapshot",
    "generate_job_artifact",
]
