"""
Grid Panel
Left sidebar for configuring multiple droplet grids with live canvas updates.
"""

import re
from typing import List

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QLineEdit,
    QCheckBox,
)
from PyQt6.QtCore import Qt

from utils import AppSignals, ConfigManager
from models import GridConfig


class GridPanel(QWidget):
    """
    Sidebar panel that manages multiple grids. Each grid has its own tab
    with controls for rows/cols/spacing/drop volume. Changes emit
    `grid_definitions_changed` for live canvas updates.
    """

    def __init__(self, app_signals: AppSignals = None, parent=None):
        super().__init__(parent)
        self.app_signals = app_signals or AppSignals()
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)

        # Load config-driven valves and grids
        cm = ConfigManager.get_instance()
        self.available_valves = self._active_valves(cm)

        # Load initial grids from machine config via ConfigManager
        grids_data = cm.machine_grids()
        self.grids: List[GridConfig] = [GridConfig.from_dict(g) for g in grids_data]

        self._build_ui()
        self._rebuild_tabs()
        self._emit_grids()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header with actions
        header_layout = QHBoxLayout()
        title = QLabel("Grid Control")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #a6e3a1;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        add_btn = QPushButton("Add Grid")
        add_btn.clicked.connect(self._add_grid)
        header_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove Grid")
        remove_btn.clicked.connect(self._remove_current_grid)
        header_layout.addWidget(remove_btn)

        layout.addLayout(header_layout)

        # Tabs for per-grid controls
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self.tab_widget, 1)

        # Stretch filler
        layout.addStretch()

        self.setLayout(layout)
        self.setStyleSheet(
            """
            QTabWidget::pane { border: 1px solid #45475a; }
            QTabBar::tab { padding: 6px 12px; }
            QLabel { color: #cdd6f4; }
            QPushButton { padding: 4px 8px; }
            """
        )

    def _add_grid(self) -> None:
        default_valve_id = self.available_valves[0]["id"] if self.available_valves else 0
        self.grids.append(GridConfig(name=self._next_default_grid_name(), valve_id=default_valve_id))
        self._rebuild_tabs()
        self._emit_grids()

    def _active_valves(self, cm: ConfigManager) -> List[dict]:
        """Return only active valves for grid assignment."""
        active = [
            {"id": v.get("id", i), "name": v.get("name", f"Valve {v.get('id', i)}")}
            for i, v in enumerate(cm.available_valves())
            if bool(v.get("is_active", True))
        ]
        return active or [{"id": 0, "name": "Valve 0"}]

    def _next_default_grid_name(self) -> str:
        """Generate a non-conflicting default grid name."""
        used_numbers = set()
        for grid in self.grids:
            match = re.fullmatch(r"Grid (\d+)", grid.name.strip())
            if match:
                used_numbers.add(int(match.group(1)))

        next_number = 1
        while next_number in used_numbers:
            next_number += 1
        return f"Grid {next_number}"

    def _remove_current_grid(self) -> None:
        if not self.grids:
            return
        index = self.tab_widget.currentIndex()
        if index < 0 or index >= len(self.grids):
            return
        self.grids.pop(index)
        self._rebuild_tabs()
        self._emit_grids()

    def _rebuild_tabs(self) -> None:
        # Clear tabs
        while self.tab_widget.count():
            self.tab_widget.removeTab(0)

        # Define fields from config/grid.config.json schema
        cm = ConfigManager.get_instance()
        grid_fields_schema = cm.grid_fields()

        if not self.grids:
            empty_tab = QWidget()
            empty_layout = QVBoxLayout(empty_tab)
            empty_layout.addWidget(QLabel("No grids configured"))
            empty_layout.addStretch()
            self.tab_widget.addTab(empty_tab, "Grids")
            return

        for idx, grid in enumerate(self.grids):
            tab = QWidget()
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

            name_edit = QLineEdit(grid.name)
            name_edit.textChanged.connect(lambda text, i=idx: self._update_grid_name(i, text))
            form.addRow("Name", name_edit)

            active_check = QCheckBox("Active")
            active_check.setChecked(bool(grid.active))
            active_check.toggled.connect(lambda checked, i=idx: self._update_grid_active(i, checked))
            form.addRow("", active_check)

            valve_combo = QComboBox()
            for valve in self.available_valves:
                valve_combo.addItem(valve["name"], valve["id"])
            current_index = valve_combo.findData(grid.valve_id)
            valve_combo.setCurrentIndex(current_index if current_index >= 0 else 0)
            valve_combo.currentIndexChanged.connect(
                lambda _, i=idx, combo=valve_combo: self._update_grid_valve(i, combo.currentData())
            )
            form.addRow("Valve", valve_combo)

            for schema in grid_fields_schema:
                name = schema.get("name")
                ftype = schema.get("type")
                label = schema.get("label", name)
                default = schema.get("default")
                min_val = schema.get("min")
                max_val = schema.get("max")
                step = schema.get("step", 0.1)
                decimals = schema.get("decimals", 2)

                if ftype == "int":
                    spin = QSpinBox()
                    if min_val is not None and max_val is not None:
                        spin.setRange(int(min_val), int(max_val))
                    spin.setValue(int(grid.config.get(name, default if default is not None else (min_val or 0))))
                    spin.valueChanged.connect(lambda val, i=idx, f=name: self._update_grid_field(i, f, val))
                    form.addRow(label, spin)
                elif ftype == "float":
                    spin = QDoubleSpinBox()
                    if min_val is not None and max_val is not None:
                        spin.setRange(float(min_val), float(max_val))
                    spin.setDecimals(int(decimals))
                    spin.setSingleStep(float(step))
                    spin.setValue(float(grid.config.get(name, default if default is not None else (min_val or 0.0))))
                    spin.valueChanged.connect(lambda val, i=idx, f=name: self._update_grid_field(i, f, val))
                    form.addRow(label, spin)
                # Extendable: str, bool, color, etc. when added to schema

            tab.setLayout(form)
            self.tab_widget.addTab(tab, grid.name)
            self.tab_widget.setTabText(idx, grid.name)

    def _update_grid_name(self, index: int, name: str) -> None:
        if 0 <= index < len(self.grids):
            grid = self.grids[index]
            grid.name = name.strip() or f"Grid {index + 1}"
            if index < self.tab_widget.count():
                self.tab_widget.setTabText(index, grid.name)
            self._emit_grids()

    def _update_grid_valve(self, index: int, valve_id) -> None:
        if 0 <= index < len(self.grids):
            self.grids[index].valve_id = int(valve_id or 0)
            self._emit_grids()

    def _update_grid_active(self, index: int, active: bool) -> None:
        if 0 <= index < len(self.grids):
            self.grids[index].active = bool(active)
            self._emit_grids()

    def _update_grid_field(self, index: int, field: str, value) -> None:
        if 0 <= index < len(self.grids):
            grid = self.grids[index]
            grid.config[field] = value
            self._emit_grids()

    def _emit_grids(self) -> None:
        if self.app_signals:
            payload = [g.to_dict() for g in self.grids]
            self.app_signals.grid_definitions_changed.emit(payload)

    def get_grids_payload(self):
        """Return grid definitions as list of dicts (for saving)."""
        return [g.to_dict() for g in self.grids]

    def set_available_valves(self, valves: List[dict]) -> None:
        """Update valve choices without replacing the current grid definitions."""
        self.available_valves = valves
        if hasattr(self, "tab_widget"):
            self._rebuild_tabs()
            self._emit_grids()

    def set_grids(self, grids: List[GridConfig]) -> None:
        """Replace grids from external state and rebuild UI."""
        self.grids = grids
        self._rebuild_tabs()
        self._emit_grids()
