import json
import re
import shlex
import unittest
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / "hardware" / "klipper" / "config"
ROOT_CONFIG = CONFIG_DIR / "printer.cfg"

INCLUDE_RE = re.compile(r"^\s*\[include\s+([^\]]+)\]", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")
TRADITIONAL_ARGS_RE = re.compile(r"([A-Z_]+|[A-Z*])")


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


def macro_gcode_template(config_text, macro_name):
    section = re.search(
        rf"(?ms)^\[gcode_macro {re.escape(macro_name)}\]\s*$.*?(?=^\[|\Z)",
        config_text,
    )
    if section is None:
        raise AssertionError(f"Missing macro {macro_name}")
    return section.group(0).split("gcode:\n", 1)[1]


def parse_extended_command(command_line):
    tokens = shlex.shlex(command_line, posix=True)
    tokens.whitespace_split = True
    tokens.commenters = "#;"
    command, *arguments = list(tokens)
    return command, {
        key.upper(): value
        for key, value in (argument.split("=", 1) for argument in arguments)
    }


def parse_traditional_command(command_line):
    line = command_line.strip()
    comment_position = line.find(";")
    if comment_position >= 0:
        line = line[:comment_position]
    parts = TRADITIONAL_ARGS_RE.split(line.upper())
    if "".join(parts[:2]) == "N":
        command = "".join(parts[3:5]).strip()
    else:
        command = "".join(parts[:3]).strip()
    params = {
        parts[index]: parts[index + 1].strip()
        for index in range(1, len(parts), 2)
    }
    return command, params


class HardwareConfigGraphTests(unittest.TestCase):
    def test_sensorless_axes_disable_unreliable_second_homing_move(self):
        hardware_text = (CONFIG_DIR / "hardware.cfg").read_text(encoding="utf-8")
        for axis in ("x", "y", "z"):
            section = re.search(
                rf"(?ms)^\[stepper_{axis}\]\s*$.*?(?=^\[|\Z)",
                hardware_text,
            )
            self.assertIsNotNone(section)
            self.assertRegex(
                section.group(0),
                r"(?m)^homing_retract_dist:\s*0\s*$",
            )

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

    def test_active_gcode_templates_compile_with_klipper_delimiters(self):
        config_paths, _ = resolve_config_graph(ROOT_CONFIG)
        environment = Environment("{%", "%}", "{", "}")
        failures = []
        compiled = 0

        for config_path in config_paths:
            config_text = config_path.read_text(encoding="utf-8")
            sections = list(re.finditer(r"(?m)^\s*\[([^\]]+)\]", config_text))
            for index, section in enumerate(sections):
                section_name = section.group(1).strip().lower()
                if not (
                    section_name.startswith("gcode_macro ")
                    or section_name.startswith("delayed_gcode ")
                ):
                    continue
                section_end = (
                    sections[index + 1].start()
                    if index + 1 < len(sections)
                    else len(config_text)
                )
                section_text = config_text[section.end() : section_end]
                gcode = re.search(r"(?m)^gcode:\s*$", section_text)
                if gcode is None:
                    failures.append(
                        f"{config_path.name} [{section.group(1)}]: missing gcode"
                    )
                    continue
                try:
                    environment.from_string(section_text[gcode.end() :])
                    compiled += 1
                except Exception as error:  # pragma: no cover - failure detail
                    failures.append(
                        f"{config_path.name} [{section.group(1)}]: {error}"
                    )

        self.assertGreater(compiled, 0)
        self.assertEqual(
            failures,
            [],
            "Invalid Klipper G-code templates:\n" + "\n".join(failures),
        )

    def test_removed_legacy_modules_and_undefined_syringe_macros_are_inactive(self):
        config_paths, _ = resolve_config_graph(ROOT_CONFIG)
        active_text = "\n".join(
            config_path.read_text(encoding="utf-8") for config_path in config_paths
        )

        self.assertNotIn("mainsails.cfg", active_text)
        self.assertNotIn("start_end.cfg", active_text)
        self.assertNotRegex(active_text, r"\b(?:SYRINGE_PRIME|RETRACT_SYRINGE)\b")

    def test_remote_control_contract_is_immutable_and_jog_is_guarded(self):
        remote_text = (CONFIG_DIR / "remote_control.cfg").read_text(encoding="utf-8")

        contract = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_CONTRACT_V3\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(contract)
        self.assertNotIn("[gcode_macro OPENSPOTTER_CONTRACT_V2]", remote_text)
        self.assertNotIn("variable_contract_version", remote_text)
        self.assertNotIn("SET_GCODE_VARIABLE", contract.group(0))
        self.assertIn("remote contract=v3", remote_text)

        jog = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_JOG\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(jog)
        jog_text = jog.group(0)
        self.assertIn("[gcode_macro OPENSPOTTER_JOG]", remote_text)
        self.assertIn("printer.print_stats.state", jog_text)
        self.assertIn("printer.virtual_sdcard.is_active", jog_text)
        self.assertIn("printer.toolhead.homed_axes", jog_text)
        self.assertIn("requires all XYZ axes to be homed", jog_text)
        self.assertIn(
            "requires needle tip offsets to be disabled",
            jog_text,
        )
        self.assertIn("printer.bed_mesh.profile_name", jog_text)
        self.assertNotIn("printer.bed_mesh.mesh_matrix", jog_text)
        self.assertIn("requires bed mesh compensation to be cleared", jog_text)
        self.assertIn("printer.gcode_move.position", jog_text)
        self.assertIn("printer.gcode_move.gcode_position", jog_text)
        self.assertIn("printer.gcode_move.absolute_coordinates", jog_text)
        self.assertIn("printer.toolhead.axis_minimum", jog_text)
        self.assertIn("printer.toolhead.axis_maximum", jog_text)
        self.assertIn("variable_min_feed: 30.0", jog_text)
        self.assertIn("variable_max_z_feed: 1500.0", jog_text)
        self.assertIn("jog safety limits were modified at runtime", jog_text)
        self.assertIn(
            "not (distance|abs >= 0.000001 and distance|abs <= max_distance)",
            jog_text,
        )
        self.assertIn(
            "not (feed >= cfg.min_feed|float and feed <= max_feed)",
            jog_text,
        )
        self.assertNotRegex(jog_text, r"(?m)^\s*G9[01]\s*$")
        self.assertIn("_CHECK_MOVE_SAFETY", jog_text)
        self.assertIn("SAVE_GCODE_STATE NAME=_openspotter_jog_state", jog_text)
        self.assertRegex(
            jog_text,
            r"(?m)^\s*G0\.1 X\{gcode_position\.x\|float \+ distance if absolute else distance\} F\{feed\}\s*$",
        )
        self.assertRegex(
            jog_text,
            r"(?m)^\s*G0\.1 Y\{gcode_position\.y\|float \+ distance if absolute else distance\} F\{feed\}\s*$",
        )
        self.assertRegex(
            jog_text,
            r"(?m)^\s*G0\.1 Z\{gcode_position\.z\|float \+ distance if absolute else distance\} F\{feed\}\s*$",
        )
        self.assertIn("RESTORE_GCODE_STATE NAME=_openspotter_jog_state", jog_text)
        self.assertLess(
            jog_text.index("_CHECK_MOVE_SAFETY"),
            jog_text.index("SAVE_GCODE_STATE NAME=_openspotter_jog_state"),
        )
        self.assertLess(
            jog_text.index("SAVE_GCODE_STATE NAME=_openspotter_jog_state"),
            jog_text.index("G0.1 X{"),
        )
        self.assertLess(jog_text.index("G0.1 X{"), jog_text.index("M400"))
        self.assertLess(
            jog_text.index("M400"),
            jog_text.index("RESTORE_GCODE_STATE NAME=_openspotter_jog_state"),
        )

    def test_manual_and_job_homing_use_reviewed_sensorless_sequences(self):
        remote_text = (CONFIG_DIR / "remote_control.cfg").read_text(encoding="utf-8")

        home = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_HOME\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(home)
        home_text = home.group(0)
        self.assertIn("printer.virtual_sdcard.is_active", home_text)
        self.assertIn(
            "print_state in ['printing', 'paused'] or virtual_sd_active",
            home_text,
        )
        self.assertLess(
            home_text.index("_OPENSPOTTER_VALIDATE_SENSORLESS_HOME"),
            home_text.index("_OPENSPOTTER_HOME_SEQUENCE"),
        )

        validator = re.search(
            r"(?ms)^\[gcode_macro _OPENSPOTTER_VALIDATE_SENSORLESS_HOME\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(validator)
        validator_text = validator.group(0)
        for axis in ("x", "y", "z"):
            self.assertIn(
                f"printer.configfile.settings['stepper_{axis}']",
                validator_text,
            )
        self.assertIn("homing_retract_dist=0 on X, Y, and Z", validator_text)
        self.assertIn("{% set commissioned_z_home_sgt = 10 %}", validator_text)
        self.assertIn(
            "printer.configfile.settings['tmc2130 stepper_z']",
            validator_text,
        )
        self.assertIn(
            "tmc_z.driver_sgt|int != commissioned_z_home_sgt",
            validator_text,
        )

        z_sgt = re.search(
            r"(?ms)^\[gcode_macro _OPENSPOTTER_SET_Z_HOME_SGT\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(z_sgt)
        self.assertIn(
            "printer.configfile.settings['tmc2130 stepper_z'].driver_sgt",
            z_sgt.group(0),
        )
        self.assertIn(
            "SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE={z_home_sgt}",
            z_sgt.group(0),
        )

        tmc_text = (CONFIG_DIR / "tmc2130.cfg").read_text(encoding="utf-8")
        tmc_z = re.search(
            r"(?ms)^\[tmc2130 stepper_z\]\s*$.*?(?=^\[|\Z)",
            tmc_text,
        )
        self.assertIsNotNone(tmc_z)
        self.assertRegex(tmc_z.group(0), r"(?m)^driver_SGT:\s*10\s*$")

        sequence = re.search(
            r"(?ms)^\[gcode_macro _OPENSPOTTER_HOME_SEQUENCE\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(sequence)
        sequence_text = sequence.group(0)
        self.assertNotRegex(sequence_text, r"(?m)^\s*G9[01]\s*$")
        self.assertNotIn("variable_settle_ms", sequence_text)
        self.assertNotIn("variable_release_distance", sequence_text)
        self.assertIn("{% set commissioned_clearance_z = 35.0 %}", sequence_text)
        self.assertIn("printer.save_variables.variables.movement_dead_zones", sequence_text)
        self.assertIn("zone.enabled|default(1)|int(none)", sequence_text)
        self.assertIn("zone_enabled == 1", sequence_text)
        self.assertIn(
            "zone_clearance > required_clearance.value",
            sequence_text,
        )
        self.assertIn("homing blocked by invalid saved dead zone", sequence_text)
        self.assertIn("clearance_z >= required_clearance.value", sequence_text)
        self.assertIn("commissioned minimum 35 mm", sequence_text)
        self.assertEqual(sequence_text.count("G4 P{settle_ms}"), 3)
        self.assertLess(
            sequence_text.index("_OPENSPOTTER_SET_Z_HOME_SGT"),
            sequence_text.index("G28 Z0"),
        )
        self.assertLess(sequence_text.index("BED_MESH_CLEAR"), sequence_text.index("G28 Z0"))
        self.assertLess(sequence_text.index("G28 Z0"), sequence_text.index("AXIS=Z"))
        self.assertLess(sequence_text.index("AXIS=Z"), sequence_text.index("G28 Y0"))
        self.assertLess(sequence_text.index("G28 Y0"), sequence_text.index("AXIS=Y"))
        self.assertLess(
            sequence_text.index("AXIS=Y"),
            sequence_text.index("_OPENSPOTTER_MOVE_PHYSICAL_Z"),
        )
        self.assertLess(
            sequence_text.index("_OPENSPOTTER_MOVE_PHYSICAL_Z"),
            sequence_text.index("G28 X0"),
        )
        self.assertLess(sequence_text.index("G28 X0"), sequence_text.index("AXIS=X"))
        self.assertLess(sequence_text.index("AXIS=X"), sequence_text.rindex("M400"))

        release = re.search(
            r"(?ms)^\[gcode_macro _OPENSPOTTER_RELEASE_AXIS\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(release)
        release_text = release.group(0)
        self.assertNotRegex(release_text, r"(?m)^\s*G9[01]\s*$")
        self.assertLess(
            release_text.index("_CHECK_MOVE_SAFETY"),
            release_text.index("SAVE_GCODE_STATE"),
        )
        self.assertLess(release_text.index("SAVE_GCODE_STATE"), release_text.index("G0.1 X{"))
        self.assertLess(release_text.index("G0.1 X{"), release_text.index("M400"))
        self.assertLess(release_text.index("M400"), release_text.index("RESTORE_GCODE_STATE"))

        job_home = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_JOB_HOME\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(job_home)
        self.assertIn(
            "not virtual_sd_active or print_state != 'printing'",
            job_home.group(0),
        )
        self.assertIn("_OPENSPOTTER_VALIDATE_SENSORLESS_HOME", job_home.group(0))
        self.assertIn("_OPENSPOTTER_HOME_SEQUENCE", job_home.group(0))

        job_rehome = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_JOB_REHOME_Z\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(job_rehome)
        self.assertIn(
            "not virtual_sd_active or print_state != 'printing'",
            job_rehome.group(0),
        )
        self.assertIn("_OPENSPOTTER_VALIDATE_SENSORLESS_HOME", job_rehome.group(0))
        self.assertIn("_OPENSPOTTER_JOB_REHOME_Z_SEQUENCE", job_rehome.group(0))

        rehome_sequence = re.search(
            r"(?ms)^\[gcode_macro _OPENSPOTTER_JOB_REHOME_Z_SEQUENCE\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(rehome_sequence)
        rehome_text = rehome_sequence.group(0)
        self.assertEqual(rehome_text.count("G4 P{settle_ms}"), 2)
        self.assertEqual(len(re.findall(r"(?m)^\s*G28 Z0\s*$", rehome_text)), 2)
        self.assertEqual(rehome_text.count("_OPENSPOTTER_RELEASE_AXIS AXIS=Z"), 2)
        self.assertEqual(rehome_text.count("_OPENSPOTTER_SET_Z_HOME_SGT"), 2)
        set_sgt_positions = [
            match.start()
            for match in re.finditer("_OPENSPOTTER_SET_Z_HOME_SGT", rehome_text)
        ]
        z_home_positions = [
            match.start() for match in re.finditer(r"(?m)^\s*G28 Z0\s*$", rehome_text)
        ]
        self.assertTrue(
            all(set_sgt < z_home for set_sgt, z_home in zip(set_sgt_positions, z_home_positions))
        )
        self.assertLess(rehome_text.index("BED_MESH_CLEAR"), rehome_text.index("G28 Z0"))
        self.assertLess(
            rehome_text.rindex("_OPENSPOTTER_RELEASE_AXIS AXIS=Z"),
            rehome_text.rindex("M400"),
        )

    def test_default_workflow_routes_all_homing_through_job_macros(self):
        workflow = json.loads(
            (PROJECT_DIR / "config" / "config_gcode_workflow.json").read_text(
                encoding="utf-8"
            )
        )
        start_block = next(
            block for block in workflow["blocks"] if block["role"] == "start"
        )
        start_section = next(
            section
            for section in start_block["sections"]
            if section["trigger"] == "job_start"
        )
        template = start_section["template"]
        x_clearance = next(
            variable
            for variable in workflow["custom_variables"]
            if variable["name"] == "x_homing_clearance_z"
        )

        self.assertIn("OPENSPOTTER_JOB_HOME", template)
        self.assertIn("OPENSPOTTER_JOB_REHOME_Z", template)
        self.assertGreaterEqual(float(x_clearance["value"]), 35.0)
        self.assertIn(
            "X_CLEARANCE_Z={{custom.x_homing_clearance_z}}",
            template,
        )
        self.assertNotRegex(template, r"(?m)^\s*G28(?:\s|$)")
        self.assertNotIn("SET_TMC_FIELD", template)
        self.assertNotIn("FIELD=SGT", template)
        self.assertLess(
            template.index("OPENSPOTTER_JOB_HOME"),
            template.index("G0 Z{{global.probe_ram_height}}"),
        )
        self.assertLess(
            template.index("G0 Z{{global.probe_return_height}}"),
            template.index("OPENSPOTTER_JOB_REHOME_Z"),
        )

    def test_cleanup_clears_all_motion_transforms_and_cancel_uses_it(self):
        remote_text = (CONFIG_DIR / "remote_control.cfg").read_text(encoding="utf-8")
        mainsail_text = (CONFIG_DIR / "mainsail.cfg").read_text(encoding="utf-8")

        cleanup = re.search(
            r"(?ms)^\[gcode_macro OPENSPOTTER_JOB_CLEANUP\]\s*$.*?(?=^\[|\Z)",
            remote_text,
        )
        self.assertIsNotNone(cleanup)
        self.assertIn("NEEDLE_TIP_OFFSETS_DISABLE", cleanup.group(0))
        self.assertIn("BED_MESH_CLEAR", cleanup.group(0))
        self.assertIn("_OPENSPOTTER_SET_Z_HOME_SGT", cleanup.group(0))
        self.assertNotRegex(cleanup.group(0), r"(?m)^\s*G[01](?:\s|$)")

        cancel = re.search(
            r"(?ms)^\[gcode_macro CANCEL_PRINT\]\s*$.*?(?=^\[|\Z)",
            mainsail_text,
        )
        self.assertIsNotNone(cancel)
        self.assertLess(
            cancel.group(0).index("OPENSPOTTER_JOB_CLEANUP"),
            cancel.group(0).rindex("CANCEL_PRINT_BASE"),
        )

    def test_dead_zone_guard_converts_logical_targets_to_physical_frame(self):
        safety_text = (CONFIG_DIR / "movement_safety.cfg").read_text(
            encoding="utf-8"
        )
        setter = re.search(
            r"(?ms)^\[gcode_macro SET_DEAD_ZONE\]\s*$.*?(?=^\[|\Z)",
            safety_text,
        )
        self.assertIsNotNone(setter)
        setter_text = setter.group(0)
        self.assertIn("printer.toolhead.axis_minimum", setter_text)
        self.assertIn("printer.toolhead.axis_maximum", setter_text)
        self.assertIn("x_min <= x_max", setter_text)
        self.assertIn("y_min <= y_max", setter_text)
        self.assertIn("X_MIN|default(existing.x_min)|float(none)", setter_text)
        self.assertIn("Z_CLEARANCE must be finite", setter_text)
        self.assertIn("ALLOW_* values must be 0 or 1", setter_text)

        guard = re.search(
            r"(?ms)^\[gcode_macro _CHECK_MOVE_SAFETY\]\s*$.*?(?=^\[|\Z)",
            safety_text,
        )
        self.assertIsNotNone(guard)
        guard_text = guard.group(0)

        self.assertIn("printer.gcode_move.position", guard_text)
        self.assertIn("printer.gcode_move.gcode_position", guard_text)
        self.assertNotIn("printer.toolhead.position", guard_text)
        for axis in ("x", "y", "z"):
            self.assertIn(
                f"requested_{axis} + (pos.{axis}|float - gcode_pos.{axis}|float)",
                guard_text,
            )
            self.assertIn(
                f"pos.{axis}|float + requested_{axis}",
                guard_text,
            )
        self.assertIn("params.X|float(none)", guard_text)
        self.assertIn("G0/G1 XYZ/F parameters must be numeric", guard_text)
        self.assertIn("G0/G1 E moves are unsupported", guard_text)
        self.assertIn("configured_max_feed", guard_text)
        self.assertIn("G0/G1 X target must be finite", guard_text)
        self.assertIn("G0/G1 feed must be finite", guard_text)
        self.assertIn("Saved movement safety state is invalid", guard_text)
        self.assertIn("Invalid saved dead zone", guard_text)
        self.assertIn("exiting_zone and tz >= sz and allow_exit == 1", guard_text)
        self.assertIn("xy_inside and tz >= sz and allow_xy_inside == 1", guard_text)

    def test_g0_g1_wrappers_emit_valid_extended_macro_parameters(self):
        safety_text = (CONFIG_DIR / "movement_safety.cfg").read_text(
            encoding="utf-8"
        )
        environment = Environment("{%", "%}", "{", "}")

        def raise_error(message):
            raise ValueError(message)

        def render_wrapper(name, params):
            template = environment.from_string(
                macro_gcode_template(safety_text, name)
            )
            return template.render(
                params=params,
                action_raise_error=raise_error,
            )

        for command_line, expected_base in (
            ("G0 X10 F600", "G0.1"),
            ("N7 G1 Y-5.5 Z2 F300", "G1.1"),
        ):
            name, params = parse_traditional_command(command_line)
            rendered_lines = [
                line.strip()
                for line in render_wrapper(name, params).splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rendered_lines), 1)
            command, parsed = parse_extended_command(rendered_lines[0])
            self.assertEqual(command, "_NEEDLE_CORRECTED_MOVE")
            self.assertEqual(parsed["BASE"], expected_base)
            for key, value in params.items():
                if key in {"X", "Y", "Z", "F"}:
                    self.assertEqual(parsed[key], value)

        self.assertNotIn("{rawparams}", macro_gcode_template(safety_text, "G0"))
        self.assertNotIn("{rawparams}", macro_gcode_template(safety_text, "G1"))
        with self.assertRaisesRegex(ValueError, "does not support parameter Q"):
            render_wrapper("G0", {"G": "0", "Q": "1"})
        scientific_name, scientific_params = parse_traditional_command(
            "G0 X1e2 F600"
        )
        self.assertIn("E", scientific_params)
        with self.assertRaisesRegex(ValueError, "does not support parameter E"):
            render_wrapper(scientific_name, scientific_params)

        corrected_template = environment.from_string(
            macro_gcode_template(safety_text, "_NEEDLE_CORRECTED_MOVE")
        )
        printer = {
            "gcode_macro _NEEDLE_TIP_OFFSETS": {
                "enabled": 0,
                "require_tcp_ready": 1,
                "required_tcp_coordinate_version": 2,
                "surface_z": 0.0,
            },
            "save_variables": {"variables": {}},
            "gcode_move": {"absolute_coordinates": True},
        }
        corrected_lines = [
            line.strip()
            for line in corrected_template.render(
                params={"BASE": "G0.1", "X": "10", "F": "600"},
                printer=printer,
                action_raise_error=raise_error,
            ).splitlines()
            if line.strip()
        ]
        self.assertEqual(len(corrected_lines), 2)
        guard_command, guard_params = parse_extended_command(corrected_lines[0])
        self.assertEqual(guard_command, "_CHECK_MOVE_SAFETY")
        self.assertEqual(guard_params, {"X": "10.0", "F": "600.0"})
        raw_command, raw_params = parse_traditional_command(corrected_lines[1])
        self.assertEqual(raw_command, "G0.1")
        self.assertEqual(raw_params["X"], "10.0")
        self.assertEqual(raw_params["F"], "600.0")

    def test_live_z_macro_validates_then_moves_then_commits_offset(self):
        safety_text = (CONFIG_DIR / "movement_safety.cfg").read_text(
            encoding="utf-8"
        )
        live_z = re.search(
            r"(?ms)^\[gcode_macro SET_NEEDLE_SURFACE_OFFSET\]\s*$.*?(?=^\[|\Z)",
            safety_text,
        )
        self.assertIsNotNone(live_z)
        macro_text = live_z.group(0)

        self.assertIn(
            "not (new_z >= min_z and new_z <= max_z)",
            macro_text,
        )
        self.assertIn(
            "not (feed >= 1.0 and feed <= 1500.0)",
            macro_text,
        )
        self.assertIn("printer.toolhead.axis_minimum", macro_text)
        self.assertIn("printer.toolhead.axis_maximum", macro_text)
        self.assertNotRegex(macro_text, r"(?m)^\s*G9[01]\s*$")
        self.assertLess(
            macro_text.index("_CHECK_MOVE_SAFETY Z="),
            macro_text.index("SAVE_GCODE_STATE NAME=_needle_surface_offset_live"),
        )
        self.assertIn(
            "G0.1 Z{gcode_position.z|float + delta if absolute else delta}",
            macro_text,
        )
        self.assertLess(macro_text.index("G0.1 Z{"), macro_text.index("M400"))
        self.assertLess(
            macro_text.index("RESTORE_GCODE_STATE NAME=_needle_surface_offset_live"),
            macro_text.index(
                "SET_GCODE_VARIABLE MACRO=_NEEDLE_TIP_OFFSETS VARIABLE=surface_z"
            ),
        )

    def test_moonraker_sample_does_not_trust_entire_private_networks(self):
        moonraker_text = (CONFIG_DIR / "moonraker.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("127.0.0.0/8", moonraker_text)
        self.assertIn("::1/128", moonraker_text)
        self.assertNotIn("10.0.0.0/8", moonraker_text)
        self.assertNotIn("172.16.0.0/12", moonraker_text)
        self.assertNotIn("192.168.0.0/16", moonraker_text)
        self.assertIn("exact control workstation", moonraker_text)


if __name__ == "__main__":
    unittest.main()
