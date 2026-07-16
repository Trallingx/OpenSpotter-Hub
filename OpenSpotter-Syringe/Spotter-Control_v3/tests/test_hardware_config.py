import re
import unittest
from collections import defaultdict
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / "hardware" / "klipper" / "config"
ROOT_CONFIG = CONFIG_DIR / "printer.cfg"

INCLUDE_RE = re.compile(r"^\s*\[include\s+([^\]]+)\]", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")


def resolve_config_graph(root_path):
    ordered_paths = []
    missing_includes = []
    visited = set()

    def visit(config_path):
        config_path = config_path.resolve()
        if config_path in visited:
            return
        visited.add(config_path)
        ordered_paths.append(config_path)

        for line_number, line in enumerate(
            config_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            match = INCLUDE_RE.match(line)
            if match is None:
                continue
            include_path = config_path.parent / match.group(1).strip()
            if not include_path.is_file():
                missing_includes.append(
                    f"{config_path.name}:{line_number}: {match.group(1).strip()}"
                )
                continue
            visit(include_path)

    visit(root_path)
    return ordered_paths, missing_includes


class HardwareConfigGraphTests(unittest.TestCase):
    def test_y_stepper_uses_positive_down_direction_pin(self):
        hardware_text = (CONFIG_DIR / "hardware.cfg").read_text(encoding="utf-8")
        stepper_y = re.search(
            r"(?ms)^\[stepper_y\]\s*$.*?(?=^\[|\Z)",
            hardware_text,
        )

        self.assertIsNotNone(stepper_y)
        self.assertRegex(stepper_y.group(0), r"(?m)^dir_pin:\s*!PL1\s*$")

    def test_needle_offsets_require_positive_down_tcp_coordinate_version(self):
        movement_text = (CONFIG_DIR / "movement_safety.cfg").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            movement_text,
            r"(?m)^variable_required_tcp_coordinate_version:\s*2\s*$",
        )
        self.assertIn("svv.tcp_coordinate_version", movement_text)

    def test_active_include_graph_is_complete_and_has_unique_sections(self):
        config_paths, missing_includes = resolve_config_graph(ROOT_CONFIG)
        self.assertEqual(
            missing_includes,
            [],
            "Missing Klipper include files:\n" + "\n".join(missing_includes),
        )

        definitions = defaultdict(list)
        for config_path in config_paths:
            for line_number, line in enumerate(
                config_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = SECTION_RE.match(line)
                if match is None:
                    continue
                section_name = " ".join(match.group(1).lower().split())
                if section_name.startswith("include "):
                    continue
                definitions[section_name].append(
                    f"{config_path.name}:{line_number}"
                )

        duplicates = {
            section: locations
            for section, locations in definitions.items()
            if len(locations) > 1
        }
        self.assertEqual(
            duplicates,
            {},
            "Duplicate sections in active Klipper config graph:\n"
            + "\n".join(
                f"{section}: {', '.join(locations)}"
                for section, locations in sorted(duplicates.items())
            ),
        )

    def test_removed_legacy_modules_and_undefined_syringe_macros_are_inactive(self):
        config_paths, _ = resolve_config_graph(ROOT_CONFIG)
        active_text = "\n".join(
            config_path.read_text(encoding="utf-8") for config_path in config_paths
        )

        self.assertNotIn("mainsails.cfg", active_text)
        self.assertNotIn("start_end.cfg", active_text)
        self.assertNotRegex(active_text, r"\b(?:SYRINGE_PRIME|RETRACT_SYRINGE)\b")


if __name__ == "__main__":
    unittest.main()
