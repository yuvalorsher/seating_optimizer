from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtGui import QColor

from gui.app_state import AppState
from seating_optimizer.models import DAYS

_EMPTY_BG = QColor("#F5F5F5")


class DeptOverlapTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._solution = None
        self._refreshing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Top bar ─────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Solution:"))
        self._sol_combo = QComboBox()
        self._sol_combo.setMinimumWidth(320)
        top.addWidget(self._sol_combo)
        top.addSpacing(16)
        top.addWidget(QLabel("Department:"))
        self._dept_combo = QComboBox()
        self._dept_combo.setMinimumWidth(200)
        top.addWidget(self._dept_combo)
        top.addStretch()
        layout.addLayout(top)

        # ── Table ────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(len(DAYS))
        self._table.setHorizontalHeaderLabels([f"Day {d}" for d in DAYS])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(True)
        self._table.verticalHeader().setMinimumWidth(140)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setAlternatingRowColors(False)
        layout.addWidget(self._table, stretch=1)

        # ── Signals ──────────────────────────────────────────────────────────
        self._sol_combo.currentIndexChanged.connect(self._on_solution_changed)
        self._dept_combo.currentIndexChanged.connect(self._on_dept_changed)
        self._state.solution_list_changed.connect(self._refresh_sol_combo)
        self._state.active_solution_changed.connect(self._on_active_solution_changed)

        self._refresh_sol_combo()

    # ── Solution combo ───────────────────────────────────────────────────────

    def _refresh_sol_combo(self):
        self._refreshing = True
        prev_id = self._solution.solution_id if self._solution else None
        self._sol_combo.clear()
        for sol in self._state.solutions:
            label = f"Score: {sol.score:.3f}  |  {sol.solution_id}  |  {sol.created_at[:10]}"
            self._sol_combo.addItem(label, userData=sol)
        self._refreshing = False
        restored = False
        if prev_id:
            for i in range(self._sol_combo.count()):
                if self._sol_combo.itemData(i).solution_id == prev_id:
                    self._sol_combo.setCurrentIndex(i)
                    restored = True
                    break
        if not restored and self._sol_combo.count() > 0:
            self._sol_combo.setCurrentIndex(0)
        self._on_solution_changed(self._sol_combo.currentIndex())

    def _on_active_solution_changed(self, solution):
        for i in range(self._sol_combo.count()):
            if self._sol_combo.itemData(i).solution_id == solution.solution_id:
                self._sol_combo.setCurrentIndex(i)
                return

    def _on_solution_changed(self, index: int):
        if self._refreshing:
            return
        self._solution = self._sol_combo.itemData(index) if index >= 0 else None
        self._refresh_dept_combo()

    # ── Department combo ─────────────────────────────────────────────────────

    def _refresh_dept_combo(self):
        self._refreshing = True
        prev_dept = self._dept_combo.currentText()
        self._dept_combo.clear()
        if self._solution is not None:
            for dept in sorted(self._state.dept_map.keys()):
                self._dept_combo.addItem(dept)
        self._refreshing = False
        if prev_dept:
            idx = self._dept_combo.findText(prev_dept)
            if idx >= 0:
                self._dept_combo.setCurrentIndex(idx)
        self._on_dept_changed(self._dept_combo.currentIndex())

    def _on_dept_changed(self, _index: int):
        if self._refreshing:
            return
        self._rebuild_table()

    # ── Table build ──────────────────────────────────────────────────────────

    def _rebuild_table(self):
        self._table.clearContents()
        self._table.setRowCount(0)

        if self._solution is None or self._dept_combo.count() == 0:
            return

        dept = self._dept_combo.currentText()
        group_ids = self._state.dept_map.get(dept, [])
        day_map = {da.group_id: set(da.days) for da in self._solution.day_assignments}
        dept_groups = [gid for gid in group_ids if gid in day_map]

        self._table.setRowCount(len(dept_groups))
        self._table.setVerticalHeaderLabels(dept_groups)

        for row, gid in enumerate(dept_groups):
            days = day_map[gid]
            q_color = QColor(self._state.group_color(gid))
            for col, day in enumerate(DAYS):
                item = QTableWidgetItem()
                item.setBackground(q_color if day in days else _EMPTY_BG)
                self._table.setItem(row, col, item)

        self._table.resizeRowsToContents()
