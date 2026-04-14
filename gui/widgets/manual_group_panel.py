from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QColor, QDrag, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMenu, QAbstractItemView,
)


class ManualGroupPanel(QWidget):
    """Right-side panel showing all groups with their day assignments and seated counts.

    Supports drag initiation (to blocks or pending panel) and right-click context menus.
    """

    day_assignment_requested = Signal(str, int)   # group_id, day
    clear_group_requested = Signal(str)           # group_id

    def __init__(self, group_color_fn, parent=None):
        super().__init__(parent)
        self._group_color_fn = group_color_fn
        self._group_ids: list[str] = []  # ordered list matching table rows

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QLabel("Groups")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        self._table = _DragTable(self)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Group", "Dept", "Day I", "Day II", "Seated"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(False)
        self._table.setColumnWidth(0, 110)
        self._table.setColumnWidth(1, 80)
        self._table.setColumnWidth(2, 42)
        self._table.setColumnWidth(3, 42)
        self._table.setColumnWidth(4, 60)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_right_click)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.verticalHeader().hide()
        layout.addWidget(self._table)

        self.setMinimumWidth(200)

    def refresh(self, manual_state, groups_by_id: dict, current_day: int = 1) -> None:
        """Rebuild table rows from current ManualState."""
        self._table.setRowCount(0)
        self._group_ids = []

        sorted_groups = sorted(groups_by_id.values(), key=lambda g: g.name)
        self._table.setRowCount(len(sorted_groups))

        for row, group in enumerate(sorted_groups):
            gid = group.group_id
            self._group_ids.append(gid)
            days = manual_state.day_assignments.get(gid, [])

            # Group name (colored background)
            name_item = QTableWidgetItem(gid)
            name_item.setData(Qt.UserRole, gid)
            color_hex = self._group_color_fn(gid)
            bg = QColor(color_hex)
            bg.setAlpha(60)
            name_item.setBackground(QBrush(bg))
            self._table.setItem(row, 0, name_item)

            # Dept
            depts = ", ".join(sorted(group.departments))
            dept_item = QTableWidgetItem(depts)
            dept_item.setData(Qt.UserRole, gid)
            self._table.setItem(row, 1, dept_item)

            # Day I
            day1_item = QTableWidgetItem(str(days[0]) if len(days) >= 1 else "—")
            day1_item.setTextAlignment(Qt.AlignCenter)
            day1_item.setData(Qt.UserRole, gid)
            self._table.setItem(row, 2, day1_item)

            # Day II
            day2_item = QTableWidgetItem(str(days[1]) if len(days) >= 2 else "—")
            day2_item.setTextAlignment(Qt.AlignCenter)
            day2_item.setData(Qt.UserRole, gid)
            self._table.setItem(row, 3, day2_item)

            # Seated on current day / group size (e.g. "5/11")
            seated_today = manual_state.get_seated_count(gid, current_day)
            seated_text = f"{seated_today}/{group.size}"
            seated_item = QTableWidgetItem(seated_text)
            seated_item.setTextAlignment(Qt.AlignCenter)
            seated_item.setData(Qt.UserRole, gid)
            if current_day in days and seated_today == group.size:
                seated_item.setForeground(QBrush(QColor("#27AE60")))
            elif seated_today > 0:
                seated_item.setForeground(QBrush(QColor("#F5A623")))
            self._table.setItem(row, 4, seated_item)

        # Pass group_ids to drag table
        self._table.set_group_ids(self._group_ids)

    def _group_id_at_row(self, row: int) -> str | None:
        if 0 <= row < len(self._group_ids):
            return self._group_ids[row]
        return None

    def _on_right_click(self, pos: QPoint) -> None:
        row = self._table.rowAt(pos.y())
        group_id = self._group_id_at_row(row)
        if group_id is None:
            return

        # Read current day assignments from the table
        day1_text = self._table.item(row, 2).text() if self._table.item(row, 2) else "—"
        day2_text = self._table.item(row, 3).text() if self._table.item(row, 3) else "—"
        assigned_days = set()
        for t in (day1_text, day2_text):
            try:
                assigned_days.add(int(t))
            except ValueError:
                pass

        menu = QMenu(self)
        add_menu = menu.addMenu("Add to day")
        for day in range(1, 5):
            action = add_menu.addAction(f"Day {day}")
            action.setEnabled(day not in assigned_days and len(assigned_days) < 2)
            action.triggered.connect(
                lambda checked=False, gid=group_id, d=day: self.day_assignment_requested.emit(gid, d)
            )
        menu.addSeparator()
        clear_action = menu.addAction("Clear all group assignments")
        clear_action.triggered.connect(
            lambda checked=False, gid=group_id: self.clear_group_requested.emit(gid)
        )
        menu.exec(self._table.viewport().mapToGlobal(pos))


class _DragTable(QTableWidget):
    """QTableWidget that initiates custom MIME drags for group rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos: QPoint | None = None
        self._drag_group_id: str | None = None
        self._group_ids: list[str] = []

    def set_group_ids(self, group_ids: list[str]) -> None:
        self._group_ids = group_ids

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            row = self.rowAt(event.pos().y())
            if 0 <= row < len(self._group_ids):
                self._drag_start_pos = event.pos()
                self._drag_group_id = self._group_ids[row]
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start_pos is not None
            and self._drag_group_id is not None
            and (event.pos() - self._drag_start_pos).manhattanLength() > 8
        ):
            mime = QMimeData()
            payload = json.dumps({
                "team_id": self._drag_group_id,
                "from_block_id": None,
                "source": "panel",
            }).encode("utf-8")
            mime.setData("application/x-team-chip", payload)
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
            self._drag_start_pos = None
            self._drag_group_id = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_group_id = None
        super().mouseReleaseEvent(event)
