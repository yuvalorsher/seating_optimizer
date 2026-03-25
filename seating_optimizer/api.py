from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .io import load_office_map, load_teams
from .models import Configuration, OfficeMap, Team
from .optimizer import find_all_configurations


def configuration_to_dict(
    cfg: Configuration,
    teams: Dict[str, Team],
) -> Dict:
    """Convert a Configuration to a JSON-serializable dict."""
    assignments = []
    for a in cfg.assignments:
        team = teams[a.team_id]
        assignments.append(
            {
                "team_id": team.id,
                "team_name": team.name,
                "department": team.department,
                "size": team.size,
                "day1": a.day1,
                "block1": a.block1_id,
                "day2": a.day2,
                "block2": a.block2_id,
            }
        )

    # Per-day teams
    days: Dict[str, Dict] = {}
    per_day: Dict[int, List[str]] = {}
    for a in cfg.assignments:
        per_day.setdefault(a.day1, []).append(a.team_id)
        per_day.setdefault(a.day2, []).append(a.team_id)

    for day, team_ids in per_day.items():
        days[str(day)] = {
            "teams": team_ids,
        }

    return {
        "assignments": assignments,
        "days": days,
    }


def save_configurations(
    configs: Iterable[Configuration],
    teams: Dict[str, Team],
    path: str | Path,
) -> None:
    """Serialize configurations to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = [configuration_to_dict(cfg, teams) for cfg in configs]
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_optimization_from_files(
    teams_path: str | Path,
    office_map_path: str | Path,
    max_solutions: Optional[int] = None,
) -> Dict[str, object]:
    """High-level helper to run optimization from input files.

    Returns a summary dict containing counts and the raw Configuration list.
    """
    teams: Dict[str, Team] = load_teams(teams_path)
    office_map: OfficeMap = load_office_map(office_map_path)

    configs: List[Configuration] = find_all_configurations(
        teams=teams,
        office_map=office_map,
        max_solutions=max_solutions,
    )

    return {
        "teams": teams,
        "office_map": office_map,
        "configurations": configs,
    }

