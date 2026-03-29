from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QSettings, QStandardPaths

from seating_optimizer.loader import (
    load_office_map, load_employees, get_groups,
    get_department_map, get_employees_by_group, load_cold_seats,
)
from seating_optimizer.persistence import list_solutions, load_solution
from gui.constants import DEPT_COLORS, DEFAULT_COLOR


def _bundled_data_path(filename: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent / "data"
    return base / filename


class AppState(QObject):
    solution_list_changed = Signal()
    active_solution_changed = Signal(object)
    active_day_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data
        self.blocks: list = []
        self.blocks_by_id: dict = {}
        self.employees: list = []
        self.groups: list = []
        self.groups_by_id: dict = {}
        self.employees_by_group: dict = {}   # {group_id: [Employee, ...]}
        self.dept_map: dict = {}             # {dept: [group_id, ...]}
        self.cold_seats: dict = {}       # {group_id: block_id}
        self.solutions: list = []
        self.active_solution = None
        self.active_day: int = 1

        # Settings-backed paths
        self._settings = QSettings("SeatingOptimizer", "SeatingOptimizer")
        default_map = str(_bundled_data_path("office_map.csv"))
        default_employees = str(_bundled_data_path("Employees list for seating with fake department.csv"))
        default_cold_seats = str(_bundled_data_path("cold_seats.csv"))
        self.office_map_path: str = self._settings.value("office_map_path", default_map)
        # Use new key; never fall back to old teams_path (different format)
        self.employees_path: str = self._settings.value("employees_path", default_employees)
        self.cold_seats_path: str = self._settings.value("cold_seats_path", default_cold_seats)

        # Solutions directory
        app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        self.solutions_dir = Path(app_data) / "solutions"
        self.solutions_dir.mkdir(parents=True, exist_ok=True)

        # Group color cache
        self._group_color_cache: dict[str, str] = {}

        # Load data if paths exist
        self._load_solutions_from_disk()
        try:
            self.load_data_files()
        except Exception:
            pass

    def set_office_map_path(self, path: str):
        self.office_map_path = path
        self._settings.setValue("office_map_path", path)

    def set_employees_path(self, path: str):
        self.employees_path = path
        self._settings.setValue("employees_path", path)

    def set_cold_seats_path(self, path: str):
        self.cold_seats_path = path
        self._settings.setValue("cold_seats_path", path)

    def load_data_files(self):
        self.blocks = load_office_map(self.office_map_path)
        self.blocks_by_id = {b.block_id: b for b in self.blocks}
        self.employees = load_employees(self.employees_path)
        self.groups = get_groups(self.employees)
        self.groups_by_id = {g.group_id: g for g in self.groups}
        self.employees_by_group = get_employees_by_group(self.employees)
        self.dept_map = get_department_map(self.groups)
        try:
            self.cold_seats = load_cold_seats(self.cold_seats_path)
        except Exception:
            self.cold_seats = {}

    def _load_solutions_from_disk(self):
        paths = list_solutions(self.solutions_dir)
        local_dir = Path(__file__).parent.parent / "solutions"
        if local_dir != self.solutions_dir and local_dir.exists():
            seen = {p.name for p in paths}
            for p in list_solutions(local_dir):
                if p.name not in seen:
                    paths.append(p)

        self.solutions = []
        for p in paths:
            try:
                self.solutions.append(load_solution(p))
            except Exception:
                pass
        self.solutions.sort(key=lambda s: s.score, reverse=True)

    def group_color(self, group_id: str) -> str:
        if group_id not in self._group_color_cache:
            idx = abs(hash(group_id)) % len(DEPT_COLORS)
            self._group_color_cache[group_id] = DEPT_COLORS[idx]
        return self._group_color_cache[group_id]

    def _bundled_data_path(self, filename: str) -> Path:
        return _bundled_data_path(filename)
