import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.gui_v3 import DropletGui
from app.input_configs import Field
from app.visual_object_editor import VisualObjectEditor
from app.visual_objects import VisualObjectValidationError


class FakeEntry:
    def __init__(self, value, state="normal"):
        self.value = str(value)
        self.state = state

    def get(self):
        return self.value

    def cget(self, name):
        if name != "state":
            raise KeyError(name)
        return self.state


class FakeCanvasDrawer:
    def __init__(self):
        self.redraws = 0

    def request_redraw(self):
        self.redraws += 1


class FailingCanvasDrawer:
    @staticmethod
    def request_redraw():
        raise RuntimeError("redraw failed")

    @staticmethod
    def reset_view():
        raise RuntimeError("reset failed")


class VisualBindingGuiTests(unittest.TestCase):
    def _target(self, entry, *, value_type="float"):
        return {
            "widget": entry,
            "field": Field("container1_x", "Container 1 X", "mm"),
            "type": value_type,
            "unit": "mm",
            "source": "Global machine parameters",
            "description": "Container 1 X",
        }

    def test_provider_reports_live_value_and_lock_state(self):
        entry = FakeEntry("16.5", state="disabled")
        owner = SimpleNamespace(
            _visual_binding_targets=lambda: {
                "global.container1_x": self._target(entry)
            }
        )

        catalog = DropletGui._visual_binding_variable_provider(owner)

        self.assertEqual(catalog["global.container1_x"]["value"], 16.5)
        self.assertTrue(catalog["global.container1_x"]["valid"])
        self.assertFalse(catalog["global.container1_x"]["writable"])

        entry.value = "21.25"
        entry.state = "normal"
        refreshed = DropletGui._visual_binding_variable_provider(owner)
        self.assertEqual(refreshed["global.container1_x"]["value"], 21.25)
        self.assertTrue(refreshed["global.container1_x"]["writable"])

    def test_reverse_write_respects_machine_lock_and_redraws_when_unlocked(self):
        entry = FakeEntry("16", state="disabled")
        drawer = FakeCanvasDrawer()

        def set_entry_value(widget, value, _field):
            widget.value = str(value)

        owner = SimpleNamespace(
            _visual_binding_targets=lambda: {
                "global.container1_x": self._target(entry)
            },
            _set_entry_value=set_entry_value,
            canvas_drawer=drawer,
        )

        with self.assertRaisesRegex(ValueError, "Unlock GLOBAL MACHINE PARAMETERS"):
            DropletGui._set_visual_binding_variable(
                owner,
                "global.container1_x",
                30,
            )
        self.assertEqual(entry.value, "16")
        self.assertEqual(drawer.redraws, 0)

        entry.state = "normal"
        result = DropletGui._set_visual_binding_variable(
            owner,
            "global.container1_x",
            30,
        )

        self.assertEqual(result, 30.0)
        self.assertEqual(entry.value, "30.0")
        self.assertEqual(drawer.redraws, 1)

    def test_redraw_failures_do_not_undo_committed_binding_state(self):
        entry = FakeEntry("16", state="normal")

        def set_entry_value(widget, value, _field):
            widget.value = str(value)

        owner = SimpleNamespace(
            _visual_binding_targets=lambda: {
                "global.container1_x": self._target(entry)
            },
            _set_entry_value=set_entry_value,
            canvas_drawer=FailingCanvasDrawer(),
        )
        with patch("app.gui_v3.traceback.print_exc") as report_error:
            result = DropletGui._set_visual_binding_variable(
                owner,
                "global.container1_x",
                30,
            )

        self.assertEqual(result, 30.0)
        self.assertEqual(entry.value, "30.0")
        report_error.assert_called_once()

        saved_objects = [{"id": "linked"}]
        save_owner = SimpleNamespace(
            visual_object_store=SimpleNamespace(
                save=lambda _objects: {"objects": saved_objects}
            ),
            visual_objects=[],
            canvas_drawer=FailingCanvasDrawer(),
        )
        with patch("app.gui_v3.traceback.print_exc") as report_error:
            DropletGui._save_visual_objects(
                save_owner,
                saved_objects,
            )

        self.assertIs(save_owner.visual_objects, saved_objects)
        report_error.assert_called_once()

    def test_program_source_wins_until_visual_geometry_is_intentionally_edited(self):
        catalog = {
            "global.container1_x": {
                "value": 25.0,
                "writable": True,
            }
        }
        owner = SimpleNamespace(
            _read_variable_catalog=lambda: catalog,
            _catalog_value=VisualObjectEditor._catalog_value,
            _same_number=VisualObjectEditor._same_number,
            _binding_catalog={},
            _geometry_dirty=set(),
        )
        unchanged_draft = {
            "x": 16.0,
            "bindings": {"x": "global.container1_x"},
        }

        updates, _previous = VisualObjectEditor._prepare_binding_updates(
            owner,
            unchanged_draft,
        )

        self.assertEqual(updates, {})
        self.assertEqual(unchanged_draft["x"], 25.0)

        owner._geometry_dirty = {"x"}
        edited_draft = {
            "x": 30.0,
            "bindings": {"x": "global.container1_x"},
        }
        updates, _previous = VisualObjectEditor._prepare_binding_updates(
            owner,
            edited_draft,
        )

        self.assertEqual(updates, {"global.container1_x": 30.0})

    def test_one_dirty_property_updates_every_property_sharing_its_source(self):
        target_name = "global.shared_size"
        catalog = {
            target_name: {
                "value": 12.0,
                "writable": True,
            }
        }
        owner = SimpleNamespace(
            _read_variable_catalog=lambda: catalog,
            _catalog_value=VisualObjectEditor._catalog_value,
            _same_number=VisualObjectEditor._same_number,
            _binding_catalog={},
            _geometry_dirty={"width"},
        )
        draft = {
            "width": 20.0,
            "height": 12.0,
            "bindings": {
                "width": target_name,
                "height": target_name,
            },
        }

        updates, _previous = VisualObjectEditor._prepare_binding_updates(
            owner,
            draft,
        )

        self.assertEqual(updates, {target_name: 20.0})
        self.assertEqual(draft["width"], 20.0)
        self.assertEqual(draft["height"], 20.0)

        owner._geometry_dirty = {"width", "height"}
        conflicting = {
            "width": 20.0,
            "height": 25.0,
            "bindings": {
                "width": target_name,
                "height": target_name,
            },
        }
        with self.assertRaisesRegex(
            VisualObjectValidationError,
            "must use the same value",
        ):
            VisualObjectEditor._prepare_binding_updates(owner, conflicting)

    def test_layer_move_publishes_top_first_mapping_and_rolls_back_on_failure(self):
        published = []
        owner = SimpleNamespace(
            objects=[{"id": "back"}, {"id": "middle"}, {"id": "front"}],
            selected_index=1,
            _publish=lambda selected_index, reload_form: published.append(
                (selected_index, reload_form)
            ),
            _update_layer_buttons=lambda: None,
            _refresh_list=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(
            VisualObjectEditor._display_index_from_storage_index(owner, 2),
            0,
        )
        self.assertEqual(
            VisualObjectEditor._storage_index_from_display_index(owner, 0),
            2,
        )

        VisualObjectEditor._move_layer(owner, "up")

        self.assertEqual(
            [item["id"] for item in owner.objects],
            ["back", "front", "middle"],
        )
        self.assertEqual(owner.selected_index, 2)
        self.assertEqual(published, [(2, False)])

        original = list(owner.objects)
        owner.selected_index = 1

        def fail_publish(_selected_index, reload_form):
            self.assertFalse(reload_form)
            raise RuntimeError("save failed")

        owner._publish = fail_publish
        with patch("app.visual_object_editor.messagebox.showerror") as show_error:
            VisualObjectEditor._move_layer(owner, "down")

        self.assertEqual(owner.objects, original)
        self.assertEqual(owner.selected_index, 1)
        show_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
