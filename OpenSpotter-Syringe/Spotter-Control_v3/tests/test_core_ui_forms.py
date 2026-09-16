import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.schema import Field
from app.core.ui import forms
from app.grid import create_labels as legacy_create_labels
from app.machine_parameters_window import (
    create_labels as machine_parameter_create_labels,
)
from app.plugins.grid.editor import create_labels as grid_create_labels
from app.plugins.spiral.fields import SPIRAL_FIELDS


class FakeWidget:
    def __init__(self, parent=None, **options):
        self.parent = parent
        self.options = options
        self.grid_options = None
        self.bindings = {}
        self.value = ""

    def cget(self, key):
        if key == "bg":
            return self.options.get("bg", "#000000")
        return self.options.get(key)

    def grid(self, **options):
        self.grid_options = options

    def bind(self, event_name, callback):
        self.bindings[event_name] = callback

    def insert(self, _index, value):
        self.value = value

    def set(self, value):
        self.value = value


class FakeFrame(FakeWidget):
    def __init__(self, parent=None, **options):
        super().__init__(parent, **options)
        self.column_options = {}
        self.row_options = {}

    def columnconfigure(self, column, **options):
        self.column_options[column] = options

    def rowconfigure(self, row, **options):
        self.row_options[row] = options


class FakeNotebook(FakeFrame):
    def __init__(self, parent=None, **options):
        super().__init__(parent, **options)
        self.pages = []

    def add(self, frame, **options):
        self.pages.append((frame, options))


class FakeLabel(FakeWidget):
    pass


class FakeEntry(FakeWidget):
    pass


class FakeCombobox(FakeWidget):
    pass


class CoreUiFormTests(unittest.TestCase):
    def _patched_widgets(self):
        return (
            patch.object(forms.tk, "Frame", FakeFrame),
            patch.object(forms.tk, "Label", FakeLabel),
            patch.object(forms.tk, "Entry", FakeEntry),
            patch.object(forms.ttk, "Notebook", FakeNotebook),
            patch.object(forms.ttk, "Combobox", FakeCombobox),
        )

    def test_legacy_and_core_imports_share_the_same_builder(self):
        self.assertIs(legacy_create_labels, forms.create_labels)
        self.assertIs(grid_create_labels, forms.create_labels)
        self.assertIs(machine_parameter_create_labels, forms.create_labels)

    def test_spiral_choices_are_declared_by_the_plugin_schema(self):
        fields = dict((field.key, field) for field in SPIRAL_FIELDS)

        self.assertEqual(fields["spiral_mode"].widget, "combobox")
        self.assertEqual(
            fields["spiral_mode"].choices,
            ("drop", "continuous"),
        )
        self.assertEqual(fields["interleave"].widget, "combobox")
        self.assertEqual(fields["interleave"].choices, (False, True))

    def test_builder_renders_generic_choice_and_entry_fields(self):
        input_frame = FakeFrame(bg="#101010")
        entries = []
        all_widgets = []
        redraw = Mock()
        gui = SimpleNamespace(
            canvas_drawer=SimpleNamespace(request_redraw=redraw)
        )
        fields = [
            Field(
                "arbitrary_mode",
                "Mode",
                "str",
                default="first",
                choices=("first", "second"),
            ),
            Field(
                "arbitrary_flag",
                "Enabled",
                "bool",
                default=False,
                widget="combobox",
                choices=(False, True),
            ),
            Field("amount", "Amount", "mm", default=1.25),
        ]

        patches = self._patched_widgets()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            forms.create_labels(
                fields,
                {"arbitrary_flag": "yes", "amount": 2.5},
                entries,
                input_frame,
                gui=gui,
                start_row=4,
                widgets_list=all_widgets,
            )

        self.assertIsInstance(entries[0], FakeCombobox)
        self.assertEqual(entries[0].options["values"], ["first", "second"])
        self.assertEqual(entries[0].value, "first")
        self.assertEqual(
            set(entries[0].bindings),
            {"<<ComboboxSelected>>"},
        )

        self.assertIsInstance(entries[1], FakeCombobox)
        self.assertEqual(entries[1].options["values"], ["False", "True"])
        self.assertEqual(entries[1].value, "True")

        self.assertIsInstance(entries[2], FakeEntry)
        self.assertEqual(entries[2].value, "2.5")
        self.assertEqual(set(entries[2].bindings), {"<KeyRelease>"})
        self.assertEqual(entries[2].grid_options["row"], 6)
        self.assertEqual(len(all_widgets), 9)

        entries[0].bindings["<<ComboboxSelected>>"](None)
        entries[2].bindings["<KeyRelease>"](None)
        self.assertEqual(redraw.call_count, 2)

    def test_builder_groups_tabbed_fields_in_declaration_order(self):
        input_frame = FakeFrame(bg="#101010")
        entries = []
        fields = [
            Field("x", "X", "mm", tab="Geometry"),
            Field("speed", "Speed", "mm/s", tab="Motion"),
            Field("y", "Y", "mm", tab="Geometry"),
        ]

        patches = self._patched_widgets()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            forms.create_labels(
                fields,
                {},
                entries,
                input_frame,
                start_row=2,
            )

        geometry_frame = entries[0].parent
        motion_frame = entries[1].parent
        self.assertIs(entries[2].parent, geometry_frame)
        self.assertIsNot(geometry_frame, motion_frame)
        self.assertEqual(entries[0].grid_options["row"], 2)
        self.assertEqual(entries[2].grid_options["row"], 3)
        self.assertEqual(entries[1].grid_options["row"], 2)


if __name__ == "__main__":
    unittest.main()
