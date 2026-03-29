from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QFileDialog,
)

from seating_optimizer import persistence

from gui.app_state import AppState
from gui.pdf_exporter import export_pdf
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
        self._export_btn = QPushButton("Export PDF")
        self._export_btn.setEnabled(False)
        self._export_btn.setStyleSheet(
            "QPushButton { background: #27AE60; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #1e8449; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        top_bar.addWidget(self._export_btn)

        top_bar.addSpacing(8)
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

        # --- Group legend ---
        self._legend_widget = QWidget()
        self._legend_layout = QHBoxLayout(self._legend_widget)
        self._legend_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_layout.setSpacing(12)
        layout.addWidget(self._legend_widget)

        # --- Zoom controls ---
        zoom_bar = QHBoxLayout()
        zoom_bar.setSpacing(4)
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedSize(28, 22)
        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedSize(28, 22)
        self._zoom_reset_btn = QPushButton("Fit")
        self._zoom_reset_btn.setFixedSize(36, 22)
        for btn in (self._zoom_in_btn, self._zoom_out_btn, self._zoom_reset_btn):
            btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 0 4px; border: 1px solid #bbb;"
                " border-radius: 3px; background: #f5f5f5; }"
                "QPushButton:hover { background: #e0e0e0; }"
            )
        zoom_bar.addWidget(self._zoom_in_btn)
        zoom_bar.addWidget(self._zoom_out_btn)
        zoom_bar.addWidget(self._zoom_reset_btn)
        zoom_bar.addStretch()
        layout.addLayout(zoom_bar)

        # --- Grid + bottom tables ---
        self._grid = OfficeGridView()

        bottom_splitter = QSplitter(Qt.Horizontal)

        block_frame = QWidget()
        block_layout = QVBoxLayout(block_frame)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.addWidget(QLabel("Block Summary"))
        self._block_table = self._make_block_table()
        block_layout.addWidget(self._block_table)
        bottom_splitter.addWidget(block_frame)

        group_frame = QWidget()
        group_layout = QVBoxLayout(group_frame)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.addWidget(QLabel("Group Schedule"))
        self._group_table = self._make_group_table()
        group_layout.addWidget(self._group_table)
        bottom_splitter.addWidget(group_frame)

        bottom_splitter.setSizes([400, 400])

        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(self._grid)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([500, 180])
        main_splitter.setChildrenCollapsible(False)
        layout.addWidget(main_splitter, stretch=1)

        # Connect signals
        self._solution_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._day_selector.day_changed.connect(self._on_day_changed)
        self._export_btn.clicked.connect(self._on_export_pdf)
        self._save_btn.clicked.connect(self._on_save)
        self._grid.team_moved.connect(self._on_group_moved)
        self._zoom_in_btn.clicked.connect(self._grid.zoom_in)
        self._zoom_out_btn.clicked.connect(self._grid.zoom_out)
        self._zoom_reset_btn.clicked.connect(self._grid.zoom_reset)

        state.solution_list_changed.connect(self._refresh_combo)
        state.active_solution_changed.connect(self._on_active_solution_changed)

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
        self._refreshing_combo = True
        try:
            for i in range(self._solution_combo.count()):
                if self._solution_combo.itemData(i) is solution:
                    self._solution_combo.setCurrentIndex(i)
                    return
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
            self._export_btn.setEnabled(False)
            return
        self._select_solution_in_combo(solution)
        self._display_solution(solution)

    def _display_solution(self, solution):
        self._metrics_bar.update_metrics(solution)
        self._refresh_legend()
        self._load_grid()
        self._populate_block_table(solution)
        self._populate_group_table(solution)
        self._modified = False
        self._save_btn.setEnabled(False)
        self._export_btn.setEnabled(True)

    # ------------------------------------------------------------------ day

    def _on_day_changed(self, day: int):
        self._state.active_day = day
        self._state.active_day_changed.emit(day)
        self._grid.reload_day(day)
        sol = self._state.active_solution
        if sol:
            self._populate_block_table(sol)
            self._populate_group_table(sol)

    # ------------------------------------------------------------------ grid

    def _load_grid(self):
        sol = self._state.active_solution
        if sol is None:
            return
        self._grid.load(
            sol,
            self._state.active_day,
            self._state.blocks,
            self._state.groups_by_id,
            group_color_fn=self._state.group_color,
            employees_by_group=self._state.employees_by_group,
        )

    def _on_group_moved(self, group_id: str, from_block_id: str, to_block_id: str, day: int):
        self._modified = True
        self._save_btn.setEnabled(True)
        sol = self._state.active_solution
        if sol:
            self._metrics_bar.update_metrics(sol)
            self._populate_block_table(sol)
            self._populate_group_table(sol)

    # ------------------------------------------------------------------ legend

    def _refresh_legend(self):
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for group in sorted(self._state.groups, key=lambda g: g.group_id):
            color = self._state.group_color(group.group_id)
            swatch = QFrame()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background: {color}; border-radius: 3px; border: 1px solid #999;"
            )
            lbl = QLabel(group.name)
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

    # ------------------------------------------------------------------ export

    def _on_export_pdf(self):
        sol = self._state.active_solution
        if sol is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            f"seating_{sol.solution_id[:8]}.pdf",
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

    # ------------------------------------------------------------------ tables

    def _make_block_table(self) -> QTableWidget:
        cols = ["Block", "Capacity", "Used", "Free", "Occupancy %", "Groups"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        return t

    def _make_group_table(self) -> QTableWidget:
        cols = ["Group", "Dept(s)", "Size", "Day X", "Day Y", "Single Block"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        return t

    def _populate_block_table(self, solution):
        day = self._state.active_day
        day_view = solution.get_day_view(day)

        self._block_table.setRowCount(0)
        for block in sorted(self._state.blocks, key=lambda b: b.block_id):
            chips = day_view.get(block.block_id, [])
            used = sum(count for _, count in chips)
            free = block.capacity - used
            occ = used / block.capacity * 100 if block.capacity > 0 else 0
            group_names = ", ".join(
                f"{gid}({cnt})" for gid, cnt in chips
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
            self._block_table.setItem(row, 5, QTableWidgetItem(group_names))

    def _populate_group_table(self, solution):
        groups_by_id = self._state.groups_by_id
        self._group_table.setRowCount(0)

        for da in solution.day_assignments:
            group = groups_by_id.get(da.group_id)
            if group is None:
                continue
            d1, d2 = da.days
            blocks_d1 = solution.get_group_blocks(da.group_id, d1)
            blocks_d2 = solution.get_group_blocks(da.group_id, d2)

            def fmt_blocks(blocks):
                if not blocks:
                    return "?"
                if len(blocks) == 1:
                    return blocks[0][0]
                return "+".join(f"{bid}({cnt})" for bid, cnt in blocks)

            single = (
                len(blocks_d1) == 1 and len(blocks_d2) == 1
                and blocks_d1[0][0] == blocks_d2[0][0]
            )

            row = self._group_table.rowCount()
            self._group_table.insertRow(row)
            dept_str = ", ".join(sorted(group.departments))
            self._group_table.setItem(row, 0, QTableWidgetItem(group.name))
            self._group_table.setItem(row, 1, QTableWidgetItem(dept_str))
            self._group_table.setItem(row, 2, QTableWidgetItem(str(group.size)))
            self._group_table.setItem(row, 3, QTableWidgetItem(f"Day {d1} → {fmt_blocks(blocks_d1)}"))
            self._group_table.setItem(row, 4, QTableWidgetItem(f"Day {d2} → {fmt_blocks(blocks_d2)}"))
            same_item = QTableWidgetItem("Yes" if single else "No")
            same_item.setBackground(QColor("#d4edda") if single else QColor("#fff3cd"))
            self._group_table.setItem(row, 5, same_item)
