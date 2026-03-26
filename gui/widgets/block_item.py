from __future__ import annotations
import json

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QMimeData
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QDrag, QCursor,
    QFontMetrics,
)
from PySide6.QtWidgets import QGraphicsObject, QApplication

from gui.constants import CELL_W, CELL_H, DEFAULT_COLOR

_CHIP_H = 20
_CHIP_MARGIN = 4
_HEADER_H = 36
_BAR_H = 8
_BAR_MARGIN_TOP = 4


class BlockItem(QGraphicsObject):
    team_dropped = Signal(str, str, str)  # team_id, from_block_id, to_block_id

    def __init__(self, block, teams_by_id: dict, dept_color_fn, read_only: bool = False):
        super().__init__()
        self._block = block
        self._teams_by_id = teams_by_id
        self._dept_color_fn = dept_color_fn
        self._read_only = read_only
        self._team_ids: list[str] = []
        self._chip_rects: list[tuple[QRectF, str]] = []  # (rect, team_id)
        self._highlight: str | None = None  # "green" | "red" | None
        self._drag_start: QPointF | None = None
        self._drag_team_id: str | None = None

        self.setAcceptDrops(True)
        if not read_only:
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def set_teams(self, team_ids: list[str]):
        self._team_ids = list(team_ids)
        self._chip_rects = []
        self.update()

    def _used_seats(self) -> int:
        return sum(
            self._teams_by_id[tid].size
            for tid in self._team_ids
            if tid in self._teams_by_id
        )

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, CELL_W, CELL_H)

    def paint(self, painter: QPainter, option, widget):
        rect = self.boundingRect()
        capacity = self._block.capacity
        used = self._used_seats()
        fill_ratio = used / capacity if capacity > 0 else 0.0

        # --- Background ---
        painter.setRenderHint(QPainter.Antialiasing)
        bg_color = QColor("#ffffff")
        painter.setBrush(QBrush(bg_color))

        if self._highlight == "green":
            border_color = QColor("#27AE60")
            border_width = 2.5
        elif self._highlight == "red":
            border_color = QColor("#D0021B")
            border_width = 2.5
        else:
            border_color = QColor("#cccccc")
            border_width = 1.0

        pen = QPen(border_color, border_width)
        painter.setPen(pen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # --- Block ID label ---
        painter.setPen(QPen(QColor("#222222")))
        id_font = QFont()
        id_font.setPointSize(9)
        id_font.setBold(True)
        painter.setFont(id_font)
        painter.drawText(QRectF(8, 4, CELL_W - 16, 16), Qt.AlignLeft | Qt.AlignVCenter,
                         self._block.block_id)

        # Cap label in gray
        cap_font = QFont()
        cap_font.setPointSize(8)
        painter.setFont(cap_font)
        painter.setPen(QPen(QColor("#888888")))
        painter.drawText(QRectF(8, 4, CELL_W - 16, 16), Qt.AlignRight | Qt.AlignVCenter,
                         f"cap={capacity}")

        # --- Seats text ---
        seats_font = QFont()
        seats_font.setPointSize(8)
        painter.setFont(seats_font)
        painter.setPen(QPen(QColor("#555555")))
        painter.drawText(QRectF(8, 18, CELL_W - 16, 14), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{used}/{capacity} seats")

        # --- Capacity bar ---
        bar_y = _HEADER_H - _BAR_H - 2
        bar_rect = QRectF(8, bar_y, CELL_W - 16, _BAR_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#e9ecef")))
        painter.drawRoundedRect(bar_rect, 3, 3)

        if fill_ratio < 0.70:
            bar_color = QColor("#27AE60")
        elif fill_ratio < 0.95:
            bar_color = QColor("#F5A623")
        else:
            bar_color = QColor("#D0021B")

        fill_w = max(0.0, min(bar_rect.width() * fill_ratio, bar_rect.width()))
        if fill_w > 0:
            fill_rect = QRectF(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(fill_rect, 3, 3)

        # --- Team chips ---
        chip_x = _CHIP_MARGIN
        chip_y = _HEADER_H + 2
        chip_w = CELL_W - _CHIP_MARGIN * 2
        max_chips = int((CELL_H - _HEADER_H - _CHIP_MARGIN) / (_CHIP_H + 3))
        max_chips = max(max_chips, 1)

        self._chip_rects = []
        chip_font = QFont()
        chip_font.setPointSize(8)
        painter.setFont(chip_font)
        fm = QFontMetrics(chip_font)

        teams_to_show = self._team_ids[:max_chips]
        overflow = len(self._team_ids) - len(teams_to_show)

        for team_id in teams_to_show:
            team = self._teams_by_id.get(team_id)
            if team is None:
                continue
            color_hex = self._dept_color_fn(team.department)
            chip_rect = QRectF(chip_x, chip_y, chip_w, _CHIP_H)
            self._chip_rects.append((chip_rect, team_id))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color_hex)))
            painter.drawRoundedRect(chip_rect, 4, 4)

            label = f"{team.name} ({team.size})"
            elided = fm.elidedText(label, Qt.ElideRight, int(chip_w) - 8)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(chip_rect.adjusted(4, 0, -4, 0), Qt.AlignLeft | Qt.AlignVCenter, elided)

            chip_y += _CHIP_H + 3

        if overflow > 0:
            painter.setPen(QPen(QColor("#888888")))
            overflow_font = QFont()
            overflow_font.setPointSize(8)
            overflow_font.setItalic(True)
            painter.setFont(overflow_font)
            painter.drawText(
                QRectF(chip_x, chip_y, chip_w, _CHIP_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"+{overflow} more",
            )

    def _team_at_pos(self, pos: QPointF) -> str | None:
        for chip_rect, team_id in self._chip_rects:
            if chip_rect.contains(pos):
                return team_id
        return None

    def mousePressEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if event.button() == Qt.LeftButton:
            team_id = self._team_at_pos(event.pos())
            if team_id:
                self._drag_start = event.pos()
                self._drag_team_id = team_id
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if (
            self._drag_start is not None
            and self._drag_team_id is not None
            and (event.pos() - self._drag_start).manhattanLength() > 5
        ):
            mime = QMimeData()
            payload = json.dumps({
                "team_id": self._drag_team_id,
                "from_block_id": self._block.block_id,
            }).encode("utf-8")
            mime.setData("application/x-team-chip", payload)

            drag = QDrag(event.widget())
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)

            self._drag_start = None
            self._drag_team_id = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self._drag_team_id = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-team-chip"):
            try:
                data = json.loads(bytes(event.mimeData().data("application/x-team-chip")).decode())
                team_id = data.get("team_id")
                from_block_id = data.get("from_block_id")

                if from_block_id == self._block.block_id:
                    # Dropping onto same block — accept silently
                    self._highlight = "green"
                    self.update()
                    event.accept()
                    return

                team = self._teams_by_id.get(team_id)
                if team is None:
                    event.ignore()
                    return

                current_used = self._used_seats()
                # Team is already counted if it's being dragged from this block
                if team_id in self._team_ids:
                    current_used -= team.size

                if current_used + team.size <= self._block.capacity:
                    self._highlight = "green"
                    self.update()
                    event.accept()
                else:
                    self._highlight = "red"
                    self.update()
                    event.ignore()
            except Exception:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-team-chip"):
            try:
                data = json.loads(bytes(event.mimeData().data("application/x-team-chip")).decode())
                team_id = data.get("team_id")
                from_block_id = data.get("from_block_id")
                to_block_id = self._block.block_id

                self._highlight = None
                self.update()

                if from_block_id == to_block_id:
                    event.ignore()
                    return

                event.accept()
                self.team_dropped.emit(team_id, from_block_id, to_block_id)
            except Exception:
                event.ignore()
        else:
            event.ignore()
