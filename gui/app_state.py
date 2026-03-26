from __future__ import annotations
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QSettings, QStandardPaths

from seating_optimizer.loader import load_office_map, load_teams, get_department_map
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
        self.teams: list = []
        self.teams_by_id: dict = {}
        self.blocks_by_id: dict = {}
        self.dept_map: dict = {}
        self.solutions: list = []
        self.active_solution = None
        self.active_day: int = 1

        # Settings-backed paths
        self._settings = QSettings("SeatingOptimizer", "SeatingOptimizer")
        default_map = str(_bundled_data_path("office_map.csv"))
        default_teams = str(_bundled_data_path("teams.json"))
        self.office_map_path: str = self._settings.value("office_map_path", default_map)
        self.teams_path: str = self._settings.value("teams_path", default_teams)

        # Solutions directory
        app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        self.solutions_dir = Path(app_data) / "solutions"
        self.solutions_dir.mkdir(parents=True, exist_ok=True)

        # Dept color cache
        self._dept_color_cache: dict[str, str] = {}

        # Load data if paths exist
        self._load_solutions_from_disk()
        try:
            self.load_data_files()
        except Exception:
            pass

    def set_office_map_path(self, path: str):
        self.office_map_path = path
        self._settings.setValue("office_map_path", path)

    def set_teams_path(self, path: str):
        self.teams_path = path
        self._settings.setValue("teams_path", path)

    def load_data_files(self):
        self.blocks = load_office_map(self.office_map_path)
        self.blocks_by_id = {b.block_id: b for b in self.blocks}
        self.teams = load_teams(self.teams_path)
        self.teams_by_id = {t.team_id: t for t in self.teams}
        self.dept_map = get_department_map(self.teams)

    def _load_solutions_from_disk(self):
        # Primary: app data dir (~/Library/Application Support/...)
        paths = list_solutions(self.solutions_dir)
        # Fallback: local solutions/ dir (Streamlit-era files)
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

    def dept_color(self, department: str) -> str:
        if department not in self._dept_color_cache:
            idx = abs(hash(department)) % len(DEPT_COLORS)
            self._dept_color_cache[department] = DEPT_COLORS[idx]
        return self._dept_color_cache[department]

    def _bundled_data_path(self, filename: str) -> Path:
        return _bundled_data_path(filename)
