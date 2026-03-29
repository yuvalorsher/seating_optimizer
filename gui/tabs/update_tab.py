from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSpinBox, QFileDialog, QProgressBar,
    QFrame,
)

from seating_optimizer import persistence
from gui.app_state import AppState
from gui.pdf_exporter import export_pdf
from gui.threads.updater_thread import UpdaterThread


class UpdateTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._updated_solution = None
        self._thread = None
        self._orig_solution = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top bar: solution selector ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Base Solution:"))
        self._solution_combo = QComboBox()
        self._solution_combo.setMinimumWidth(360)
        top_bar.addWidget(self._solution_combo)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # --- Splitter: groups table | diff table ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: group sizes
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Group Sizes"))
        self._groups_table = self._make_groups_table()
        left_layout.addWidget(self._groups_table)
        splitter.addWidget(left)

        # Right: diff
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Changes"))
        self._diff_table = self._make_diff_table()
        right_layout.addWidget(self._diff_table)
        splitter.addWidget(right)

        splitter.setSizes([420, 580])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        # --- Progress bar ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # --- Bottom buttons ---
        btn_bar = QHBoxLayout()
        self._update_btn = QPushButton("Update Solution")
        self._update_btn.setEnabled(False)
        self._update_btn.setStyleSheet(
            "QPushButton { background: #4A90D9; color: white; font-weight: bold;"
            " padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #2c6fad; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        btn_bar.addWidget(self._update_btn)

        btn_bar.addSpacing(16)

        self._save_btn = QPushButton("Save New Solution")
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #27AE60; color: white; font-weight: bold;"
            " padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #1e8449; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        btn_bar.addWidget(self._save_btn)

        self._export_btn = QPushButton("Export PDF")
        self._export_btn.setEnabled(False)
        self._export_btn.setStyleSheet(
            "QPushButton { background: #8E44AD; color: white; font-weight: bold;"
            " padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #6c3483; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        btn_bar.addWidget(self._export_btn)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # --- Connections ---
        self._solution_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._update_btn.clicked.connect(self._on_update)
        self._save_btn.clicked.connect(self._on_save)
        self._export_btn.clicked.connect(self._on_export)

        state.solution_list_changed.connect(self._refresh_combo)
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

        if self._solution_combo.count() > 0:
            self._solution_combo.setCurrentIndex(0)
            self._load_solution(self._solution_combo.currentData())

    def _on_combo_changed(self, index: int):
        if self._refreshing_combo:
            return
        sol = self._solution_combo.currentData()
        if sol:
            self._load_solution(sol)

    def _load_solution(self, sol):
        self._orig_solution = sol
        self._updated_solution = None
        self._save_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._diff_table.setRowCount(0)
        self._populate_groups_table(sol)
        self._update_btn.setEnabled(sol is not None and bool(self._state.groups))

    # ------------------------------------------------------------------ groups table

    def _make_groups_table(self) -> QTableWidget:
        cols = ["Group", "Dept(s)", "Current Size", "New Size"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        return t

    def _populate_groups_table(self, solution):
        self._groups_table.setRowCount(0)
        if solution is None:
            return

        # Build {group_id: current size from solution} — use actual Group objects
        for da in solution.day_assignments:
            group = self._state.groups_by_id.get(da.group_id)
            if group is None:
                continue
            row = self._groups_table.rowCount()
            self._groups_table.insertRow(row)

            dept_str = ", ".join(sorted(group.departments))
            self._groups_table.setItem(row, 0, QTableWidgetItem(group.name))
            self._groups_table.setItem(row, 1, QTableWidgetItem(dept_str))
            self._groups_table.setItem(row, 2, QTableWidgetItem(str(group.size)))

            # Spin box for new size
            spin = QSpinBox()
            spin.setRange(1, 500)
            spin.setValue(group.size)
            spin.setFrame(False)
            # Store group_id in row data via item
            id_item = QTableWidgetItem(group.group_id)
            id_item.setData(Qt.UserRole, group.group_id)
            self._groups_table.setItem(row, 0, id_item)
            id_item.setText(group.name)
            self._groups_table.setCellWidget(row, 3, spin)

    # ------------------------------------------------------------------ update

    def _on_update(self):
        sol = self._orig_solution
        if sol is None or not self._state.groups:
            return

        # Collect size overrides (only where changed)
        size_overrides = {}
        for row in range(self._groups_table.rowCount()):
            gid_item = self._groups_table.item(row, 0)
            if gid_item is None:
                continue
            gid = gid_item.data(Qt.UserRole)
            spin = self._groups_table.cellWidget(row, 3)
            if gid is None or spin is None:
                continue
            group = self._state.groups_by_id.get(gid)
            if group and spin.value() != group.size:
                size_overrides[gid] = spin.value()

        self._update_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._thread = UpdaterThread(
            self._state.blocks,
            self._state.groups_by_id,
            sol,
            size_overrides,
            parent=self,
        )
        self._thread.finished.connect(self._on_update_done)
        self._thread.error.connect(self._on_update_error)
        self._thread.start()

    def _on_update_done(self, new_solution):
        self._progress.setVisible(False)
        self._update_btn.setEnabled(True)
        self._updated_solution = new_solution
        self._save_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._populate_diff_table(self._orig_solution, new_solution)

    def _on_update_error(self, msg: str):
        self._progress.setVisible(False)
        self._update_btn.setEnabled(True)
        QMessageBox.warning(self, "Update Failed", f"Could not compute updated solution:\n{msg}")

    # ------------------------------------------------------------------ diff table

    def _make_diff_table(self) -> QTableWidget:
        cols = ["Group", "Size", "Days", "Day 1 Blocks", "Day 2 Blocks"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        return t

    def _populate_diff_table(self, orig, updated):
        self._diff_table.setRowCount(0)

        orig_day_map = {da.group_id: da.days for da in orig.day_assignments}
        new_day_map = {da.group_id: da.days for da in updated.day_assignments}

        # Collect all group ids from both solutions
        all_gids = list(
            dict.fromkeys(
                list(orig_day_map.keys()) + list(new_day_map.keys())
            )
        )

        for gid in all_gids:
            group_orig = self._state.groups_by_id.get(gid)
            if group_orig is None:
                continue

            # New size: check spin boxes
            new_size = group_orig.size
            for row in range(self._groups_table.rowCount()):
                item = self._groups_table.item(row, 0)
                if item and item.data(Qt.UserRole) == gid:
                    spin = self._groups_table.cellWidget(row, 3)
                    if spin:
                        new_size = spin.value()
                    break

            orig_days = orig_day_map.get(gid)
            new_days = new_day_map.get(gid)

            if orig_days is None or new_days is None:
                continue

            d1_orig = orig.get_group_blocks(gid, orig_days[0])
            d2_orig = orig.get_group_blocks(gid, orig_days[1])
            d1_new = updated.get_group_blocks(gid, new_days[0])
            d2_new = updated.get_group_blocks(gid, new_days[1])

            def fmt(blocks):
                if not blocks:
                    return "?"
                if len(blocks) == 1:
                    return blocks[0][0]
                return "+".join(f"{bid}({cnt})" for bid, cnt in blocks)

            size_changed = new_size != group_orig.size
            days_changed = orig_days != new_days
            blocks_d1_changed = fmt(d1_orig) != fmt(d1_new)
            blocks_d2_changed = fmt(d2_orig) != fmt(d2_new)
            any_change = size_changed or days_changed or blocks_d1_changed or blocks_d2_changed

            row = self._diff_table.rowCount()
            self._diff_table.insertRow(row)

            name_item = QTableWidgetItem(group_orig.name)
            if any_change:
                name_item.setBackground(QColor("#fff3cd"))
            self._diff_table.setItem(row, 0, name_item)

            # Size cell
            size_str = (
                f"{group_orig.size} → {new_size}" if size_changed
                else str(group_orig.size)
            )
            size_item = QTableWidgetItem(size_str)
            if size_changed:
                size_item.setBackground(QColor("#cce5ff"))
            self._diff_table.setItem(row, 1, size_item)

            # Days cell
            days_str = (
                f"({orig_days[0]},{orig_days[1]}) → ({new_days[0]},{new_days[1]})"
                if days_changed
                else f"({new_days[0]},{new_days[1]})"
            )
            days_item = QTableWidgetItem(days_str)
            if days_changed:
                days_item.setBackground(QColor("#f8d7da"))
            self._diff_table.setItem(row, 2, days_item)

            # Day 1 blocks
            d1_str = (
                f"{fmt(d1_orig)} → {fmt(d1_new)}" if blocks_d1_changed
                else fmt(d1_new)
            )
            d1_item = QTableWidgetItem(d1_str)
            if blocks_d1_changed:
                d1_item.setBackground(QColor("#d4edda"))
            self._diff_table.setItem(row, 3, d1_item)

            # Day 2 blocks
            d2_str = (
                f"{fmt(d2_orig)} → {fmt(d2_new)}" if blocks_d2_changed
                else fmt(d2_new)
            )
            d2_item = QTableWidgetItem(d2_str)
            if blocks_d2_changed:
                d2_item.setBackground(QColor("#d4edda"))
            self._diff_table.setItem(row, 4, d2_item)

    # ------------------------------------------------------------------ save

    def _on_save(self):
        sol = self._updated_solution
        if sol is None:
            return
        try:
            persistence.save_solution(sol, self._state.solutions_dir)
            self._state.solutions.append(sol)
            self._state.solutions.sort(key=lambda s: s.score, reverse=True)
            self._state.solution_list_changed.emit()
            QMessageBox.information(
                self, "Saved",
                f"Solution {sol.solution_id} saved.\n"
                f"Score: {sol.score:.3f}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")

    # ------------------------------------------------------------------ export

    def _on_export(self):
        sol = self._updated_solution
        if sol is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            f"seating_{sol.solution_id}.pdf",
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        try:
            export_pdf(
                path,
                sol,
                self._state.blocks,
                self._state.groups_by_id,
                self._state.employees_by_group,
                self._state.group_color,
            )
            QMessageBox.information(self, "Exported", f"PDF saved to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", f"Failed to export PDF:\n{exc}")
