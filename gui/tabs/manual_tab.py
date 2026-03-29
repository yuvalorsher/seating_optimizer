from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from gui.app_state import AppState


class ManualTab(QWidget):
    """Placeholder — not yet updated for the new employee/group model."""

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel(
            "Manual seating tab is not yet available.\n"
            "It will be rebuilt for the new employee/group model in a future update."
        )
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #666; font-size: 13px;")
        layout.addWidget(lbl)

    # Keep stub so main_window.py doesn't crash when switching tabs
    @property
    def _grid(self):
        return _DummyGrid()


class _DummyGrid:
    def _fit_in_view(self):
        pass
