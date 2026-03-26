from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QFileDialog, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMessageBox,
)

from seating_optimizer.loader import load_teams
from seating_optimizer import persistence

from gui.app_state import AppState
from gui.threads.updater_thread import UpdaterThread
from gui.widgets.day_selector import DaySelectorWidget
from gui.widgets.office_grid import OfficeGridView


class UpdateTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._new_teams: list = []
        self._new_teams_path: str = ""
        self._updated_solution = None
        self._thread: UpdaterThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        top_bar.addWidget(QLabel("Base Solution:"))
        self._base_combo = QComboBox()
        self._base_combo.setMinimumWidth(280)
        top_bar.addWidget(self._base_combo)

        top_bar.addSpacing(12)
        top_bar.addWidget(QLabel("New Teams JSON:"))
        self._new_teams_lbl = QLabel("(not selected)")
        self._new_teams_lbl.setStyleSheet("color: #888; font-size: 10px;")
        top_bar.addWidget(self._new_teams_lbl)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_new_teams)
        top_bar.addWidget(browse_btn)

        top_bar.addSpacing(12)
        self._run_btn = QPushButton("Run Updater")
        self._run_btn.setEnabled(False)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #E67E22; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #ca6f1e; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        self._run_btn.clicked.connect(self._run_updater)
        top_bar.addWidget(self._run_btn)

        top_bar.addSpacing(12)
        self._save_btn = QPushButton("Save Updated Solution")
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #4A90D9; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #2c6fad; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        self._save_btn.clicked.connect(self._save_updated)
        top_bar.addWidget(self._save_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # --- Diff table ---
        diff_box = QGroupBox("Team Size Changes")
        diff_layout = QVBoxLayout(diff_box)
        self._diff_table = self._make_diff_table()
        diff_layout.addWidget(self._diff_table)
        layout.addWidget(diff_box)

        # --- Grid splitter + day selectors ---
        day_bar = QHBoxLayout()
        day_bar.addWidget(QLabel("Day:"))
        self._day_selector = DaySelectorWidget()
        self._day_selector.day_changed.connect(self._on_day_changed)
        day_bar.addWidget(self._day_selector)
        day_bar.addStretch()
        layout.addLayout(day_bar)

        grid_splitter = QSplitter(Qt.Horizontal)

        before_box = QGroupBox("Before")
        before_layout = QVBoxLayout(before_box)
        self._before_grid = OfficeGridView()
        self._before_grid.set_read_only(True)
        before_layout.addWidget(self._before_grid)
        grid_splitter.addWidget(before_box)

        after_box = QGroupBox("After")
        after_layout = QVBoxLayout(after_box)
        self._after_grid = OfficeGridView()
        self._after_grid.set_read_only(True)
        after_layout.addWidget(self._after_grid)
        grid_splitter.addWidget(after_box)

        layout.addWidget(grid_splitter, stretch=1)

        # Populate combo from state
        state.solution_list_changed.connect(self._refresh_combo)
        self._base_combo.currentIndexChanged.connect(self._on_base_changed)
        self._refresh_combo()

    # ------------------------------------------------------------------ combo

    def _refresh_combo(self):
        self._base_combo.clear()
        for sol in self._state.solutions:
            label = f"Score: {sol.score:.3f}  |  {sol.solution_id}  |  {sol.created_at[:10]}"
            self._base_combo.addItem(label, userData=sol)
        self._check_run_ready()

    def _on_base_changed(self, index: int):
        self._check_run_ready()
        self._compute_diff()

    # ------------------------------------------------------------------ browse

    def _browse_new_teams(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select New Teams JSON", "", "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            self._new_teams = load_teams(path)
            self._new_teams_path = path
            short = path if len(path) <= 40 else "…" + path[-38:]
            self._new_teams_lbl.setText(short)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load teams:\n{exc}")
            return
        self._check_run_ready()
        self._compute_diff()

    def _check_run_ready(self):
        has_base = self._base_combo.currentData() is not None
        has_new = bool(self._new_teams)
        self._run_btn.setEnabled(has_base and has_new)

    # ------------------------------------------------------------------ diff

    def _compute_diff(self):
        self._diff_table.setRowCount(0)
        base_sol = self._base_combo.currentData()
        if base_sol is None or not self._new_teams:
            return

        old_by_id = self._state.teams_by_id
        new_by_id = {t.team_id: t for t in self._new_teams}
        all_ids = set(old_by_id) | set(new_by_id)

        # Determine violated teams (new size > block capacity on any day)
        # For simplicity, mark violated if team size increased and > block capacity
        violated_ids: set[str] = set()
        for ba in base_sol.block_assignments:
            block = self._state.blocks_by_id.get(ba.block_id)
            team = new_by_id.get(ba.team_id)
            if block and team and team.size > block.capacity:
                violated_ids.add(ba.team_id)

        for tid in sorted(all_ids):
            old_team = old_by_id.get(tid)
            new_team = new_by_id.get(tid)

            old_size = old_team.size if old_team else 0
            new_size = new_team.size if new_team else 0
            delta = new_size - old_size
            dept = (new_team or old_team).department
            name = (new_team or old_team).name

            if delta == 0 and tid not in violated_ids:
                continue  # Only show changed rows

            status = "Removed" if new_size == 0 else ("Added" if old_size == 0 else "Changed")
            if tid in violated_ids:
                status = "Violated"

            row = self._diff_table.rowCount()
            self._diff_table.insertRow(row)
            self._diff_table.setItem(row, 0, QTableWidgetItem(name))
            self._diff_table.setItem(row, 1, QTableWidgetItem(dept))
            self._diff_table.setItem(row, 2, QTableWidgetItem(str(old_size)))
            self._diff_table.setItem(row, 3, QTableWidgetItem(str(new_size)))
            delta_item = QTableWidgetItem(f"{delta:+d}" if delta != 0 else "0")
            self._diff_table.setItem(row, 4, delta_item)
            status_item = QTableWidgetItem(status)
            self._diff_table.setItem(row, 5, status_item)

            if tid in violated_ids:
                for col in range(6):
                    item = self._diff_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#f8d7da"))
            elif delta != 0:
                for col in range(6):
                    item = self._diff_table.item(row, col)
                    if item:
                        item.setBackground(QColor("#fff3cd"))

    # ------------------------------------------------------------------ run updater

    def _run_updater(self):
        base_sol = self._base_combo.currentData()
        if base_sol is None or not self._new_teams:
            return

        self._run_btn.setEnabled(False)
        old_teams = self._state.teams

        self._thread = UpdaterThread(
            blocks=self._state.blocks,
            old_teams=old_teams,
            new_teams=self._new_teams,
            base_solution=base_sol,
        )
        self._thread.finished.connect(self._on_updater_finished)
        self._thread.error.connect(self._on_updater_error)
        self._thread.start()

    def _on_updater_finished(self, updated_solution):
        self._run_btn.setEnabled(True)
        self._updated_solution = updated_solution

        base_sol = self._base_combo.currentData()
        new_teams_by_id = {t.team_id: t for t in self._new_teams}

        day = self._state.active_day

        # Load before grid (original solution, original teams)
        self._before_grid.load(
            base_sol,
            day,
            self._state.blocks,
            self._state.teams_by_id,
            dept_color_fn=self._state.dept_color,
        )

        # Load after grid (updated solution, new teams)
        self._after_grid.load(
            updated_solution,
            day,
            self._state.blocks,
            new_teams_by_id,
            dept_color_fn=self._state.dept_color,
        )

        self._save_btn.setEnabled(True)

    def _on_updater_error(self, msg: str):
        self._run_btn.setEnabled(True)
        QMessageBox.critical(self, "Updater Error", f"The updater encountered an error:\n{msg}")

    # ------------------------------------------------------------------ day

    def _on_day_changed(self, day: int):
        self._state.active_day = day
        if self._before_grid._solution:
            self._before_grid.reload_day(day)
        if self._after_grid._solution:
            self._after_grid.reload_day(day)

    # ------------------------------------------------------------------ save

    def _save_updated(self):
        if self._updated_solution is None:
            return
        try:
            persistence.save_solution(self._updated_solution, self._state.solutions_dir)
            self._state.solutions.insert(0, self._updated_solution)
            self._state.solution_list_changed.emit()
            QMessageBox.information(
                self, "Saved",
                f"Updated solution {self._updated_solution.solution_id} saved."
            )
            self._save_btn.setEnabled(False)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")

    # ------------------------------------------------------------------ table helpers

    def _make_diff_table(self) -> QTableWidget:
        cols = ["Team", "Dept", "Old Size", "New Size", "Delta", "Status"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setMaximumHeight(160)
        return t
