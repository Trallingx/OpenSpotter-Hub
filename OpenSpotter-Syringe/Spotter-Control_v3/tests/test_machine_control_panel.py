import tkinter as tk
import unittest

from app.machine_control_panel import MachineControlPanel


class MachineControlPanelTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        self.root.geometry("330x613+0+0")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.update_idletasks()
        self.panel = MachineControlPanel(self.root)
        self.root.update_idletasks()
        self.assertEqual(str(self.panel.home_button.cget("text")), "RUN HOMING")

    def tearDown(self):
        if hasattr(self, "root") and self.root.winfo_exists():
            self.root.destroy()

    def test_xyz_live_z_and_gcode_tabs_fit_compact_host(self):
        self.panel.machine_tabs.select(self.panel.motion_tab)
        self.root.update_idletasks()
        self.assertGreaterEqual(self.panel.jog_feed_entry.winfo_width(), 45)
        self.assertLessEqual(
            self.panel.home_button.winfo_rooty()
            + self.panel.home_button.winfo_height(),
            self.root.winfo_rooty() + self.root.winfo_height(),
        )

        self.panel.machine_tabs.select(self.panel.live_z_tab)
        self.root.update_idletasks()
        self.assertTrue(self.panel.z_closer_button.winfo_ismapped())
        self.assertTrue(self.panel.z_away_button.winfo_ismapped())
        self.assertLessEqual(
            self.panel.z_away_button.winfo_rooty()
            + self.panel.z_away_button.winfo_height(),
            self.root.winfo_rooty() + self.root.winfo_height(),
        )

        self.panel.machine_tabs.select(self.panel.gcode_tab)
        self.panel.gcode_modes.select(self.panel.live_gcode_frame)
        self.root.update_idletasks()
        self.assertTrue(self.panel.gcode_text.winfo_ismapped())
        self.assertIn("READ / QUEUED", self.panel.gcode_title_var.get())

        self.panel.gcode_modes.select(self.panel.manual_gcode_frame)
        self.root.update_idletasks()
        self.assertTrue(self.panel.manual_gcode_text.winfo_ismapped())
        self.assertTrue(self.panel.manual_parse_button.winfo_ismapped())
        self.assertTrue(self.panel.manual_console_text.winfo_ismapped())
        self.assertLessEqual(
            self.panel.manual_send_button.winfo_rooty()
            + self.panel.manual_send_button.winfo_height(),
            self.root.winfo_rooty() + self.root.winfo_height(),
        )

    def test_control_gating_keeps_emergency_available_during_unknown_state(self):
        self.panel.set_control_state(
            connected=True,
            ready=True,
            print_state="printing",
            homed_axes="xyz",
            offsets_enabled=True,
            operation_busy=True,
            runtime_started=True,
            gcode_commands=("HOMING", "OPENSPOTTER_JOG"),
            remote_controls_ready=True,
        )

        self.assertEqual(str(self.panel.start_button.cget("state")), "disabled")
        self.assertEqual(str(self.panel.pause_button.cget("state")), "disabled")
        self.assertEqual(str(self.panel.z_closer_button.cget("state")), "disabled")
        self.assertEqual(str(self.panel.emergency_button.cget("state")), "normal")

    def test_motion_controls_require_firmware_macros_and_offsets_disabled(self):
        self.panel.set_control_state(
            connected=True,
            ready=True,
            print_state="standby",
            homed_axes="xyz",
            offsets_enabled=False,
            operation_busy=False,
            runtime_started=True,
            gcode_commands=(),
            remote_controls_ready=False,
        )
        self.assertEqual(str(self.panel.home_button.cget("state")), "disabled")
        self.assertEqual(str(self.panel.jog_buttons[0].cget("state")), "disabled")
        self.assertEqual(str(self.panel.manual_send_button.cget("state")), "normal")

        self.panel.set_control_state(
            connected=True,
            ready=True,
            print_state="standby",
            homed_axes="xyz",
            offsets_enabled=False,
            operation_busy=False,
            runtime_started=True,
            gcode_commands=("HOMING", "OPENSPOTTER_JOG"),
            remote_controls_ready=True,
        )
        self.assertEqual(str(self.panel.home_button.cget("state")), "normal")
        self.assertEqual(str(self.panel.jog_buttons[0].cget("state")), "normal")

        self.panel.set_control_state(
            connected=True,
            ready=True,
            print_state="standby",
            homed_axes="xyz",
            offsets_enabled=True,
            operation_busy=False,
            runtime_started=True,
            gcode_commands=("HOMING", "OPENSPOTTER_JOG"),
            remote_controls_ready=True,
        )
        self.assertEqual(str(self.panel.home_button.cget("state")), "normal")
        self.assertEqual(str(self.panel.jog_buttons[0].cget("state")), "disabled")

    def test_stale_virtual_sd_or_active_mesh_disables_manual_motion(self):
        common = {
            "connected": True,
            "ready": True,
            "print_state": "standby",
            "homed_axes": "xyz",
            "offsets_enabled": False,
            "operation_busy": False,
            "runtime_started": True,
            "gcode_commands": ("HOMING", "OPENSPOTTER_JOG"),
            "remote_controls_ready": True,
        }

        self.panel.set_control_state(
            **common,
            virtual_sd_active=True,
        )
        self.assertEqual(str(self.panel.home_button.cget("state")), "disabled")
        self.assertEqual(str(self.panel.jog_buttons[0].cget("state")), "disabled")
        self.assertEqual(str(self.panel.cancel_button.cget("state")), "normal")
        self.assertEqual(
            str(self.panel.manual_send_button.cget("state")),
            "disabled",
        )

        self.panel.set_control_state(
            **common,
            virtual_sd_active=False,
            bed_mesh_active=True,
        )
        self.assertEqual(str(self.panel.home_button.cget("state")), "normal")
        self.assertEqual(str(self.panel.jog_buttons[0].cget("state")), "disabled")


if __name__ == "__main__":
    unittest.main()
