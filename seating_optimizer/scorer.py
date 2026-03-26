from __future__ import annotations
from itertools import combinations

WEIGHT_CONSISTENCY = 0.6
WEIGHT_DEPT_PROXIMITY = 0.4
MAX_MANHATTAN = 8  # max Manhattan distance on a 5×5 grid


def score_consistency(
    day_assignments: dict,   # {team_id: (day_a, day_b)}
    block_assignments: dict, # {(team_id, day): block_id}
) -> float:
    """
    Fraction of teams whose block is identical on both their days.
    Returns value in [0.0, 1.0].
    """
    if not day_assignments:
        return 0.0
    consistent = 0
    for team_id, (d1, d2) in day_assignments.items():
        b1 = block_assignments.get((team_id, d1))
        b2 = block_assignments.get((team_id, d2))
        if b1 is not None and b2 is not None and b1 == b2:
            consistent += 1
    return consistent / len(day_assignments)


def score_dept_proximity(
    day_assignments: dict,
    block_assignments: dict,
    teams_by_id: dict,
    blocks_by_id: dict,
    dept_map: dict,          # {dept_id: [Team, ...]}
) -> float:
    """
    Per (day, dept): 1 - avg_pairwise_manhattan / MAX_MANHATTAN.
    Average over all (day, dept) pairs that have >=2 teams present.
    Returns value in [0.0, 1.0]; higher is better (teams sit close together).
    If no dept has >=2 teams on any day, returns 1.0.
    """
    from .models import DAYS

    total_score = 0.0
    count = 0

    for day in DAYS:
        for dept, teams in dept_map.items():
            present = [
                t for t in teams
                if day in day_assignments.get(t.team_id, ())
            ]
            if len(present) < 2:
                continue
            pairs = list(combinations(present, 2))
            distances = []
            for t1, t2 in pairs:
                b1 = block_assignments.get((t1.team_id, day))
                b2 = block_assignments.get((t2.team_id, day))
                if b1 is None or b2 is None:
                    continue
                dist = blocks_by_id[b1].manhattan_distance(blocks_by_id[b2])
                distances.append(dist)
            if distances:
                avg_dist = sum(distances) / len(distances)
                total_score += 1.0 - (avg_dist / MAX_MANHATTAN)
                count += 1

    return total_score / count if count > 0 else 1.0


def compute_total_score(
    day_assignments: dict,
    block_assignments: dict,
    teams_by_id: dict,
    blocks_by_id: dict,
    dept_map: dict,
) -> tuple:
    """
    Returns (total_score, breakdown_dict).
    total_score = WEIGHT_CONSISTENCY * consistency + WEIGHT_DEPT_PROXIMITY * dept_proximity
    """
    cons = score_consistency(day_assignments, block_assignments)
    prox = score_dept_proximity(
        day_assignments, block_assignments, teams_by_id, blocks_by_id, dept_map
    )
    total = WEIGHT_CONSISTENCY * cons + WEIGHT_DEPT_PROXIMITY * prox
    return total, {"consistency": cons, "dept_proximity": prox}
