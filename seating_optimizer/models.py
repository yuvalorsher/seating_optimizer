from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


Day = int  # Values 1..5


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    size: int
    department: str


@dataclass(frozen=True)
class Block:
    id: str
    row: int
    col: int
    capacity: int


@dataclass
class OfficeMap:
    blocks: Dict[str, Block]
    rows: int
    cols: int

    def all_blocks(self) -> List[Block]:
        return list(self.blocks.values())


@dataclass(frozen=True)
class Assignment:
    team_id: str
    day1: Day
    block1_id: str
    day2: Day
    block2_id: str


@dataclass
class Configuration:
    assignments: List[Assignment]

    # Derived / convenience structures are computed on demand
    def teams_on_day(self) -> Dict[Day, List[str]]:
        per_day: Dict[Day, List[str]] = {}
        for a in self.assignments:
            per_day.setdefault(a.day1, []).append(a.team_id)
            per_day.setdefault(a.day2, []).append(a.team_id)
        return per_day

    def per_day_block_usage(
        self,
    ) -> Dict[Day, Dict[str, List[Tuple[str, int]]]]:
        """
        Returns mapping: day -> block_id -> list of (team_id, team_size_placeholder).
        The actual team sizes should be joined externally if needed.
        """
        result: Dict[Day, Dict[str, List[Tuple[str, int]]]] = {}
        for a in self.assignments:
            for day, block_id in ((a.day1, a.block1_id), (a.day2, a.block2_id)):
                day_map = result.setdefault(day, {})
                day_map.setdefault(block_id, []).append((a.team_id, 0))
        return result

