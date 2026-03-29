from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QPushButton,
    QSpinBox, QFileDialog, QProgressBar, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
)

from seating_optimizer import persistence

from gui.app_state import AppState
from gui.threads.solver_thread import SolverThread
from gui.widgets.solution_list import SolutionListWidget


class SolveTab(QWidget):
    visualize_requested = Signal(object)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._thread: SolverThread | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Left panel ---
        left_box = QGroupBox("Settings")
        left_box.setFixedWidth(260)
        left_layout = QVBoxLayout(left_box)
        left_layout.setSpacing(6)

        # Office Map path
        left_layout.addWidget(QLabel("Office Map:"))
        self._map_path_lbl = QLabel(self._short_path(state.office_map_path))
        self._map_path_lbl.setWordWrap(True)
        self._map_path_lbl.setStyleSheet("color: #555; font-size: 10px;")
        left_layout.addWidget(self._map_path_lbl)
        map_browse_btn = QPushButton("Browse…")
        map_browse_btn.clicked.connect(self._browse_map)
        left_layout.addWidget(map_browse_btn)

        # Employees CSV path
        left_layout.addWidget(QLabel("Employees CSV:"))
        self._employees_path_lbl = QLabel(self._short_path(state.employees_path))
        self._employees_path_lbl.setWordWrap(True)
        self._employees_path_lbl.setStyleSheet("color: #555; font-size: 10px;")
        left_layout.addWidget(self._employees_path_lbl)
        employees_browse_btn = QPushButton("Browse…")
        employees_browse_btn.clicked.connect(self._browse_employees)
        left_layout.addWidget(employees_browse_btn)

        left_layout.addSpacing(8)

        # Number of solutions
        left_layout.addWidget(QLabel("Solutions to find:"))
        self._n_solutions_spin = QSpinBox()
        self._n_solutions_spin.setRange(1, 20)
        self._n_solutions_spin.setValue(5)
        left_layout.addWidget(self._n_solutions_spin)

        # Max iterations
        left_layout.addWidget(QLabel("Max iterations/cover:"))
        self._max_iters_spin = QSpinBox()
        self._max_iters_spin.setRange(4, 200)
        self._max_iters_spin.setValue(20)
        left_layout.addWidget(self._max_iters_spin)

        # Seed
        left_layout.addWidget(QLabel("Seed (0=random):"))
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 9999)
        self._seed_spin.setValue(0)
        left_layout.addWidget(self._seed_spin)

        left_layout.addSpacing(12)

        # Run button
        self._run_btn = QPushButton("Run Solver")
        self._run_btn.setStyleSheet(
            "QPushButton { background: #27AE60; color: white; font-size: 14px; "
            "font-weight: bold; padding: 10px; border-radius: 6px; }"
            "QPushButton:hover { background: #219a52; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        self._run_btn.clicked.connect(self._run_solver)
        left_layout.addWidget(self._run_btn)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        left_layout.addWidget(self._progress)

        left_layout.addStretch()
        layout.addWidget(left_box)

        # --- Right panel ---
        right_splitter = QSplitter(Qt.Vertical)

        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        self._solution_list = SolutionListWidget()
        results_layout.addWidget(self._solution_list)
        right_splitter.addWidget(results_box)

        schedule_box = QGroupBox("Schedule")
        schedule_layout = QVBoxLayout(schedule_box)
        self._schedule_table = self._make_schedule_table()
        schedule_layout.addWidget(self._schedule_table)
        right_splitter.addWidget(schedule_box)

        right_splitter.setSizes([300, 250])
        layout.addWidget(right_splitter, stretch=1)

        # Connect solution list signals
        self._solution_list.solution_saved.connect(self._on_solution_saved)
        self._solution_list.visualize_requested.connect(self._on_visualize_requested)
        self._solution_list.solution_selected.connect(self._on_solution_selected)

    def _short_path(self, path: str) -> str:
        if len(path) > 40:
            return "…" + path[-38:]
        return path

    def _browse_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Office Map CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_office_map_path(path)
            self._map_path_lbl.setText(self._short_path(path))
            self._reload_data()

    def _browse_employees(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Employees CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_employees_path(path)
            self._employees_path_lbl.setText(self._short_path(path))
            self._reload_data()

    def _reload_data(self):
        try:
            self._state.load_data_files()
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load data files:\n{exc}")

    def _run_solver(self):
        if not self._state.blocks or not self._state.groups:
            QMessageBox.warning(self, "No Data", "Please load office map and employees CSV first.")
            return

        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        seed = self._seed_spin.value()
        self._thread = SolverThread(
            blocks=self._state.blocks,
            groups=self._state.groups,
            n_solutions=self._n_solutions_spin.value(),
            max_iters=self._max_iters_spin.value(),
            seed=seed if seed > 0 else None,
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_solver_finished)
        self._thread.error.connect(self._on_solver_error)
        self._thread.start()

    def _on_progress(self, done: int, total: int):
        if total > 0:
            pct = int(done * 100 / total)
            self._progress.setValue(pct)

    def _on_solver_finished(self, solutions: list):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._solution_list.populate(solutions)

    def _on_solver_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Solver Error", f"The solver encountered an error:\n{msg}")

    def _on_solution_saved(self, solution):
        try:
            persistence.save_solution(solution, self._state.solutions_dir)
            self._state.solutions.insert(0, solution)
            self._state.solution_list_changed.emit()
            QMessageBox.information(self, "Saved", f"Solution {solution.solution_id} saved.")
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")

    def _on_visualize_requested(self, solution):
        self._state.active_solution = solution
        self._state.active_solution_changed.emit(solution)
        self.visualize_requested.emit(solution)

    def _on_solution_selected(self, solution):
        self._populate_schedule(solution)

    def _make_schedule_table(self) -> QTableWidget:
        cols = ["Group", "Dept(s)", "Size", "Day 1", "Day 2", "Single Block"]
        table = QTableWidget(0, len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        return table

    def _populate_schedule(self, solution):
        table = self._schedule_table
        table.setRowCount(0)
        groups_by_id = self._state.groups_by_id

        for da in solution.day_assignments:
            group = groups_by_id.get(da.group_id)
            if group is None:
                continue
            row = table.rowCount()
            table.insertRow(row)

            d1, d2 = da.days
            blocks_d1 = solution.get_group_blocks(da.group_id, d1)
            blocks_d2 = solution.get_group_blocks(da.group_id, d2)

            def fmt_blocks(blocks):
                if not blocks:
                    return "?"
                if len(blocks) == 1:
                    return blocks[0][0]
                return "+".join(f"{bid}({cnt})" for bid, cnt in blocks)

            single_block = (
                len(blocks_d1) == 1 and len(blocks_d2) == 1
                and blocks_d1[0][0] == blocks_d2[0][0]
            )

            dept_str = ", ".join(sorted(group.departments))
            table.setItem(row, 0, QTableWidgetItem(group.name))
            table.setItem(row, 1, QTableWidgetItem(dept_str))
            table.setItem(row, 2, QTableWidgetItem(str(group.size)))
            table.setItem(row, 3, QTableWidgetItem(f"Day {d1} → {fmt_blocks(blocks_d1)}"))
            table.setItem(row, 4, QTableWidgetItem(f"Day {d2} → {fmt_blocks(blocks_d2)}"))

            same_item = QTableWidgetItem("Yes" if single_block else "No")
            if single_block:
                same_item.setBackground(QColor("#d4edda"))
            else:
                same_item.setBackground(QColor("#fff3cd"))
            table.setItem(row, 5, same_item)

        table.resizeRowsToContents()
