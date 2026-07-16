"""Detached job snapshots and exact runtime G-code artifacts.

Tk widgets are captured on the GUI thread, then converted into small value
adapters so the existing planner and workflow generator can run safely in a
worker thread without touching Tk.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .core.application_patterns import (
    FrozenDict,
    PatternRecipeSnapshot,
    RuntimeGenerationContext,
)
from .core.schema import parse_widget_entries
from .gcode_workflow import load_workflow
from .input_configs import GLOBAL_FIELDS
from .paths import GCODE_DIR, WORKFLOW_CONFIG
from .plugin_runtime import require_application_plugin
from .plugins.grid.runtime import GridJobSnapshot
from .plugins.spiral.runtime import SpiralJobSnapshot
from .runtime_logging import get_logger, log_options


logger = get_logger("machine.runtime_job")

MAX_PATTERN_COUNT = 64
MAX_TOTAL_PATTERN_POINTS = 100_000
MAX_RUNTIME_ARTIFACT_BYTES = 50 * 1024 * 1024
RUNTIME_ARTIFACT_RETENTION = 20


@dataclass(frozen=True, init=False)
class GenerationSnapshot:
    """Detached direct-run state for one selected pattern plugin.

    ``grids`` and ``spirals`` remain compatibility views. New plugins use the
    generic ``recipes`` collection and do not require changes to this class.
    """

    kind: str
    config_dir: str
    global_values: Mapping[str, Any]
    workflow_json: str
    recipes: Tuple[PatternRecipeSnapshot[Any], ...]

    def __init__(
        self,
        kind: str,
        config_dir: str,
        global_values: Mapping[str, Any],
        workflow_json: str,
        grids: Sequence[GridJobSnapshot] = (),
        spirals: Sequence[SpiralJobSnapshot] = (),
        *,
        recipes: Optional[Sequence[PatternRecipeSnapshot[Any]]] = None,
    ):
        """Create a generic snapshot while accepting the legacy arguments."""

        if recipes is not None and (grids or spirals):
            raise ValueError(
                "Pass either generic recipes or legacy grid/spiral snapshots"
            )
        if recipes is None:
            detached_recipes = tuple(
                PatternRecipeSnapshot(
                    plugin_id="grid",
                    number=item.number,
                    payload=item,
                )
                for item in grids
            ) + tuple(
                PatternRecipeSnapshot(
                    plugin_id="spiral",
                    number=item.number,
                    payload=item,
                )
                for item in spirals
            )
        else:
            detached_recipes = tuple(recipes)

        object.__setattr__(self, "kind", str(kind).strip().lower())
        object.__setattr__(self, "config_dir", str(config_dir))
        object.__setattr__(self, "global_values", global_values)
        object.__setattr__(self, "workflow_json", str(workflow_json))
        object.__setattr__(self, "recipes", detached_recipes)

    @property
    def grids(self) -> Tuple[GridJobSnapshot, ...]:
        """Return legacy grid payloads captured in this snapshot."""

        return tuple(
            recipe.payload
            for recipe in self.recipes
            if recipe.plugin_id == "grid"
            and isinstance(recipe.payload, GridJobSnapshot)
        )

    @property
    def spirals(self) -> Tuple[SpiralJobSnapshot, ...]:
        """Return legacy spiral payloads captured in this snapshot."""

        return tuple(
            recipe.payload
            for recipe in self.recipes
            if recipe.plugin_id == "spiral"
            and isinstance(recipe.payload, SpiralJobSnapshot)
        )

    @property
    def runtime_context(self) -> RuntimeGenerationContext:
        """Return the plugin-neutral context used for generation."""

        return RuntimeGenerationContext(
            config_dir=self.config_dir,
            global_values=self.global_values,
            workflow_json=self.workflow_json,
        )


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


def _strict_entries_to_dict(
    entries: Sequence[Any],
    fields: Sequence[Any],
    context: str,
) -> Dict[str, Any]:
    """Strictly capture widget values through the shared field-schema parser."""

    return parse_widget_entries(
        entries,
        fields,
        strict=True,
        context=context,
    )


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


def capture_generation_snapshot(gui: Any, kind: Optional[str] = None) -> GenerationSnapshot:
    """Capture the current GUI inputs. Call this only from the Tk thread."""
    selected_kind = str(kind or gui._current_workspace_mode()).strip().lower()
    if not selected_kind:
        raise ValueError("Job kind must identify a registered pattern plugin")
    try:
        plugin = require_application_plugin(selected_kind)
    except KeyError as exc:
        raise ValueError(
            "Pattern plugin {!r} is unavailable or does not support direct-run "
            "jobs".format(selected_kind)
        ) from exc

    config_dir = str(getattr(gui, "config_dir", WORKFLOW_CONFIG.parent))
    workflow_path = Path(config_dir) / WORKFLOW_CONFIG.name
    workflow = load_workflow(workflow_path)
    global_values = _strict_entries_to_dict(
        gui.entry,
        GLOBAL_FIELDS,
        "Global machine parameters",
    )
    _validate_global(global_values)

    recipes = tuple(
        plugin.capture_runtime_recipes(
            gui,
            FrozenDict(global_values),
            workflow,
        )
    )
    if not recipes:
        raise ValueError(
            "Pattern plugin {!r} did not capture any direct-run recipes".format(
                selected_kind
            )
        )
    for recipe in recipes:
        if not isinstance(recipe, PatternRecipeSnapshot):
            raise TypeError(
                "Pattern plugin {!r} returned an incompatible runtime recipe".format(
                    selected_kind
                )
            )
        if recipe.plugin_id != selected_kind:
            raise ValueError(
                "Pattern plugin {!r} returned a recipe for {!r}".format(
                    selected_kind,
                    recipe.plugin_id,
                )
            )

    total_pattern_points = sum(recipe.estimated_work for recipe in recipes)
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
        recipes=recipes,
    )
    log_options(
        logger,
        "runtime_job.snapshot_captured",
        kind=selected_kind,
        plugin_version=plugin.manifest.version,
        recipe_count=len(recipes),
        estimated_work=total_pattern_points,
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
    try:
        plugin = require_application_plugin(snapshot.kind)
    except KeyError as exc:
        raise ValueError(
            "Pattern plugin {!r} is unavailable or does not support direct-run "
            "jobs".format(snapshot.kind)
        ) from exc
    if not snapshot.recipes:
        raise ValueError(
            "Runtime snapshot for {!r} contains no recipes".format(
                snapshot.kind
            )
        )
    for recipe in snapshot.recipes:
        if recipe.plugin_id != snapshot.kind:
            raise ValueError(
                "Runtime snapshot for {!r} contains a {!r} recipe".format(
                    snapshot.kind,
                    recipe.plugin_id,
                )
            )

    destination_dir = Path(output_dir or (GCODE_DIR / "runtime"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    path = destination_dir / f"openspotter_{snapshot.kind}_{stamp}_{unique}.gcode"

    generated = plugin.generate_runtime(
        snapshot.runtime_context,
        snapshot.recipes,
        str(path),
    )
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
    "PatternRecipeSnapshot",
    "SpiralJobSnapshot",
    "capture_generation_snapshot",
    "generate_job_artifact",
]
