from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from seating_optimizer.updater import SolutionUpdater


class UpdaterThread(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, blocks, groups_by_id, solution, size_overrides, parent=None):
        super().__init__(parent)
        self._blocks = blocks
        self._groups_by_id = groups_by_id
        self._solution = solution
        self._size_overrides = size_overrides

    def run(self):
        try:
            updater = SolutionUpdater(self._blocks, self._groups_by_id)
            result = updater.update(self._solution, self._size_overrides)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
