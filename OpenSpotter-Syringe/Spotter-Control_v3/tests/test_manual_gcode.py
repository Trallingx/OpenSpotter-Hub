import dataclasses
import unittest

from app.manual_gcode import (
    CATEGORY_EMERGENCY,
    CATEGORY_FIRMWARE,
    CATEGORY_HEATER,
    CATEGORY_HOMING,
    CATEGORY_MOTION,
    CATEGORY_OTHER,
    CATEGORY_STATE,
    CATEGORY_UNKNOWN_MACRO,
    MAX_MANUAL_GCODE_BYTES,
    MAX_MANUAL_GCODE_COMMANDS,
    MAX_MANUAL_GCODE_LINES,
    ManualGcodeValidationError,
    parse_manual_gcode,
)


class ManualGcodeParserTests(unittest.TestCase):
    def test_normalizes_newlines_preserves_script_and_ignores_comments(self):
        source = (
            "; operator note\r\n"
            "  g01X1.5 Y2 ; inline note\r\n"
            "\r\n"
            "# UI-only comment\r"
            "M117 Prøve\r"
        )

        result = parse_manual_gcode(source)

        self.assertEqual(
            result.normalized_script,
            (
                "; operator note\n"
                "  g01X1.5 Y2 ; inline note\n"
                "\n"
                "; UI-only comment\n"
                "M117 Prøve\n"
            ),
        )
        self.assertEqual(
            [(command.line_number, command.name) for command in result.commands],
            [(2, "G1"), (5, "M117")],
        )
        self.assertEqual(result.commands[0].text, "g01X1.5 Y2")
        self.assertEqual(result.commands[1].text, "M117 Prøve")
        self.assertEqual(
            [command.category for command in result.commands],
            [CATEGORY_MOTION, CATEGORY_OTHER],
        )
        self.assertEqual(result.blocked_reasons, ())

    def test_classifies_all_confirmation_categories_and_unknown_macros(self):
        result = parse_manual_gcode(
            "\n".join(
                (
                    "G1 X10",
                    "G28",
                    "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=40",
                    "SET_GCODE_OFFSET Z=0.1",
                    "M3 S100",
                    "FIRMWARE_RESTART",
                    "SHUTDOWN",
                    "M112",
                    "MY_CUSTOM_MACRO VALUE=1",
                )
            )
        )

        self.assertEqual(
            [command.category for command in result.commands],
            [
                CATEGORY_MOTION,
                CATEGORY_HOMING,
                CATEGORY_HEATER,
                CATEGORY_STATE,
                CATEGORY_STATE,
                CATEGORY_FIRMWARE,
                CATEGORY_FIRMWARE,
                CATEGORY_EMERGENCY,
                CATEGORY_UNKNOWN_MACRO,
            ],
        )
        self.assertEqual(len(result.warnings), len(result.commands))
        self.assertTrue(result.requires_confirmation)
        self.assertTrue(result.is_blocked)
        self.assertIn("unknown macro 'MY_CUSTOM_MACRO'", result.warnings[-1])
        self.assertIn("emergency stop must be the only", result.blocked_reasons[-2])
        self.assertIn("BLOCKED", result.summary)
        self.assertIn("confirmation cannot override", result.summary)

    def test_informational_commands_do_not_require_confirmation(self):
        result = parse_manual_gcode(
            "G4 P100\nM105\nM114\nRESPOND MSG=*42\n"
        )

        self.assertEqual(
            [command.name for command in result.commands],
            ["G4", "M105", "M114", "RESPOND"],
        )
        self.assertEqual(
            [command.category for command in result.commands],
            [CATEGORY_OTHER] * 4,
        )
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.blocked_reasons, ())
        self.assertIn("RESPOND MSG=*42", result.normalized_script)
        self.assertFalse(result.is_blocked)
        self.assertFalse(result.requires_confirmation)
        self.assertIn("no confirmation warnings", result.summary)

    def test_parse_result_and_nested_commands_are_immutable(self):
        result = parse_manual_gcode("G1 X1")

        self.assertIsInstance(result.commands, tuple)
        self.assertIsInstance(result.warnings, tuple)
        self.assertIsInstance(result.blocked_reasons, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.summary = "changed"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.commands[0].name = "M105"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.commands[0].blocked_reason = "changed"

    def test_empty_and_comment_only_scripts_have_no_commands(self):
        result = parse_manual_gcode(
            " \n; note\n# note\n(parenthetical note) ; trailing note\n"
        )

        self.assertEqual(result.commands, ())
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.blocked_reasons, ())
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(result.summary, "No executable commands.")

    def test_rejects_nul_and_forbidden_control_characters(self):
        for source, expected in (
            ("G1 X1\x00", "NUL"),
            ("G1 X1\x1b", "U+001B"),
            ("M117 ok\x7f", "U+007F"),
            ("M117 hidden\u202e", "U+202E"),
        ):
            with self.subTest(source=repr(source)):
                with self.assertRaises(ManualGcodeValidationError) as raised:
                    parse_manual_gcode(source)
                self.assertIn(expected, str(raised.exception))

        result = parse_manual_gcode("\tM105\r\n")
        self.assertEqual(result.commands[0].name, "M105")

    def test_rejects_excessive_byte_size_and_line_count(self):
        self.assertEqual(MAX_MANUAL_GCODE_BYTES, 16 * 1024)
        self.assertEqual(MAX_MANUAL_GCODE_LINES, 100)
        self.assertEqual(MAX_MANUAL_GCODE_COMMANDS, 50)

        with self.assertRaises(ManualGcodeValidationError) as raised:
            parse_manual_gcode("A" * (MAX_MANUAL_GCODE_BYTES + 1))
        self.assertIn("byte safety limit", str(raised.exception))

        oversized_lines = "\n".join(
            "M105" for _ in range(MAX_MANUAL_GCODE_LINES + 1)
        )
        with self.assertRaises(ManualGcodeValidationError) as raised:
            parse_manual_gcode(oversized_lines)
        self.assertIn("line safety limit", str(raised.exception))

        oversized_commands = "\n".join(
            "M105" for _ in range(MAX_MANUAL_GCODE_COMMANDS + 1)
        )
        with self.assertRaises(ManualGcodeValidationError) as raised:
            parse_manual_gcode(oversized_commands)
        self.assertIn("command safety limit", str(raised.exception))

    def test_rejects_lines_without_a_command_name(self):
        with self.assertRaises(ManualGcodeValidationError) as raised:
            parse_manual_gcode("M105\n@shell-command\n")

        self.assertIn("Line 2", str(raised.exception))
        self.assertIn("valid G-code", str(raised.exception))

    def test_canonicalizes_standard_command_names_without_changing_script(self):
        source = "g0001X1\nG00.1 X2\nM104S40\n"
        result = parse_manual_gcode(source)

        self.assertEqual(result.normalized_script, source)
        self.assertEqual(
            [command.name for command in result.commands],
            ["G1", "G0.1", "M104"],
        )
        self.assertEqual(
            [command.category for command in result.commands],
            [
                CATEGORY_MOTION,
                CATEGORY_MOTION,
                CATEGORY_HEATER,
            ],
        )
        self.assertIsNone(result.commands[0].blocked_reason)
        self.assertIn("raw motion", result.commands[1].blocked_reason)
        self.assertIn("restricted manual-command", result.commands[2].blocked_reason)

    def test_transport_framing_cannot_hide_emergency_stop(self):
        result = parse_manual_gcode("N123 M112*45\r\n")

        self.assertEqual(result.normalized_script, "M112\n")
        self.assertEqual(result.commands[0].name, "M112")
        self.assertEqual(result.commands[0].category, CATEGORY_EMERGENCY)
        self.assertIsNone(result.commands[0].blocked_reason)
        self.assertFalse(result.is_blocked)

        emergency_macro = parse_manual_gcode("EMERGENCY_STOP\n")
        self.assertEqual(
            emergency_macro.commands[0].category,
            CATEGORY_EMERGENCY,
        )
        self.assertFalse(emergency_macro.is_blocked)

        compact = parse_manual_gcode("N7M112*9\n")
        self.assertEqual(compact.normalized_script, "M112\n")
        self.assertEqual(compact.commands[0].category, CATEGORY_EMERGENCY)

        framed_comment = parse_manual_gcode("N8 # controller note*4\n")
        self.assertEqual(
            framed_comment.normalized_script,
            "; controller note\n",
        )
        self.assertEqual(framed_comment.commands, ())

        mixed = parse_manual_gcode("N1 M112*0\nM105\n")
        self.assertTrue(mixed.is_blocked)
        self.assertIn(
            "emergency stop must be the only executable command",
            mixed.commands[0].blocked_reason,
        )
        self.assertIn("BLOCKED", mixed.summary)

    def test_unsafe_bypasses_and_unknown_commands_are_blocked(self):
        blocked_scripts = (
            "G0.1 X1",
            "G1.1 X1",
            "G2 X1 Y1 I0 J1",
            "G3 X1 Y1 I0 J1",
            "G5 X1 Y1",
            "G28",
            "G92 X0",
            "FORCE_MOVE STEPPER=stepper_x DISTANCE=1",
            "SET_KINEMATIC_POSITION X=0",
            "MANUAL_STEPPER STEPPER=test MOVE=1",
            "MOVEMENT_SAFETY_DISABLE",
            "SET_STEPPER_ENABLE STEPPER=stepper_x ENABLE=0",
            "SET_TMC_FIELD STEPPER=stepper_x FIELD=toff VALUE=0",
            "SET_TMC_CURRENT STEPPER=stepper_x CURRENT=2",
            "SET_TMC_HOLDCURRENT STEPPER=stepper_x HOLDCURRENT=2",
            "SET_GCODE_VARIABLE MACRO=test VARIABLE=value VALUE=1",
            "SET_GCODE_OFFSET Z=0",
            "SET_PIN PIN=x13_switch VALUE=1",
            "SET_SERVO SERVO=test ANGLE=90",
            "CLEAR_DEAD_ZONES",
            "REMOVE_DEAD_ZONE INDEX=0",
            "SET_DEAD_ZONE X_MIN=0 X_MAX=1 Y_MIN=0 Y_MAX=1",
            "_OPENSPOTTER_RUNTIME",
            "OPENSPOTTER_SET_PROMPT PROMPT=20",
            "OPENSPOTTER_JOB_CLEANUP",
            "NEEDLE_TIP_OFFSETS_ENABLE REQUIRE_TCP=0",
            "NEEDLE_TIP_OFFSETS_ENABLE REQUIRE_TCP=1",
            "NEEDLE_TIP_OFFSETS_DISABLE",
            "BED_MESH_PROFILE LOAD=default",
            "BED_MESH_CLEAR",
            "SET_NEEDLE_SURFACE_OFFSET Z=0.1",
            "ADJUST_NEEDLE_SURFACE_OFFSET Z_ADJUST=0.01 MOVE=1",
            "RESET_NEEDLE_SURFACE_OFFSET MOVE=1",
            "HOME_SYRINGE",
            "PROBE",
            "MESH",
            "TCPSTART X=1 Y=1 Z=1",
            "ASPIRATE VOLUME=1",
            "DISPENSE VOLUME=1",
            "M104 S40",
            "M109 S40",
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=40",
            "PAUSE",
            "RESUME",
            "CANCEL_PRINT",
            "G20",
            "G21",
            "G10",
            "G11",
            "M106 S255",
            "M107",
            "M220 S100",
            "MOVEMENT_SAFETY_ENABLE",
            "LOAD_BLTOUCH",
            "PARK_BLTOUCH",
            "WAIT S=1",
            "STATUS",
            "SET_BLTOUCH_DOCK_STATE STATE=loaded",
            "TCPON",
            "TCPOFF",
            "TCPABORT",
            "TURN_OFF_HEATERS",
            "TEMPERATURE_WAIT SENSOR=extruder MINIMUM=20",
            "SAVE_GCODE_STATE NAME=test",
            "RESTORE_GCODE_STATE NAME=test",
            "SAVE_VARIABLE VARIABLE=tcp_ready VALUE=True",
            "FIRMWARE_RESTART",
            "RESTART",
            "SAVE_CONFIG",
            "HOST_REBOOT",
            "HOST_SHUTDOWN",
            "REBOOT",
            "SHUTDOWN",
            "M999",
            "G123 X1",
            "M3 S100",
            "T0",
            "MY_CUSTOM_MACRO VALUE=1",
        )

        for script in blocked_scripts:
            with self.subTest(script=script):
                result = parse_manual_gcode(script)
                self.assertTrue(result.is_blocked)
                self.assertTrue(result.blocked_reasons)
                self.assertIsNotNone(result.commands[0].blocked_reason)
                self.assertIn("BLOCKED", result.summary)

    def test_small_reviewed_manual_allowlist_remains_available(self):
        script = "\n".join(
            (
                "G0 X1",
                "G1 Y1",
                "G4 P100",
                "G90",
                "G91",
                "M105",
                "M114",
                "M117 Ready",
                "RESPOND MSG=ready",
                "QUERY_ENDSTOPS",
                "OPENSPOTTER_HOME",
                "OPENSPOTTER_JOG AXIS=X DISTANCE=1 F=600",
                "OPENSPOTTER_RUNTIME_STATUS",
            )
        )

        result = parse_manual_gcode(script)

        self.assertFalse(result.is_blocked)
        self.assertEqual(result.blocked_reasons, ())
        self.assertTrue(result.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
