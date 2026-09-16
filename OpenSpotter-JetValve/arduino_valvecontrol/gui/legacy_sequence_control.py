from PyQt5 import QtCore


class LegacySequenceControlMixin:
    def start_sequence(self):
        if self.updating_ui:
            return
        if not self.connected:
            self.status_label.setText("Connect first")
            return
        if self.stop_requested:
            self.status_label.setText("Stopped")
            return
        if not self._push_current_config():
            return

        self.send_cmd(f"K:{self.cycle_count.value()}")
        self.status_label.setText(f"Sent {self.cycle_count.value()} cycles")

    def stop_sequence(self):
        self.stop_requested = not self.stop_requested
        self.stop_button.setText("Resume" if self.stop_requested else "Stop")
        self.status_label.setText("Stopped" if self.stop_requested else "Ready")