from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QMenuBar, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from gui.app_state import AppState
from gui.tabs.solve_tab import SolveTab
from gui.tabs.visualize_tab import VisualizeTab
from gui.tabs.update_tab import UpdateTab
from gui.tabs.manual_tab import ManualTab
from gui.tabs.dept_overlap_tab import DeptOverlapTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Seating Optimizer")

        self._state = AppState(self)

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._solve_tab = SolveTab(self._state)
        self._visualize_tab = VisualizeTab(self._state)
        self._update_tab = UpdateTab(self._state)
        self._dept_overlap_tab = DeptOverlapTab(self._state)
        self._manual_tab = ManualTab(self._state)

        self._tabs.addTab(self._solve_tab, "Solve")
        self._tabs.addTab(self._visualize_tab, "Visualize")
        self._tabs.addTab(self._update_tab, "Update")
        self._tabs.addTab(self._dept_overlap_tab, "Dept Overlap")
        self._tabs.addTab(self._manual_tab, "Manual")

        self._solve_tab.visualize_requested.connect(self._on_visualize_requested)
        self._state.solution_list_changed.connect(self._on_solution_list_changed)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._update_status_bar()

        self._build_menu()

    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        open_map_action = QAction("Open Office Map CSV…", self)
        open_map_action.triggered.connect(self._open_office_map)
        file_menu.addAction(open_map_action)

        open_employees_action = QAction("Open Employees CSV…", self)
        open_employees_action.triggered.connect(self._open_employees_csv)
        file_menu.addAction(open_employees_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _open_office_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Office Map CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_office_map_path(path)
            try:
                self._state.load_data_files()
                self._update_status_bar()
            except Exception as exc:
                QMessageBox.warning(self, "Load Error", f"Failed to load office map:\n{exc}")

    def _open_employees_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Employees CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_employees_path(path)
            try:
                self._state.load_data_files()
                self._update_status_bar()
            except Exception as exc:
                QMessageBox.warning(self, "Load Error", f"Failed to load employees file:\n{exc}")

    def _show_about(self):
        QMessageBox.about(
            self,
            "About Seating Optimizer",
            "<b>Seating Optimizer</b><br>"
            "A tool for optimizing office seating assignments.<br><br>"
            "Assigns employee groups to seating blocks across multiple days "
            "while satisfying cover, department-overlap, and column-distance constraints.",
        )

    def _on_tab_changed(self, index: int):
        if index == 1:  # Visualize tab
            self._visualize_tab._grid._fit_in_view()
        elif index == 4:  # Manual tab (placeholder — safe stub)
            self._manual_tab._grid._fit_in_view()

    def _on_visualize_requested(self, solution):
        self._state.active_solution = solution
        self._state.active_solution_changed.emit(solution)
        self._tabs.setCurrentWidget(self._visualize_tab)

    def _on_solution_list_changed(self):
        self._update_status_bar()

    def _update_status_bar(self):
        blocks_info = f"{len(self._state.blocks)} blocks" if self._state.blocks else "no map"
        groups_info = f"{len(self._state.groups)} groups, {len(self._state.employees)} employees" \
            if self._state.groups else "no employees"
        solutions_info = f"{len(self._state.solutions)} solutions"
        self._status.showMessage(
            f"Office map: {blocks_info}  |  {groups_info}  |  Solutions: {solutions_info}"
        )
