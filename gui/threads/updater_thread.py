from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from seating_optimizer.updater import SolutionUpdater


class UpdaterThread(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, blocks, old_teams, new_teams, base_solution, parent=None):
        super().__init__(parent)
        self._blocks = blocks
        self._old_teams = old_teams
        self._new_teams = new_teams
        self._base_solution = base_solution

    def run(self):
        try:
            updater = SolutionUpdater(self._blocks, self._old_teams, self._new_teams)
            result = updater.update(self._base_solution)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
