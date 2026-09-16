"""Static checks for the core, plugin, and compatibility dependency rules."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"

LEGACY_MODULES = frozenset(
    (
        "app.SpotterFunctions",
        "app.gcode_planner",
        "app.grid",
        "app.grid_gcode",
        "app.spiral_gcode",
        "app.spiral_grid",
    )
)
CONCRETE_PATTERN_MODULES = frozenset(
    (
        "app.plugins.grid",
        "app.plugins.spiral",
    )
)
SHELL_MODULE_PREFIXES = (
    "app.canvas_drawer",
    "app.gui_v3",
    "app.machine",
    "app.machine_controller",
    "app.runtime_job",
)
PURE_PLUGIN_MODULES = frozenset(
    (
        "fields.py",
        "geometry.py",
        "manifest.py",
        "planner.py",
        "workflow.py",
    )
)
GENERIC_SHELL_FILES = (
    "canvas_drawer.py",
    "gcode_editor.py",
    "gcode_generation.py",
    "gui_v3.py",
    "machine_controller.py",
    "main_v3.py",
    "plugin_runtime.py",
)


def _module_name(path: Path) -> str:
    relative = path.relative_to(PROJECT_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_import(
    current_module: str,
    current_path: Path,
    level: int,
    imported_module: str,
) -> str:
    if level == 0:
        return imported_module

    package_parts = current_module.split(".")
    if current_path.name != "__init__.py":
        package_parts.pop()
    parent_count = level - 1
    if parent_count:
        package_parts = package_parts[:-parent_count]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts)


def _application_imports(path: Path) -> Iterable[Tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current_module = _module_name(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            yield (
                node.lineno,
                _resolve_import(
                    current_module,
                    path,
                    node.level,
                    node.module or "",
                ),
            )


def _matches_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in prefixes
    )


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_generic_shells_do_not_import_concrete_or_legacy_patterns(self):
        violations = []
        for filename in GENERIC_SHELL_FILES:
            path = APP_ROOT / filename
            for line_number, imported_module in _application_imports(path):
                if (
                    _matches_prefix(
                        imported_module,
                        CONCRETE_PATTERN_MODULES,
                    )
                    or imported_module in LEGACY_MODULES
                ):
                    violations.append(
                        "{}:{} imports {}".format(
                            path.relative_to(PROJECT_ROOT),
                            line_number,
                            imported_module,
                        )
                    )
        self.assertEqual([], violations, "\n".join(violations))

    def test_core_never_imports_concrete_patterns_or_shell_modules(self):
        violations = []
        for path in sorted((APP_ROOT / "core").rglob("*.py")):
            for line_number, imported_module in _application_imports(path):
                is_non_ui_tk_import = (
                    imported_module == "tkinter"
                    or imported_module.startswith("tkinter.")
                ) and "ui" not in path.relative_to(APP_ROOT / "core").parts
                if (
                    _matches_prefix(
                        imported_module,
                        CONCRETE_PATTERN_MODULES,
                    )
                    or _matches_prefix(imported_module, SHELL_MODULE_PREFIXES)
                    or imported_module in LEGACY_MODULES
                    or is_non_ui_tk_import
                ):
                    violations.append(
                        "{}:{} imports {}".format(
                            path.relative_to(PROJECT_ROOT),
                            line_number,
                            imported_module,
                        )
                    )
        self.assertEqual([], violations, "\n".join(violations))

    def test_pure_plugin_layers_do_not_use_shell_or_legacy_facades(self):
        violations = []
        for plugin_directory in sorted((APP_ROOT / "plugins").iterdir()):
            if not plugin_directory.is_dir():
                continue
            plugin_prefix = "app.plugins.{}".format(plugin_directory.name)
            for path in sorted(plugin_directory.glob("*.py")):
                if path.name not in PURE_PLUGIN_MODULES:
                    continue
                for line_number, imported_module in _application_imports(path):
                    crosses_application_boundary = (
                        imported_module.startswith("app.")
                        and not _matches_prefix(
                            imported_module,
                            ("app.core", plugin_prefix),
                        )
                    )
                    if (
                        imported_module == "tkinter"
                        or imported_module.startswith("tkinter.")
                        or imported_module in LEGACY_MODULES
                        or _matches_prefix(
                            imported_module,
                            SHELL_MODULE_PREFIXES,
                        )
                        or crosses_application_boundary
                    ):
                        violations.append(
                            "{}:{} imports {}".format(
                                path.relative_to(PROJECT_ROOT),
                                line_number,
                                imported_module,
                            )
                        )
        self.assertEqual([], violations, "\n".join(violations))

    def test_legacy_facades_contain_exports_not_duplicate_implementations(self):
        violations = []
        for module_name in sorted(LEGACY_MODULES):
            path = PROJECT_ROOT.joinpath(*module_name.split(".")).with_suffix(
                ".py"
            )
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for index, node in enumerate(tree.body):
                if (
                    index == 0
                    and isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    continue
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = (
                        node.targets
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                    if all(
                        isinstance(target, ast.Name)
                        and target.id == "__all__"
                        for target in targets
                    ):
                        continue
                violations.append(
                    "{}:{} contains executable {}".format(
                        path.relative_to(PROJECT_ROOT),
                        node.lineno,
                        type(node).__name__,
                    )
                )
        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
