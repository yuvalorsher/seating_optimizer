from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QWheelEvent
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem

from seating_optimizer.scorer import compute_total_score
from seating_optimizer.loader import get_department_map

from gui.constants import CELL_W, CELL_H, CELL_GAP
from gui.widgets.block_item import BlockItem

_ZOOM_STEP = 1.15
_ZOOM_MIN = 0.2
_ZOOM_MAX = 5.0


class OfficeGridView(QGraphicsView):
    team_moved = Signal(str, str, str, int)  # team_id, from_block_id, to_block_id, day

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._solution = None
        self._day = 1
        self._blocks: list = []
        self._teams_by_id: dict = {}
        self._blocks_by_id: dict = {}
        self._dept_color_fn = None
        self._block_items: dict[str, BlockItem] = {}
        self._read_only = False
        self._user_zoomed = False
        self._current_scale = 1.0

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAcceptDrops(True)  # required for item-level drop events to fire
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor("#f0f2f5")))

    def set_read_only(self, read_only: bool):
        self._read_only = read_only

    def load(self, solution, day: int, blocks: list, teams_by_id: dict, dept_color_fn=None):
        self._solution = solution
        self._day = day
        self._blocks = blocks
        self._teams_by_id = teams_by_id
        self._blocks_by_id = {b.block_id: b for b in blocks}
        self._dept_color_fn = dept_color_fn
        self._rebuild_scene()

    def reload_day(self, day: int):
        self._day = day
        if self._solution:
            self._rebuild_scene()

    def zoom_in(self):
        self._apply_zoom(_ZOOM_STEP)

    def zoom_out(self):
        self._apply_zoom(1.0 / _ZOOM_STEP)

    def zoom_reset(self):
        self._user_zoomed = False
        self._current_scale = 1.0
        self.resetTransform()
        self._fit_in_view()

    def _apply_zoom(self, factor: float):
        new_scale = self._current_scale * factor
        if new_scale < _ZOOM_MIN or new_scale > _ZOOM_MAX:
            return
        self._user_zoomed = True
        self._current_scale = new_scale
        self.scale(factor, factor)

    def _rebuild_scene(self):
        self._scene.clear()
        self._block_items = {}
        self._user_zoomed = False
        self._current_scale = 1.0
        self.resetTransform()

        if not self._blocks or self._solution is None:
            return

        grid_rows = max(b.row for b in self._blocks) + 1
        grid_cols = max(b.col for b in self._blocks) + 1

        # Map from (row, col) to block
        block_map: dict[tuple, object] = {
            (b.row, b.col): b for b in self._blocks
        }

        # Get day view
        day_view = self._solution.get_day_view(self._day)

        for row in range(grid_rows):
            for col in range(grid_cols):
                x = col * (CELL_W + CELL_GAP)
                y = row * (CELL_H + CELL_GAP)

                if (row, col) in block_map:
                    block = block_map[(row, col)]
                    item = BlockItem(
                        block,
                        self._teams_by_id,
                        self._dept_color_fn or (lambda d: "#888888"),
                        read_only=self._read_only,
                    )
                    item.setPos(x, y)
                    team_ids = day_view.get(block.block_id, [])
                    item.set_teams(team_ids)
                    item.team_dropped.connect(self._on_team_dropped)
                    self._scene.addItem(item)
                    self._block_items[block.block_id] = item
                else:
                    # Empty cell placeholder
                    rect_item = QGraphicsRectItem(0, 0, CELL_W, CELL_H)
                    rect_item.setBrush(QBrush(QColor("#dde1e7")))
                    rect_item.setPen(Qt.NoPen)
                    rect_item.setPos(x, y)
                    self._scene.addItem(rect_item)

        total_w = grid_cols * (CELL_W + CELL_GAP) - CELL_GAP
        total_h = grid_rows * (CELL_H + CELL_GAP) - CELL_GAP
        self._scene.setSceneRect(0, 0, total_w, total_h)
        # Defer fitInView so it runs after the widget is laid out and visible
        QTimer.singleShot(0, self._fit_in_view)

    def _fit_in_view(self):
        if not self._user_zoomed and self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            # Track resulting scale so zoom_in/out starts from the right baseline
            t = self.transform()
            self._current_scale = t.m11()

    def _on_team_dropped(self, team_id: str, from_block_id: str, to_block_id: str):
        if self._solution is None:
            return

        # Mutate block_assignments in-place
        for ba in self._solution.block_assignments:
            if ba.team_id == team_id and ba.day == self._day:
                ba.block_id = to_block_id
                break

        # Recompute score
        day_assignments = {da.team_id: da.days for da in self._solution.day_assignments}
        block_assignments = {
            (ba.team_id, ba.day): ba.block_id for ba in self._solution.block_assignments
        }
        dept_map = get_department_map(list(self._teams_by_id.values()))
        score, breakdown = compute_total_score(
            day_assignments, block_assignments,
            self._teams_by_id, self._blocks_by_id, dept_map,
        )
        self._solution.score = score
        self._solution.score_breakdown = breakdown

        # Rebuild to reflect changes
        self._rebuild_scene()
        self.team_moved.emit(team_id, from_block_id, to_block_id, self._day)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._apply_zoom(_ZOOM_STEP)
            elif delta < 0:
                self._apply_zoom(1.0 / _ZOOM_STEP)
            event.accept()
        else:
            super().wheelEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_in_view)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_in_view()
