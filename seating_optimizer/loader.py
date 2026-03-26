from __future__ import annotations
import csv
import json
from pathlib import Path

from .models import Block, Team


def load_office_map(path: str) -> list:
    """
    Parse a CSV where non-zero values are seating block capacities.
    Returns list[Block] in row-major order, IDs B0, B1, …
    """
    blocks = []
    block_idx = 0
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row_idx, row in enumerate(reader):
            for col_idx, cell in enumerate(row):
                capacity = int(cell.strip())
                if capacity > 0:
                    blocks.append(Block(
                        block_id=f"B{block_idx}",
                        row=row_idx,
                        col=col_idx,
                        capacity=capacity,
                    ))
                    block_idx += 1
    return blocks


def load_teams(path: str) -> list:
    """
    Parse teams.json.
    Expected format: {"t1": {"name": "T1", "size": 5, "department": "D1"}, ...}
    Returns list[Team].
    """
    with open(path) as f:
        raw = json.load(f)
    teams = []
    for team_id, data in raw.items():
        teams.append(Team(
            team_id=team_id,
            name=data["name"],
            department=data["department"],
            size=int(data["size"]),
        ))
    return teams


def get_department_map(teams: list) -> dict:
    """Return {dept_id: [Team, ...]} grouping."""
    dept_map: dict = {}
    for team in teams:
        dept_map.setdefault(team.department, []).append(team)
    return dept_map
