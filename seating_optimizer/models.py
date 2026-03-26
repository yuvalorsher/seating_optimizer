from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

DAYS = [1, 2, 3, 4]


@dataclass(frozen=True)
class Block:
    block_id: str   # "B0"…"B5", row-major order over non-zero grid cells
    row: int
    col: int
    capacity: int

    def manhattan_distance(self, other: Block) -> int:
        return abs(self.row - other.row) + abs(self.col - other.col)


@dataclass(frozen=True)
class Team:
    team_id: str
    name: str
    department: str
    size: int


@dataclass
class TeamDayAssignment:
    team_id: str
    days: tuple  # (day_a, day_b) sorted, both in DAYS


@dataclass
class TeamBlockAssignment:
    team_id: str
    day: int
    block_id: str


@dataclass
class Solution:
    solution_id: str
    created_at: str                           # ISO-8601
    cover_pair: tuple                         # (A, B) — days that together cover all teams
    day_assignments: list                     # list[TeamDayAssignment]
    block_assignments: list                   # list[TeamBlockAssignment]
    score: float
    score_breakdown: dict                     # {"consistency": float, "dept_proximity": float}
    metadata: dict                            # solver_seed, iterations, derived_from, …

    # ------------------------------------------------------------------ helpers

    def get_day_view(self, day: int) -> dict:
        """Return {block_id: [team_id, ...]} for the given day."""
        view: dict = {}
        for ba in self.block_assignments:
            if ba.day == day:
                view.setdefault(ba.block_id, []).append(ba.team_id)
        return view

    def get_team_days(self, team_id: str) -> Optional[tuple]:
        for da in self.day_assignments:
            if da.team_id == team_id:
                return da.days
        return None

    def get_team_block(self, team_id: str, day: int) -> Optional[str]:
        for ba in self.block_assignments:
            if ba.team_id == team_id and ba.day == day:
                return ba.block_id
        return None
