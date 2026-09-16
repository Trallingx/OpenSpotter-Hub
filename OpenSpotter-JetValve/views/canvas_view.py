"""
Canvas View
2D/3D visualization of droplet spots using QGraphicsView.
"""

from typing import List, Dict, Any, Set

from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsSimpleTextItem,
)
from PyQt6.QtGui import QBrush, QColor, QPen, QPainter
from PyQt6.QtCore import Qt

from utils import AppSignals, ConfigManager


class CanvasView(QGraphicsView):
    """
    2D canvas for displaying droplet spots and print paths.
    Uses QGraphicsView/QGraphicsScene for efficient rendering.
    """

    def __init__(self, app_signals: AppSignals = None, parent=None):
        """
        Initialize canvas view.

        Args:
            app_signals: Global application signals
            parent: Parent widget
        """
        super().__init__(parent)
        self.app_signals = app_signals or AppSignals()
        self.grids: List[Dict[str, Any]] = []
        self.finished_keys: Set[str] = set()
        self._spot_items: Dict[str, QGraphicsEllipseItem] = {}
        self._grid_items: List[QGraphicsLineItem] = []
        self._legend_items: List[QGraphicsSimpleTextItem] = []
        self._toolhead_marker_items: List[QGraphicsLineItem] = []
        self._toolhead_position = (0.0, 0.0, 0.0)
        self._mode = "buildplate"
        # Valve colors from machine config (fallback palette if missing)
        palette_fallback = [
            QColor("#f38ba8"), QColor("#a6e3a1"), QColor("#89b4fa"),
            QColor("#f9e2af"), QColor("#94e2d5"), QColor("#cba6f7")
        ]
        self.valve_colors = {}
        cm = ConfigManager.get_instance()
        for i, v in enumerate(cm.get("valves", [])):
            vid = v.get("id", i)
            color = v.get("color")
            if isinstance(color, list) and len(color) == 3:
                qcolor = QColor(color[0], color[1], color[2])
            else:
                qcolor = palette_fallback[i % len(palette_fallback)]
            self.valve_colors[vid] = qcolor

        # Scene setup
        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Zoom/pan behavior
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._panning = False
        self._last_pan_point = None

        # Visual settings from gui config
        self.spot_radius = int(cm.get("gui.canvas.spot_radius_px", 5))
        self.grid_visible = True
        self.spots_visible = True
        self.progress_visible = True

        # Background
        self.setStyleSheet("QGraphicsView { background-color: #1e1e2e; }")

        # Enable anti-aliasing
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._create_toolhead_marker()

        # Signals
        if self.app_signals:
            self.app_signals.canvas_updated.connect(self.update_canvas)
            self.app_signals.grid_definitions_changed.connect(self.set_grids)
            self.app_signals.mode_changed.connect(self.set_mode)
            self.app_signals.config_saved.connect(self.reload_from_config)
            self.app_signals.spotting_progress_updated.connect(self.set_finished_spots)
            self.app_signals.gantry_position_updated.connect(self.set_toolhead_position)

    def update_canvas(self) -> None:
        """Redraw canvas layers that need full rebuild (grid)."""
        # Only rebuild grid layer to avoid heavy redraws
        self._clear_grid_layer()
        if self.grid_visible:
            self._draw_grid()
        # If spot items not built yet, build them
        if self.spots_visible and not self._spot_items:
            self._build_spot_items()
        self._draw_r2r_legend()

    def _draw_grid(self) -> None:
        """Draw background grid."""
        cm = ConfigManager.get_instance()
        grid_color = QColor(cm.get("gui.canvas.grid_color", "#45475a"))
        grid_pen = QPen(grid_color)
        grid_pen.setWidth(int(cm.get("gui.canvas.line_width_px", 1)))
        grid_z = 0.0

        # Grid extent from gantry config; spacing from gui (default 10)
        max_x = int(cm.get("gantry.max_x", 200))
        max_y = int(cm.get("gantry.max_y", 200))
        spacing = int(cm.get("gui.canvas.grid_spacing_mm", 10))
        for x in range(0, max_x + spacing, spacing):
            line = self.scene.addLine(x, 0, x, max_y, grid_pen)
            line.setZValue(grid_z)
            self._grid_items.append(line)
        for y in range(0, max_y + spacing, spacing):
            line = self.scene.addLine(0, y, max_x, y, grid_pen)
            line.setZValue(grid_z)
            self._grid_items.append(line)

    def _build_spot_items(self) -> None:
        """Create persistent QGraphicsEllipseItem for all spots once."""
        self._spot_items.clear()
        active_grids = [grid for grid in self.grids if bool(grid.get("active", True))]
        for grid_index, grid in enumerate(active_grids):
            rows = int(grid.get("rows", 0))
            cols = int(grid.get("cols", 0))
            row_spacing = float(grid.get("row_spacing", 10.0))
            col_spacing = float(grid.get("col_spacing", 10.0))
            origin_x = float(grid.get("origin_x", 20.0))
            origin_y = float(grid.get("origin_y", 20.0))
            valve_id = int(grid.get("valve_id", 0))
            drop_vol = float(grid.get("drop_vol", 1.0))

            color = self._color_for_valve(valve_id)
            planned_alpha = 80
            planned_color = QColor(color.red(), color.green(), color.blue(), planned_alpha)
            planned_brush = QBrush(planned_color)

            radius = drop_vol * 0.1  # 1 => 0.1 mm radius
            visible_rows = self._visible_rows_for_grid(rows)

            for display_row, r in enumerate(visible_rows):
                # Visual order doesn't matter for item creation; use forward
                for c in range(cols):
                    x = origin_x + c * col_spacing
                    y = origin_y + display_row * row_spacing if self._is_r2r_mode() else origin_y + r * row_spacing
                    key = self._spot_key(grid_index, r, c, x, y, valve_id)
                    pen_width = max(0.2, min(3.0, radius * 0.2))
                    ellipse = QGraphicsEllipseItem(
                        x - radius,
                        y - radius,
                        radius * 2,
                        radius * 2,
                    )
                    # Initialize as planned
                    ellipse.setBrush(planned_brush)
                    ppen = QPen(planned_color)
                    ppen.setWidthF(pen_width)
                    ellipse.setPen(ppen)
                    ellipse.setZValue(1.0)
                    self.scene.addItem(ellipse)
                    self._spot_items[key] = ellipse
                    if self._is_r2r_mode():
                        self._spot_items[self._r2r_display_key(grid_index, display_row, c)] = ellipse
                    else:
                        self._spot_items[self._legacy_spot_key(x, y, valve_id)] = ellipse

    def _draw_progress_overlay(self) -> None:
        """Draw progress region overlay."""
        # TODO: Draw progress overlay based on print job progress
        pass


    def wheelEvent(self, event) -> None:
        """Handle mouse wheel for zoom."""
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._last_pan_point = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._last_pan_point is not None:
            delta = event.pos() - self._last_pan_point
            self._last_pan_point = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self._last_pan_point = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def toggle_grid(self, visible: bool) -> None:
        """Toggle grid visibility."""
        self.grid_visible = visible
        self.update_canvas()

    def toggle_spots(self, visible: bool) -> None:
        """Toggle spots visibility."""
        self.spots_visible = visible
        self.update_canvas()

    def toggle_progress(self, visible: bool) -> None:
        """Toggle progress overlay visibility."""
        self.progress_visible = visible
        self.update_canvas()

    def set_mode(self, mode: str) -> None:
        """Switch canvas rendering mode."""
        normalized = "roll-to-roll" if mode == "roll-to-roll" else "buildplate"
        if normalized == self._mode:
            return
        self._mode = normalized
        self.finished_keys.clear()
        self._remove_spot_items()
        self._clear_legend_layer()
        self.update_canvas()

    def set_grids(self, grids: List[Dict[str, Any]]) -> None:
        """Replace grid definitions and trigger redraw."""
        self.grids = grids
        # Rebuild the full canvas so background grid lines and spot items stay in sync.
        self._remove_spot_items()
        self.update_canvas()

    def set_finished_spots(self, finished_keys: List[str]) -> None:
        """Incrementally update spot visuals for changed keys."""
        if self._is_r2r_mode():
            self.finished_keys = set(finished_keys)
            self._apply_r2r_progress()
            self._draw_r2r_legend()
            return

        new_set = set(finished_keys)
        added = new_set - self.finished_keys
        removed = self.finished_keys - new_set
        self.finished_keys = new_set
        # Update only changed items
        for key in added:
            item = self._spot_items.get(key)
            if item:
                # Change brush/pen to finished style
                # Derive valve id from key
                try:
                    _, _, valve_str = key.split(",")
                    valve_id = int(valve_str)
                except Exception:
                    valve_id = 0
                color = self._color_for_valve(valve_id)
                finished_color = QColor(color.red(), color.green(), color.blue(), 255)
                item.setBrush(QBrush(finished_color))
                pen = QPen(finished_color)
                pen.setWidthF(item.pen().widthF())
                item.setPen(pen)
        for key in removed:
            item = self._spot_items.get(key)
            if item:
                # Revert to planned style
                try:
                    _, _, valve_str = key.split(",")
                    valve_id = int(valve_str)
                except Exception:
                    valve_id = 0
                color = self._color_for_valve(valve_id)
                planned_color = QColor(color.red(), color.green(), color.blue(), 80)
                item.setBrush(QBrush(planned_color))
                pen = QPen(planned_color)
                pen.setWidthF(item.pen().widthF())
                item.setPen(pen)

    def set_toolhead_position(self, x: float, y: float, z: float) -> None:
        """Move the persistent live toolhead marker to the latest position."""
        try:
            self._toolhead_position = (float(x), float(y), float(z))
        except (TypeError, ValueError):
            return
        self._update_toolhead_marker()

    def reload_from_config(self) -> None:
        """Reload visual parameters and valve palette from config and redraw."""
        cm = ConfigManager.get_instance()
        # Rebuild valve colors
        palette_fallback = [
            QColor("#f38ba8"), QColor("#a6e3a1"), QColor("#89b4fa"),
            QColor("#f9e2af"), QColor("#94e2d5"), QColor("#cba6f7")
        ]
        self.valve_colors.clear()
        for i, v in enumerate(cm.get("valves", [])):
            vid = v.get("id", i)
            color = v.get("color")
            if isinstance(color, list) and len(color) == 3:
                qcolor = QColor(color[0], color[1], color[2])
            else:
                qcolor = palette_fallback[i % len(palette_fallback)]
            self.valve_colors[vid] = qcolor

        # Spot radius
        self.spot_radius = int(cm.get("gui.canvas.spot_radius_px", 5))
        # Rebuild grid layer; keep spot items and recolor by valve if needed
        self.update_canvas()

    def _color_for_valve(self, valve_id: int) -> QColor:
        """Return a QColor for the given valve id, cycling palette if needed."""
        if valve_id in self.valve_colors:
            return self.valve_colors[valve_id]
        # Fallback: deterministic color based on id
        palette = list(self.valve_colors.values())
        return palette[valve_id % len(palette)]

    def reset_view(self) -> None:
        """Reset zoom and pan to default."""
        self.resetTransform()
        self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _clear_grid_layer(self) -> None:
        """Remove only tracked background grid lines."""
        for item in self._grid_items:
            self.scene.removeItem(item)
        self._grid_items.clear()

    def _clear_legend_layer(self) -> None:
        """Remove R2R progress legend items."""
        for item in self._legend_items:
            self.scene.removeItem(item)
        self._legend_items.clear()

    def _remove_spot_items(self) -> None:
        """Remove current spot ellipse items from scene."""
        removed_item_ids = set()
        for item in list(self._spot_items.values()):
            item_id = id(item)
            if item_id in removed_item_ids:
                continue
            removed_item_ids.add(item_id)
            self.scene.removeItem(item)
        self._spot_items.clear()

    def _is_r2r_mode(self) -> bool:
        return self._mode == "roll-to-roll"

    def _visible_rows_for_grid(self, rows: int) -> List[int]:
        if not self._is_r2r_mode():
            return list(range(max(0, rows)))
        if rows <= 0:
            return []
        return [0, 1 if rows > 1 else 0]

    def _apply_r2r_progress(self) -> None:
        """Map actual row progress onto the two anchored R2R display rows."""
        active_grids = [grid for grid in self.grids if bool(grid.get("active", True))]
        total_rows_by_grid = {
            grid_index: int(grid.get("rows", 0))
            for grid_index, grid in enumerate(active_grids)
        }
        states = self._r2r_progress_by_grid(self.finished_keys, total_rows_by_grid)

        for grid_index, grid in enumerate(active_grids):
            total_rows = max(0, int(grid.get("rows", 0)))
            cols = max(0, int(grid.get("cols", 0)))
            valve_id = int(grid.get("valve_id", 0))
            color = self._color_for_valve(valve_id)
            planned_color = QColor(color.red(), color.green(), color.blue(), 80)
            finished_color = QColor(color.red(), color.green(), color.blue(), 255)
            state = states.get(grid_index, self._empty_r2r_state(total_rows))
            display_rows = state["display_rows"]
            finished_by_row = state["finished_cols_by_row"]

            for display_row in range(2):
                actual_row = display_rows[display_row] if display_row < len(display_rows) else None
                for col in range(cols):
                    item = self._spot_items.get(self._r2r_display_key(grid_index, display_row, col))
                    if not item:
                        continue
                    is_finished = (
                        actual_row is not None
                        and col in finished_by_row.get(actual_row, set())
                    )
                    item_color = finished_color if is_finished else planned_color
                    item.setBrush(QBrush(item_color))
                    pen = QPen(item_color)
                    pen.setWidthF(item.pen().widthF())
                    item.setPen(pen)

    def _draw_r2r_legend(self) -> None:
        """Draw a compact top-right row progress legend in R2R mode."""
        self._clear_legend_layer()
        if not self._is_r2r_mode():
            return

        active_grids = [grid for grid in self.grids if bool(grid.get("active", True))]
        total_rows_by_grid = {
            grid_index: int(grid.get("rows", 0))
            for grid_index, grid in enumerate(active_grids)
        }
        states = self._r2r_progress_by_grid(self.finished_keys, total_rows_by_grid)

        cm = ConfigManager.get_instance()
        max_x = float(cm.get("gantry.max_x", 200))
        y = 8.0
        text_color = QColor("#cdd6f4")
        for grid_index, grid in enumerate(active_grids):
            total_rows = max(0, int(grid.get("rows", 0)))
            state = states.get(grid_index, self._empty_r2r_state(total_rows))
            current_row = int(state["current_row_display"])
            name = str(grid.get("name", f"Grid {grid_index + 1}"))
            item = QGraphicsSimpleTextItem(f"{name}: {current_row}/{total_rows}")
            item.setBrush(QBrush(text_color))
            item.setZValue(4.0)
            self.scene.addItem(item)
            item.setPos(max(0.0, max_x - item.boundingRect().width() - 8.0), y)
            self._legend_items.append(item)
            y += item.boundingRect().height() + 3.0

    @staticmethod
    def _empty_r2r_state(total_rows: int) -> Dict[str, Any]:
        display_rows = [0, 1 if total_rows > 1 else 0]
        return {
            "current_row_display": 0,
            "display_rows": display_rows,
            "finished_cols_by_row": {},
        }

    @classmethod
    def _r2r_progress_by_grid(
        cls,
        finished_keys: Set[str],
        total_rows_by_grid: Dict[int, int],
    ) -> Dict[int, Dict[str, Any]]:
        finished_cols_by_grid: Dict[int, Dict[int, Set[int]]] = {
            grid_index: {}
            for grid_index in total_rows_by_grid
        }
        for key in finished_keys:
            parsed = cls._parse_spot_key(key)
            if parsed is None:
                continue
            grid_index, row, col, _, _, _ = parsed
            if grid_index not in finished_cols_by_grid:
                continue
            finished_cols_by_grid[grid_index].setdefault(row, set()).add(col)

        states: Dict[int, Dict[str, Any]] = {}
        for grid_index, total_rows in total_rows_by_grid.items():
            total_rows = max(0, int(total_rows))
            finished_cols_by_row = finished_cols_by_grid.get(grid_index, {})
            if not finished_cols_by_row or total_rows <= 0:
                states[grid_index] = cls._empty_r2r_state(total_rows)
                continue

            max_row = min(max(finished_cols_by_row), total_rows - 1)
            current_row_display = max_row + 1
            if max_row >= total_rows - 1:
                first_row = max(0, total_rows - 2)
                second_row = total_rows - 1
                display_rows = [first_row, second_row]
            else:
                display_rows = [max_row, max_row + 1 if total_rows > 1 else max_row]

            states[grid_index] = {
                "current_row_display": current_row_display,
                "display_rows": display_rows,
                "finished_cols_by_row": finished_cols_by_row,
            }
        return states

    def _create_toolhead_marker(self) -> None:
        """Create a persistent black X marker for the live toolhead position."""
        marker_pen = QPen(QColor("#000000"))
        marker_pen.setWidthF(1.2)
        for _ in range(2):
            item = QGraphicsLineItem()
            item.setPen(marker_pen)
            item.setZValue(3.0)
            self.scene.addItem(item)
            self._toolhead_marker_items.append(item)
        self._update_toolhead_marker()

    def _update_toolhead_marker(self) -> None:
        if len(self._toolhead_marker_items) != 2:
            return
        x, y, _ = self._toolhead_position
        half_size = 2.5
        self._toolhead_marker_items[0].setLine(
            x - half_size,
            y - half_size,
            x + half_size,
            y + half_size,
        )
        self._toolhead_marker_items[1].setLine(
            x - half_size,
            y + half_size,
            x + half_size,
            y - half_size,
        )

    @staticmethod
    def _spot_key(grid_index: int, row: int, col: int, x: float, y: float, valve_id: int) -> str:
        return f"{grid_index}:{row}:{col}:{x:.3f},{y:.3f},{valve_id}"

    @staticmethod
    def _legacy_spot_key(x: float, y: float, valve_id: int) -> str:
        return f"{x:.3f},{y:.3f},{valve_id}"

    @staticmethod
    def _r2r_display_key(grid_index: int, display_row: int, col: int) -> str:
        return f"r2r:{grid_index}:{display_row}:{col}"

    @staticmethod
    def _parse_spot_key(key: str):
        try:
            grid_part, xy_part, valve_part = str(key).split(",", 2)
            grid_index, row, col, x = grid_part.split(":", 3)
            return (
                int(grid_index),
                int(row),
                int(col),
                float(x),
                float(xy_part),
                int(valve_part),
            )
        except (TypeError, ValueError):
            return None
