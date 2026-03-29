from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from seating_optimizer.solver import Solver


class SolverThread(QThread):
    progress = Signal(int, int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, blocks, groups, n_solutions=5, max_iters=20, seed=None,
                 cold_seats=None, parent=None):
        super().__init__(parent)
        self._blocks = blocks
        self._groups = groups
        self._n_solutions = n_solutions
        self._max_iters = max_iters
        self._seed = seed if seed and seed > 0 else None
        self._cold_seats = cold_seats or {}

    def run(self):
        try:
            solver = Solver(
                self._blocks,
                self._groups,
                n_solutions=self._n_solutions,
                max_iterations_per_cover=self._max_iters,
                seed=self._seed,
                cold_seats=self._cold_seats,
            )

            def _progress_cb(iteration: int, total: int):
                self.progress.emit(iteration, total)

            solutions = solver.solve(progress_callback=_progress_cb)
            self.finished.emit(solutions)
        except Exception as exc:
            self.error.emit(str(exc))
