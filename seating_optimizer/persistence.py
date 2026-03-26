from __future__ import annotations
import json
from pathlib import Path

from .models import Solution, TeamDayAssignment, TeamBlockAssignment

SOLUTIONS_DIR = Path("solutions")


def save_solution(solution: Solution, directory: Path = SOLUTIONS_DIR) -> Path:
    """Serialize Solution to JSON and write to directory/solution_<id>.json."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"solution_{solution.solution_id}.json"
    with open(path, "w") as f:
        json.dump(solution_to_dict(solution), f, indent=2)
    return path


def load_solution(path) -> Solution:
    """Deserialize a Solution from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return solution_from_dict(data)


def list_solutions(directory: Path = SOLUTIONS_DIR) -> list:
    """Return all solution JSON paths sorted by modification time (newest first)."""
    directory = Path(directory)
    if not directory.exists():
        return []
    paths = sorted(
        directory.glob("solution_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return paths


def solution_to_dict(solution: Solution) -> dict:
    return {
        "solution_id": solution.solution_id,
        "created_at": solution.created_at,
        "cover_pair": list(solution.cover_pair),
        "day_assignments": [
            {"team_id": da.team_id, "days": list(da.days)}
            for da in solution.day_assignments
        ],
        "block_assignments": [
            {"team_id": ba.team_id, "day": ba.day, "block_id": ba.block_id}
            for ba in solution.block_assignments
        ],
        "score": solution.score,
        "score_breakdown": solution.score_breakdown,
        "metadata": solution.metadata,
    }


def solution_from_dict(d: dict) -> Solution:
    return Solution(
        solution_id=d["solution_id"],
        created_at=d["created_at"],
        cover_pair=tuple(d["cover_pair"]),
        day_assignments=[
            TeamDayAssignment(team_id=da["team_id"], days=tuple(da["days"]))
            for da in d["day_assignments"]
        ],
        block_assignments=[
            TeamBlockAssignment(team_id=ba["team_id"], day=ba["day"], block_id=ba["block_id"])
            for ba in d["block_assignments"]
        ],
        score=d["score"],
        score_breakdown=d["score_breakdown"],
        metadata=d.get("metadata", {}),
    )
