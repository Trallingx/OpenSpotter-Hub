import tkinter as tk
import unittest
from tkinter import messagebox
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.gui_v3 import DropletGui
from app.machine_parameters_window import MachineParametersWindow


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class MachineParametersWindowTests(unittest.TestCase):
    def test_hide_withdraws_without_destroying_the_window(self):
        window = SimpleNamespace(withdraw=Mock())

        result = MachineParametersWindow.hide(window)

        window.withdraw.assert_called_once_with()
        self.assertEqual(result, "break")

    def test_show_reuses_the_window_and_restores_maximized_state(self):
        window = SimpleNamespace(
            deiconify=Mock(),
            _maximize=Mock(),
            lift=Mock(),
            focus_set=Mock(),
        )

        result = MachineParametersWindow.show(window)

        self.assertIs(result, window)
        window.deiconify.assert_called_once_with()
        window._maximize.assert_called_once_with()
        window.lift.assert_called_once_with()
        window.focus_set.assert_called_once_with()

    def test_maximize_prefers_native_zoomed_window_state(self):
        window = SimpleNamespace(
            state=Mock(),
            attributes=Mock(),
            geometry=Mock(),
        )

        MachineParametersWindow._maximize(window)

        window.state.assert_called_once_with("zoomed")
        window.attributes.assert_not_called()
        window.geometry.assert_not_called()

    def test_maximize_falls_back_to_decorated_screen_geometry(self):
        window = SimpleNamespace(
            state=Mock(side_effect=tk.TclError),
            attributes=Mock(side_effect=tk.TclError),
            winfo_screenwidth=Mock(return_value=1920),
            winfo_screenheight=Mock(return_value=1080),
            geometry=Mock(),
        )

        MachineParametersWindow._maximize(window)

        window.geometry.assert_called_once_with("1920x1080+0+0")

    def test_populate_uses_existing_label_builder_once_and_keeps_entry_list(self):
        input_frame = Mock()
        window = SimpleNamespace(
            _populated=False,
            input_frame=input_frame,
            _sync_scrollregion=Mock(),
        )
        entries = []
        fields = [object()]
        defaults = {"x": 1}
        gui = object()

        with patch(
            "app.machine_parameters_window.create_labels"
        ) as create_labels:
            MachineParametersWindow.populate(
                window,
                fields,
                defaults,
                entries,
                gui=gui,
            )

        create_labels.assert_called_once_with(
            fields,
            defaults,
            entries,
            input_frame,
            gui=gui,
        )
        input_frame.update_idletasks.assert_called_once_with()
        window._sync_scrollregion.assert_called_once_with()
        self.assertTrue(window._populated)

        with self.assertRaisesRegex(RuntimeError, "already been populated"):
            MachineParametersWindow.populate(
                window,
                fields,
                defaults,
                entries,
                gui=gui,
            )

    def test_gui_open_action_delegates_to_persistent_window(self):
        editor = SimpleNamespace(show=Mock(return_value="shown"))
        gui = SimpleNamespace(machine_parameters_window=editor)

        result = DropletGui.show_machine_parameters(gui)

        self.assertEqual(result, "shown")
        editor.show.assert_called_once_with()

    def test_unlock_warning_keeps_existing_lock_contract_and_uses_editor_parent(self):
        editor = object()
        gui = SimpleNamespace(
            global_locked=FakeVariable(True),
            machine_parameters_window=editor,
            _update_global_fields_state=Mock(),
            lock_button=SimpleNamespace(config=Mock()),
        )

        with patch(
            "app.gui_v3.messagebox.showwarning",
            return_value=messagebox.OK,
        ) as warning:
            DropletGui._toggle_global_lock(gui)

        self.assertFalse(gui.global_locked.get())
        gui._update_global_fields_state.assert_called_once_with()
        gui.lock_button.config.assert_called_once_with(text="EDITING")
        self.assertIs(warning.call_args.kwargs["parent"], editor)

    def test_relocking_does_not_prompt_and_disables_fields_again(self):
        gui = SimpleNamespace(
            global_locked=FakeVariable(False),
            machine_parameters_window=object(),
            _update_global_fields_state=Mock(),
            lock_button=SimpleNamespace(config=Mock()),
        )

        with patch("app.gui_v3.messagebox.showwarning") as warning:
            DropletGui._toggle_global_lock(gui)

        warning.assert_not_called()
        self.assertTrue(gui.global_locked.get())
        gui._update_global_fields_state.assert_called_once_with()
        gui.lock_button.config.assert_called_once_with(text="LOCKED")


if __name__ == "__main__":
    unittest.main()
