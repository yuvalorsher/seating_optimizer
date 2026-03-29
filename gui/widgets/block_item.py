from __future__ import annotations
import json

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QMimeData
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QDrag, QCursor,
    QFontMetrics,
)
from PySide6.QtWidgets import QGraphicsObject, QApplication, QToolTip

from gui.constants import CELL_W, CELL_H, DEFAULT_COLOR

_CHIP_H = 20
_CHIP_MARGIN = 4
_HEADER_H = 36
_BAR_H = 8
_BAR_MARGIN_TOP = 4


class BlockItem(QGraphicsObject):
    team_dropped = Signal(str, str, str)   # group_id, from_block_id, to_block_id
    team_right_clicked = Signal(str, str)  # group_id, block_id

    def __init__(
        self,
        block,
        groups_by_id: dict,
        group_color_fn,
        employees_by_group: dict = None,
        read_only: bool = False,
        allow_oversize: bool = False,
    ):
        super().__init__()
        self._block = block
        self._groups_by_id = groups_by_id
        self._group_color_fn = group_color_fn
        self._employees_by_group = employees_by_group or {}
        self._read_only = read_only
        self._allow_oversize = allow_oversize
        # Each chip: (group_id, count)
        self._group_chips: list[tuple[str, int]] = []
        self._chip_rects: list[tuple[QRectF, str]] = []  # (rect, group_id)
        self._highlight: str | None = None
        self._external_highlight: str | None = None
        self._drag_start: QPointF | None = None
        self._drag_group_id: str | None = None

        self.setAcceptDrops(True)
        self.setAcceptHoverEvents(True)
        if not read_only:
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def set_external_highlight(self, color: str | None):
        self._external_highlight = color
        self.update()

    def set_groups(self, group_chips: list[tuple[str, int]]):
        """Set displayed groups: list of (group_id, count)."""
        self._group_chips = list(group_chips)
        self._chip_rects = []
        self.update()

    def _used_seats(self) -> int:
        return sum(count for _, count in self._group_chips)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, CELL_W, CELL_H)

    def paint(self, painter: QPainter, option, widget):
        rect = self.boundingRect()
        capacity = self._block.capacity
        used = self._used_seats()
        fill_ratio = used / capacity if capacity > 0 else 0.0

        # --- Background ---
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#ffffff")))

        effective_highlight = self._highlight or self._external_highlight
        if effective_highlight == "green":
            border_color = QColor("#27AE60")
            border_width = 2.5
        elif effective_highlight == "red":
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

        # --- Group chips ---
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

        chips_to_show = self._group_chips[:max_chips]
        overflow = len(self._group_chips) - len(chips_to_show)

        for group_id, count in chips_to_show:
            color_hex = self._group_color_fn(group_id)
            chip_rect = QRectF(chip_x, chip_y, chip_w, _CHIP_H)
            self._chip_rects.append((chip_rect, group_id))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color_hex)))
            painter.drawRoundedRect(chip_rect, 4, 4)

            group = self._groups_by_id.get(group_id)
            label = f"{group_id} ×{count}" if group else f"{group_id} ×{count}"
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
                f"+{overflow} more groups",
            )

    def _group_at_pos(self, pos: QPointF) -> str | None:
        for chip_rect, group_id in self._chip_rects:
            if chip_rect.contains(pos):
                return group_id
        return None

    def hoverMoveEvent(self, event):
        group_id = self._group_at_pos(event.pos())
        if group_id and group_id in self._employees_by_group:
            names = [e.name for e in self._employees_by_group[group_id]]
            tooltip = f"<b>{group_id}</b><br>" + "<br>".join(names)
            QToolTip.showText(
                event.screenPos().toPoint(), tooltip,
            )
        else:
            QToolTip.hideText()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if event.button() == Qt.RightButton:
            group_id = self._group_at_pos(event.pos())
            if group_id:
                self.team_right_clicked.emit(group_id, self._block.block_id)
                event.accept()
                return
        if event.button() == Qt.LeftButton:
            group_id = self._group_at_pos(event.pos())
            if group_id:
                self._drag_start = event.pos()
                self._drag_group_id = group_id
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if (
            self._drag_start is not None
            and self._drag_group_id is not None
            and (event.pos() - self._drag_start).manhattanLength() > 5
        ):
            mime = QMimeData()
            payload = json.dumps({
                "team_id": self._drag_group_id,   # keep key for MIME compatibility
                "from_block_id": self._block.block_id,
            }).encode("utf-8")
            mime.setData("application/x-team-chip", payload)

            drag = QDrag(event.widget())
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)

            self._drag_start = None
            self._drag_group_id = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self._drag_group_id = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if self._read_only:
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-team-chip"):
            try:
                data = json.loads(bytes(event.mimeData().data("application/x-team-chip")).decode())
                group_id = data.get("team_id")
                from_block_id = data.get("from_block_id")

                if from_block_id == self._block.block_id:
                    self._highlight = "green"
                    self.update()
                    event.accept()
                    return

                group = self._groups_by_id.get(group_id)
                if group is None:
                    event.ignore()
                    return

                current_used = self._used_seats()
                if group_id in [gid for gid, _ in self._group_chips]:
                    existing_count = next(
                        (c for gid, c in self._group_chips if gid == group_id), 0
                    )
                    current_used -= existing_count

                fits = current_used + group.size <= self._block.capacity
                self._highlight = "green" if fits else "red"
                self.update()
                if fits or self._allow_oversize:
                    event.accept()
                else:
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
                group_id = data.get("team_id")
                from_block_id = data.get("from_block_id")
                to_block_id = self._block.block_id

                self._highlight = None
                self.update()

                if from_block_id == to_block_id:
                    event.ignore()
                    return

                event.accept()
                self.team_dropped.emit(group_id, from_block_id, to_block_id)
            except Exception:
                event.ignore()
        else:
            event.ignore()
