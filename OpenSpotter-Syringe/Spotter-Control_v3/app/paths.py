"""Resolve immutable application resources and writable runtime directories.

Source checkouts retain the historical layout by default: configuration,
output, and logs stay beside ``main.py``. Installed and frozen applications
use a per-user data directory so they do not attempt to modify site-packages
or a temporary bundle extraction directory.

Environment overrides:

``OPENSPOTTER_MODE``
    ``auto`` (default), ``source``, ``portable``, or ``user``.
``OPENSPOTTER_HOME``
    Explicit writable root. This takes precedence over the selected mode.
``OPENSPOTTER_MIGRATE_FROM``
    Old application root or config directory copied on first run.
``OPENSPOTTER_RESOURCE_ROOT``
    Advanced build/test override for the immutable config/assets root.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple


APP_DIR = Path(__file__).resolve().parent
SOURCE_PROJECT_DIR = APP_DIR.parent

_VALID_MODES = frozenset({"auto", "source", "portable", "user"})
_RESOURCE_MARKERS = (
    Path("config") / "config_global.json",
    Path("assets"),
)

# Keep this explicit so a developer's ignored config_moonraker.json can never
# be included in a package or copied as a fresh-install default by accident.
PACKAGED_CONFIG_FILES = (
    "config_gcode_workflow.json",
    "config_global.json",
    "config_grid_1.json",
    "config_grid_2.json",
    "config_grid_3.json",
    "config_grid_4.json",
    "config_grid_5.json",
    "config_grid_6.json",
    "config_grid_7.json",
    "config_grid_8.json",
    "config_grid_9.json",
    "config_moonraker.example.json",
    "config_spiral_1.json",
    "config_states.json",
    "config_visual_objects.json",
)


@dataclass(frozen=True)
class RuntimeLayout:
    """Resolved resource and writable paths for one application process."""

    mode: str
    resource_dir: Path
    runtime_dir: Path
    config_dir: Path
    assets_dir: Path
    image_dir: Path
    output_dir: Path
    gcode_dir: Path
    log_dir: Path
    migration_config_dir: Optional[Path] = None


def _is_resource_root(candidate: Path) -> bool:
    return all((candidate / marker).exists() for marker in _RESOURCE_MARKERS)


def _resource_candidates() -> Tuple[Path, ...]:
    candidates = [SOURCE_PROJECT_DIR]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.insert(0, Path(bundle_root))
    candidates.extend(
        [
            Path(sys.prefix) / "share" / "openspotter-control",
            Path(sys.prefix) / "openspotter-control",
        ]
    )
    unique = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return tuple(unique)


def resolve_resource_dir(environ: Optional[Mapping[str, str]] = None) -> Path:
    """Locate packaged defaults and assets without depending on the CWD."""
    values = os.environ if environ is None else environ
    override = str(values.get("OPENSPOTTER_RESOURCE_ROOT", "")).strip()
    if override:
        candidate = Path(os.path.expandvars(override)).expanduser().resolve(strict=False)
        if not _is_resource_root(candidate):
            raise RuntimeError(
                "OPENSPOTTER_RESOURCE_ROOT does not contain config defaults and assets: "
                f"{candidate}"
            )
        return candidate

    candidates = _resource_candidates()
    for candidate in candidates:
        if _is_resource_root(candidate):
            return candidate
    rendered = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(
        "OpenSpotter resources could not be located. Checked: " + rendered
    )


def _looks_like_source_checkout(resource_dir: Path) -> bool:
    return (
        (resource_dir / "main.py").is_file()
        and (resource_dir / "pyproject.toml").is_file()
        and (resource_dir / "app" / "paths.py").is_file()
    )


def _default_user_data_dir(
    platform_name: str,
    environ: Mapping[str, str],
    home_dir: Path,
) -> Path:
    if platform_name.startswith("win"):
        base = Path(
            environ.get("LOCALAPPDATA")
            or (home_dir / "AppData" / "Local")
        )
        return base / "OpenSpotter" / "Control"
    if platform_name == "darwin":
        return home_dir / "Library" / "Application Support" / "OpenSpotter" / "Control"
    xdg_data_home = str(environ.get("XDG_DATA_HOME", "")).strip()
    base = Path(xdg_data_home).expanduser() if xdg_data_home else home_dir / ".local" / "share"
    return base / "openspotter-control"


def _normalize_migration_config_dir(value: str) -> Path:
    candidate = Path(os.path.expandvars(value)).expanduser().resolve(strict=False)
    if candidate.name.lower() == "config":
        return candidate
    if (candidate / "config_global.json").is_file():
        return candidate
    return candidate / "config"


def resolve_runtime_layout(
    environ: Optional[Mapping[str, str]] = None,
    *,
    resource_dir: Optional[Path] = None,
    source_checkout: Optional[bool] = None,
    platform_name: Optional[str] = None,
    home_dir: Optional[Path] = None,
    executable_dir: Optional[Path] = None,
) -> RuntimeLayout:
    """Resolve a runtime layout without creating or modifying directories."""
    values = os.environ if environ is None else environ
    resources = Path(resource_dir or resolve_resource_dir(values)).resolve(strict=False)
    detected_source = (
        _looks_like_source_checkout(resources)
        if source_checkout is None
        else bool(source_checkout)
    )

    requested_mode = str(values.get("OPENSPOTTER_MODE", "auto")).strip().lower() or "auto"
    if requested_mode not in _VALID_MODES:
        choices = ", ".join(sorted(_VALID_MODES))
        raise RuntimeError(
            f"Invalid OPENSPOTTER_MODE {requested_mode!r}; expected one of {choices}"
        )

    explicit_home = str(values.get("OPENSPOTTER_HOME", "")).strip()
    if explicit_home:
        mode = "custom"
        runtime_dir = (
            Path(os.path.expandvars(explicit_home))
            .expanduser()
            .resolve(strict=False)
        )
    else:
        mode = requested_mode
        if mode == "auto":
            mode = "source" if detected_source else "user"
        if mode == "source":
            runtime_dir = resources
        elif mode == "portable":
            if executable_dir is not None:
                runtime_dir = Path(executable_dir).resolve(strict=False)
            elif getattr(sys, "frozen", False):
                runtime_dir = Path(sys.executable).resolve().parent
            elif detected_source:
                runtime_dir = resources
            else:
                runtime_dir = Path(sys.argv[0]).resolve(strict=False).parent
        else:
            runtime_dir = _default_user_data_dir(
                platform_name or sys.platform,
                values,
                Path(home_dir or Path.home()).resolve(strict=False),
            ).resolve(strict=False)

    migration_value = str(values.get("OPENSPOTTER_MIGRATE_FROM", "")).strip()
    migration_dir = (
        _normalize_migration_config_dir(migration_value)
        if migration_value
        else None
    )
    config_dir = runtime_dir / "config"
    output_dir = runtime_dir / "output"
    assets_dir = resources / "assets"
    return RuntimeLayout(
        mode=mode,
        resource_dir=resources,
        runtime_dir=runtime_dir,
        config_dir=config_dir,
        assets_dir=assets_dir,
        image_dir=assets_dir / "images",
        output_dir=output_dir,
        gcode_dir=output_dir / "gcodes",
        log_dir=runtime_dir / "logs",
        migration_config_dir=migration_dir,
    )


def _copy_if_missing(source: Path, destination: Path) -> bool:
    """Atomically copy one config file without replacing user state."""
    if not source.is_file() or destination.exists():
        return False
    try:
        if source.resolve(strict=False) == destination.resolve(strict=False):
            return False
    except OSError:
        pass

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        shutil.copy2(str(source), str(temporary_path))
        if destination.exists():
            return False
        os.replace(str(temporary_path), str(destination))
        return True
    finally:
        try:
            temporary_path.unlink()
        except OSError:
            pass


def prepare_runtime_layout(layout: Optional[RuntimeLayout] = None) -> Tuple[Path, ...]:
    """Create writable directories, migrate old config, and seed defaults.

    Existing destination files always win. Explicit migration files are copied
    before packaged defaults, including a local ``config_moonraker.json`` when
    the operator deliberately selected an old application directory.
    """
    active = LAYOUT if layout is None else layout
    for directory in (active.config_dir, active.gcode_dir, active.log_dir):
        directory.mkdir(parents=True, exist_ok=True)

    copied = []
    migration_dir = active.migration_config_dir
    if migration_dir and migration_dir.is_dir():
        for source in sorted(migration_dir.glob("config_*.json")):
            destination = active.config_dir / source.name
            if _copy_if_missing(source, destination):
                copied.append(destination)

    packaged_config_dir = active.resource_dir / "config"
    for filename in PACKAGED_CONFIG_FILES:
        source = packaged_config_dir / filename
        destination = active.config_dir / filename
        if _copy_if_missing(source, destination):
            copied.append(destination)
    return tuple(copied)


RESOURCE_DIR = resolve_resource_dir()
RESOURCE_CONFIG_DIR = RESOURCE_DIR / "config"
LAYOUT = resolve_runtime_layout(resource_dir=RESOURCE_DIR)

# Stable compatibility exports used throughout the existing application.
PROJECT_DIR = RESOURCE_DIR
RUNTIME_DIR = LAYOUT.runtime_dir
PATH_MODE = LAYOUT.mode
CONFIG_DIR = LAYOUT.config_dir
WORKFLOW_CONFIG = CONFIG_DIR / "config_gcode_workflow.json"
VISUAL_OBJECT_CONFIG = CONFIG_DIR / "config_visual_objects.json"
ASSETS_DIR = LAYOUT.assets_dir
IMAGE_DIR = LAYOUT.image_dir
OUTPUT_DIR = LAYOUT.output_dir
GCODE_DIR = LAYOUT.gcode_dir
LOG_DIR = LAYOUT.log_dir


def ensure_runtime_dirs() -> Tuple[Path, ...]:
    """Prepare writable runtime storage and return newly seeded config paths."""
    return prepare_runtime_layout(LAYOUT)
