from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup


class DaySelectorWidget(QWidget):
    day_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, QPushButton] = {}

        for day in range(1, 5):
            btn = QPushButton(f"Day {day}")
            btn.setCheckable(True)
            btn.setFixedWidth(64)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #aaa; border-radius: 4px; padding: 4px 8px; }"
                "QPushButton:checked { background-color: #4A90D9; color: white; border-color: #2c6fad; }"
            )
            self._group.addButton(btn, day)
            self._buttons[day] = btn
            layout.addWidget(btn)

        self._buttons[1].setChecked(True)
        self._group.idClicked.connect(self._on_button_clicked)

    def _on_button_clicked(self, day_id: int):
        self.day_changed.emit(day_id)

    def set_day(self, day: int):
        if day in self._buttons:
            self._buttons[day].setChecked(True)
