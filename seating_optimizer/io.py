from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict

from .models import Block, OfficeMap, Team


def load_teams(path: str | Path) -> Dict[str, Team]:
    """Load teams from a JSON file.

    Expected structure:
    {
        "team_id": {
            "name": "Team Name",
            "size": 5,
            "department": "Dept"
        },
        ...
    }
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("Teams JSON must be an object mapping team_id to team info.")

    teams: Dict[str, Team] = {}
    for team_id, info in raw.items():
        if not isinstance(info, dict):
            raise ValueError(f"Team '{team_id}' entry must be an object.")

        try:
            name = str(info["name"])
            size = int(info["size"])
            department = str(info.get("department", ""))
        except KeyError as e:
            raise ValueError(f"Missing required field {e} for team '{team_id}'.") from e

        if size <= 0:
            raise ValueError(f"Team '{team_id}' must have positive size, got {size}.")

        teams[team_id] = Team(
            id=team_id,
            name=name,
            size=size,
            department=department,
        )

    return teams


def load_office_map(path: str | Path) -> OfficeMap:
    """Load office map from a CSV file.

    Each cell contains:
    - 0 for non-seatable blocks
    - positive integer for capacity of that block
    """
    p = Path(path)
    rows: list[list[int]] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            rows.append([int(cell) for cell in row])

    if not rows:
        raise ValueError("Office map CSV is empty.")

    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)

    blocks: Dict[str, Block] = {}
    for r_idx, row in enumerate(rows):
        for c_idx, value in enumerate(row):
            if value <= 0:
                continue
            block_id = f"r{r_idx}_c{c_idx}"
            blocks[block_id] = Block(
                id=block_id,
                row=r_idx,
                col=c_idx,
                capacity=value,
            )

    return OfficeMap(blocks=blocks, rows=n_rows, cols=n_cols)

