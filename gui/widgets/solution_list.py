from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox,
)


def _solution_label(solution) -> str:
    score = solution.score
    sid = solution.solution_id
    created = solution.created_at[:19].replace("T", " ")
    return f"Score: {score:.3f}  |  ID: {sid}  |  Created: {created}"


class SolutionListWidget(QWidget):
    solution_selected = Signal(object)
    visualize_requested = Signal(object)
    solution_saved = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(
            "QListWidget::item { padding: 6px 8px; }"
            "QListWidget::item:selected { background: #4A90D9; color: white; }"
        )
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip("Save selected solution to disk")
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setToolTip("Remove selected solution from list")
        self._visualize_btn = QPushButton("Visualize →")
        self._visualize_btn.setToolTip("Open selected solution in Visualize tab")

        for btn in [self._save_btn, self._delete_btn, self._visualize_btn]:
            btn.setEnabled(False)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

        # Connections
        self._list.currentItemChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._save_btn.clicked.connect(self._on_save)
        self._delete_btn.clicked.connect(self._on_delete)
        self._visualize_btn.clicked.connect(self._on_visualize)

    def _current_solution(self):
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_selection_changed(self, current, previous):
        has_sel = current is not None
        self._save_btn.setEnabled(has_sel)
        self._delete_btn.setEnabled(has_sel)
        self._visualize_btn.setEnabled(has_sel)
        if has_sel:
            sol = current.data(Qt.UserRole)
            self.solution_selected.emit(sol)

    def _on_double_click(self, item: QListWidgetItem):
        sol = item.data(Qt.UserRole)
        if sol is not None:
            self.visualize_requested.emit(sol)

    def _on_save(self):
        sol = self._current_solution()
        if sol is not None:
            self.solution_saved.emit(sol)

    def _on_delete(self):
        item = self._list.currentItem()
        if item is None:
            return
        sol = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self,
            "Delete Solution",
            f"Remove solution {sol.solution_id} from the list?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            row = self._list.row(item)
            self._list.takeItem(row)

    def _on_visualize(self):
        sol = self._current_solution()
        if sol is not None:
            self.visualize_requested.emit(sol)

    def populate(self, solutions: list):
        self._list.clear()
        for sol in solutions:
            self.add_solution(sol)

    def add_solution(self, solution):
        item = QListWidgetItem(_solution_label(solution))
        item.setData(Qt.UserRole, solution)
        self._list.insertItem(0, item)
