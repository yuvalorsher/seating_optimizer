from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame,
)

from seating_optimizer import persistence

from gui.app_state import AppState
from gui.widgets.day_selector import DaySelectorWidget
from gui.widgets.metrics_bar import MetricsBarWidget
from gui.widgets.office_grid import OfficeGridView


class VisualizeTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._modified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        top_bar.addWidget(QLabel("Solution:"))
        self._solution_combo = QComboBox()
        self._solution_combo.setMinimumWidth(320)
        top_bar.addWidget(self._solution_combo)

        top_bar.addSpacing(16)
        top_bar.addWidget(QLabel("Day:"))
        self._day_selector = DaySelectorWidget()
        top_bar.addWidget(self._day_selector)

        top_bar.addSpacing(16)
        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #4A90D9; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #2c6fad; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        top_bar.addWidget(self._save_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # --- Metrics bar ---
        self._metrics_bar = MetricsBarWidget()
        layout.addWidget(self._metrics_bar)

        # --- Department legend ---
        self._legend_widget = QWidget()
        self._legend_layout = QHBoxLayout(self._legend_widget)
        self._legend_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_layout.setSpacing(12)
        layout.addWidget(self._legend_widget)

        # --- Grid ---
        self._grid = OfficeGridView()
        layout.addWidget(self._grid, stretch=1)

        # --- Bottom tables splitter ---
        bottom_splitter = QSplitter(Qt.Horizontal)

        block_frame = QWidget()
        block_layout = QVBoxLayout(block_frame)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.addWidget(QLabel("Block Summary"))
        self._block_table = self._make_block_table()
        block_layout.addWidget(self._block_table)
        bottom_splitter.addWidget(block_frame)

        team_frame = QWidget()
        team_layout = QVBoxLayout(team_frame)
        team_layout.setContentsMargins(0, 0, 0, 0)
        team_layout.addWidget(QLabel("Team Schedule"))
        self._team_table = self._make_team_table()
        team_layout.addWidget(self._team_table)
        bottom_splitter.addWidget(team_frame)

        bottom_splitter.setSizes([400, 400])
        layout.addWidget(bottom_splitter)

        # Connect signals
        self._solution_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._day_selector.day_changed.connect(self._on_day_changed)
        self._save_btn.clicked.connect(self._on_save)
        self._grid.team_moved.connect(self._on_team_moved)

        state.solution_list_changed.connect(self._refresh_combo)
        state.active_solution_changed.connect(self._on_active_solution_changed)

        # Initial populate
        self._refreshing_combo = False
        self._refresh_combo()

    # ------------------------------------------------------------------ combo

    def _refresh_combo(self):
        self._refreshing_combo = True
        self._solution_combo.clear()
        for sol in self._state.solutions:
            label = f"Score: {sol.score:.3f}  |  {sol.solution_id}  |  {sol.created_at[:10]}"
            self._solution_combo.addItem(label, userData=sol)
        self._refreshing_combo = False

        # Restore active solution selection
        active = self._state.active_solution
        if active is not None:
            self._select_solution_in_combo(active)
            self._display_solution(active)
        elif self._solution_combo.count() > 0:
            self._refreshing_combo = True
            self._solution_combo.setCurrentIndex(0)
            self._refreshing_combo = False
            sol = self._solution_combo.currentData()
            if sol:
                self._state.active_solution = sol
                self._display_solution(sol)

    def _select_solution_in_combo(self, solution):
        """Set combo index without triggering _on_combo_changed (uses _refreshing_combo guard)."""
        self._refreshing_combo = True
        try:
            for i in range(self._solution_combo.count()):
                if self._solution_combo.itemData(i) is solution:
                    self._solution_combo.setCurrentIndex(i)
                    return
            # Fallback: match by id
            for i in range(self._solution_combo.count()):
                sol = self._solution_combo.itemData(i)
                if sol and sol.solution_id == solution.solution_id:
                    self._solution_combo.setCurrentIndex(i)
                    return
        finally:
            self._refreshing_combo = False

    def _on_combo_changed(self, index: int):
        if self._refreshing_combo:
            return
        sol = self._solution_combo.currentData()
        if sol is None:
            return
        self._state.active_solution = sol
        self._display_solution(sol)

    def _on_active_solution_changed(self, solution):
        if solution is None:
            self._metrics_bar.update_metrics(None)
            self._grid._scene.clear()
            return

        self._select_solution_in_combo(solution)
        self._display_solution(solution)

    def _display_solution(self, solution):
        """Update all UI elements for the given solution. No signal emits."""
        self._metrics_bar.update_metrics(solution)
        self._refresh_legend()
        self._load_grid()
        self._populate_block_table(solution)
        self._populate_team_table(solution)
        self._modified = False
        self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------ day

    def _on_day_changed(self, day: int):
        self._state.active_day = day
        self._state.active_day_changed.emit(day)
        self._grid.reload_day(day)
        sol = self._state.active_solution
        if sol:
            self._populate_block_table(sol)
            self._populate_team_table(sol)

    # ------------------------------------------------------------------ grid

    def _load_grid(self):
        sol = self._state.active_solution
        if sol is None:
            return
        self._grid.load(
            sol,
            self._state.active_day,
            self._state.blocks,
            self._state.teams_by_id,
            dept_color_fn=self._state.dept_color,
        )

    def _on_team_moved(self, team_id: str, from_block_id: str, to_block_id: str, day: int):
        self._modified = True
        self._save_btn.setEnabled(True)
        sol = self._state.active_solution
        if sol:
            self._metrics_bar.update_metrics(sol)
            self._populate_block_table(sol)
            self._populate_team_table(sol)

    # ------------------------------------------------------------------ legend

    def _refresh_legend(self):
        # Clear existing
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for dept in sorted(self._state.dept_map.keys()):
            color = self._state.dept_color(dept)
            swatch = QFrame()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background: {color}; border-radius: 3px; border: 1px solid #999;"
            )
            lbl = QLabel(dept)
            lbl.setStyleSheet("font-size: 11px;")

            self._legend_layout.addWidget(swatch)
            self._legend_layout.addWidget(lbl)
            self._legend_layout.addSpacing(4)

        self._legend_layout.addStretch()

    # ------------------------------------------------------------------ save

    def _on_save(self):
        sol = self._state.active_solution
        if sol is None:
            return
        try:
            persistence.save_solution(sol, self._state.solutions_dir)
            self._modified = False
            self._save_btn.setEnabled(False)
            self._state.solution_list_changed.emit()
            QMessageBox.information(self, "Saved", f"Solution {sol.solution_id} saved.")
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")

    # ------------------------------------------------------------------ tables

    def _make_block_table(self) -> QTableWidget:
        cols = ["Block", "Capacity", "Used", "Free", "Occupancy %", "Teams"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setMaximumHeight(180)
        return t

    def _make_team_table(self) -> QTableWidget:
        cols = ["Team", "Dept", "Size", "Day X", "Day Y", "Same Block"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setMaximumHeight(180)
        return t

    def _populate_block_table(self, solution):
        day = self._state.active_day
        day_view = solution.get_day_view(day)
        teams_by_id = self._state.teams_by_id

        self._block_table.setRowCount(0)
        for block in sorted(self._state.blocks, key=lambda b: b.block_id):
            team_ids = day_view.get(block.block_id, [])
            used = sum(teams_by_id[tid].size for tid in team_ids if tid in teams_by_id)
            free = block.capacity - used
            occ = used / block.capacity * 100 if block.capacity > 0 else 0
            team_names = ", ".join(
                teams_by_id[tid].name for tid in team_ids if tid in teams_by_id
            )

            row = self._block_table.rowCount()
            self._block_table.insertRow(row)
            self._block_table.setItem(row, 0, QTableWidgetItem(block.block_id))
            self._block_table.setItem(row, 1, QTableWidgetItem(str(block.capacity)))
            self._block_table.setItem(row, 2, QTableWidgetItem(str(used)))
            self._block_table.setItem(row, 3, QTableWidgetItem(str(free)))
            occ_item = QTableWidgetItem(f"{occ:.0f}%")
            if occ >= 95:
                occ_item.setBackground(QColor("#f8d7da"))
            elif occ >= 70:
                occ_item.setBackground(QColor("#fff3cd"))
            else:
                occ_item.setBackground(QColor("#d4edda"))
            self._block_table.setItem(row, 4, occ_item)
            self._block_table.setItem(row, 5, QTableWidgetItem(team_names))

    def _populate_team_table(self, solution):
        teams_by_id = self._state.teams_by_id
        self._team_table.setRowCount(0)

        for da in solution.day_assignments:
            team = teams_by_id.get(da.team_id)
            if team is None:
                continue
            d1, d2 = da.days
            b1 = solution.get_team_block(da.team_id, d1)
            b2 = solution.get_team_block(da.team_id, d2)
            same = b1 is not None and b2 is not None and b1 == b2

            row = self._team_table.rowCount()
            self._team_table.insertRow(row)
            self._team_table.setItem(row, 0, QTableWidgetItem(team.name))
            self._team_table.setItem(row, 1, QTableWidgetItem(team.department))
            self._team_table.setItem(row, 2, QTableWidgetItem(str(team.size)))
            self._team_table.setItem(row, 3, QTableWidgetItem(f"Day {d1} → {b1 or '?'}"))
            self._team_table.setItem(row, 4, QTableWidgetItem(f"Day {d2} → {b2 or '?'}"))
            same_item = QTableWidgetItem("Yes" if same else "No")
            same_item.setBackground(QColor("#d4edda") if same else QColor("#fff3cd"))
            self._team_table.setItem(row, 5, same_item)
