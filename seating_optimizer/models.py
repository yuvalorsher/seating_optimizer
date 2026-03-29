from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

DAYS = [1, 2, 3, 4]


@dataclass(frozen=True)
class Block:
    block_id: str   # "B0"…"BN", row-major order over non-zero grid cells
    row: int
    col: int
    capacity: int

    def manhattan_distance(self, other: Block) -> int:
        return abs(self.row - other.row) + abs(self.col - other.col)

    def col_distance(self, other: Block) -> int:
        return abs(self.col - other.col)


@dataclass(frozen=True)
class Employee:
    employee_id: str   # unique identifier (index-prefixed slug of name)
    name: str
    group_id: str      # group this employee belongs to (original group name)
    department: str    # department this employee belongs to


@dataclass(frozen=True)
class Group:
    group_id: str
    name: str
    size: int                   # total number of employees
    departments: frozenset      # set of dept strings this group has members in


@dataclass
class GroupDayAssignment:
    group_id: str
    days: tuple       # (day_a, day_b) sorted, both in DAYS


@dataclass
class GroupBlockAssignment:
    group_id: str
    day: int
    block_id: str
    count: int        # number of employees from this group seated in this block


@dataclass
class Solution:
    solution_id: str
    created_at: str                           # ISO-8601
    cover_pair: tuple                         # (A, B) — days that together cover all groups
    day_assignments: list                     # list[GroupDayAssignment]
    block_assignments: list                   # list[GroupBlockAssignment]
    score: float
    score_breakdown: dict                     # {"compactness": float, "consistency": float}
    metadata: dict                            # solver_seed, iterations, derived_from, …

    # ------------------------------------------------------------------ helpers

    def get_day_view(self, day: int) -> dict:
        """Return {block_id: [(group_id, count), ...]} for the given day."""
        view: dict = {}
        for ba in self.block_assignments:
            if ba.day == day:
                view.setdefault(ba.block_id, []).append((ba.group_id, ba.count))
        return view

    def get_group_days(self, group_id: str) -> Optional[tuple]:
        for da in self.day_assignments:
            if da.group_id == group_id:
                return da.days
        return None

    def get_group_blocks(self, group_id: str, day: int) -> list:
        """Return [(block_id, count), ...] for this group on this day."""
        return [
            (ba.block_id, ba.count)
            for ba in self.block_assignments
            if ba.group_id == group_id and ba.day == day
        ]
