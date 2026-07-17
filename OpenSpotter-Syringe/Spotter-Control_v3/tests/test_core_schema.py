import math
import unittest

from app.SpotterFunctions import (
    Field as LegacyField,
    coerce_field_value as legacy_coerce_field_value,
    entries_to_dict,
    parse_widget_entries as legacy_parse_widget_entries,
)
from app.core.schema import (
    Field,
    FieldInputError,
    coerce_field_value,
    parse_widget_entries,
)
from app.input_configs import Field as ConfigField


class FakeEntry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class BrokenEntry:
    def get(self):
        raise RuntimeError("widget unavailable")


class CoreSchemaTests(unittest.TestCase):
    def test_legacy_modules_reexport_the_core_field_and_parsers(self):
        self.assertIs(ConfigField, Field)
        self.assertIs(LegacyField, Field)
        self.assertIs(legacy_coerce_field_value, coerce_field_value)
        self.assertIs(legacy_parse_widget_entries, parse_widget_entries)

    def test_non_strict_parser_preserves_gui_coercion_and_defaulting(self):
        fields = [
            Field("speed", "Speed", "mm/s", default=1.5),
            Field("count", "Count", "int", default=2),
            Field("enabled", "Enabled", "bool", default=False),
            Field("mode", "Mode", "str", default="drop"),
            Field("missing", "Missing", "mm", default=9.0),
        ]
        errors = []

        values = parse_widget_entries(
            [
                FakeEntry("invalid"),
                FakeEntry("3.9"),
                FakeEntry("not-a-known-boolean"),
                FakeEntry("continuous"),
                BrokenEntry(),
            ],
            fields,
            on_error=lambda field, raw, default, error: errors.append(
                (field.key, raw, default, str(error))
            ),
        )

        self.assertEqual(
            values,
            {
                "speed": 1.5,
                "count": 3,
                "enabled": False,
                "mode": "continuous",
                "missing": 9.0,
            },
        )
        self.assertEqual([error[0] for error in errors], ["speed", "missing"])
        self.assertEqual(errors[1][1], "<unavailable>")

    def test_legacy_entries_to_dict_keeps_public_behavior(self):
        fields = [
            Field("integer", "Integer", "int", default=4),
            Field("boolean", "Boolean", "bool", default=True),
            Field("number", "Number", "mm", default=2.5),
        ]

        values = entries_to_dict(
            [FakeEntry("2.0"), FakeEntry("off"), FakeEntry("bad")],
            fields,
        )

        self.assertEqual(
            values,
            {"integer": 2, "boolean": False, "number": 2.5},
        )

    def test_strict_parser_accepts_unambiguous_finite_values(self):
        fields = [
            Field("integer", "Integer", "int", default=0),
            Field("enabled", "Enabled", "bool", default=False),
            Field("number", "Number", "mm", default=0.0),
            Field("mode", "Mode", "str", default=""),
        ]

        values = parse_widget_entries(
            [
                FakeEntry("2.0"),
                FakeEntry("off"),
                FakeEntry("1.25"),
                FakeEntry("drop"),
            ],
            fields,
            strict=True,
            context="Pattern",
        )

        self.assertEqual(
            values,
            {
                "integer": 2,
                "enabled": False,
                "number": 1.25,
                "mode": "drop",
            },
        )

    def test_strict_parser_reports_all_invalid_fields(self):
        fields = [
            Field("integer", "Integer", "int", default=0),
            Field("enabled", "Enabled", "bool", default=False),
            Field("number", "Number", "mm", default=0.0),
        ]

        with self.assertRaises(FieldInputError) as raised:
            parse_widget_entries(
                [
                    FakeEntry("2.5"),
                    FakeEntry("maybe"),
                    FakeEntry("nan"),
                ],
                fields,
                strict=True,
                context="Pattern",
            )

        message = str(raised.exception)
        self.assertIn("Pattern contains invalid values", message)
        self.assertIn("Integer: expected a finite whole number", message)
        self.assertIn("Enabled: expected true or false", message)
        self.assertIn("Number: expected a finite number", message)

    def test_strict_parser_rejects_missing_widgets(self):
        fields = [
            Field("first", "First", "mm"),
            Field("second", "Second", "mm"),
        ]

        with self.assertRaisesRegex(
            FieldInputError,
            "missing 1 required input field",
        ):
            parse_widget_entries(
                [FakeEntry("1")],
                fields,
                strict=True,
                context="Pattern",
            )

    def test_direct_coercion_distinguishes_strict_numeric_rules(self):
        integer = Field("integer", "Integer", "int")
        number = Field("number", "Number", "mm")

        self.assertEqual(coerce_field_value(integer, "2.9"), 2)
        self.assertTrue(math.isnan(coerce_field_value(number, "nan")))
        with self.assertRaisesRegex(ValueError, "finite whole number"):
            coerce_field_value(integer, "2.9", strict=True)
        with self.assertRaisesRegex(ValueError, "finite number"):
            coerce_field_value(number, "inf", strict=True)


if __name__ == "__main__":
    unittest.main()
