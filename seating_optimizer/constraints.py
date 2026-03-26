from __future__ import annotations
from itertools import combinations

from .models import DAYS

# All C(4,2) = 6 cover-pair candidates
ALL_COVER_PAIRS: list = list(combinations(DAYS, 2))


def valid_day_combos_for_cover_pair(cover_pair: tuple) -> list:
    """
    Return all 2-day combinations from DAYS that include at least one day
    from cover_pair.  For cover_pair=(1,2), the excluded combo is (3,4).
    """
    a, b = cover_pair
    excluded = tuple(sorted(d for d in DAYS if d != a and d != b))
    return [c for c in combinations(DAYS, 2) if c != excluded]


def check_cover_constraint(
    cover_pair: tuple,
    day_assignments: dict,  # {team_id: (day_a, day_b)}
) -> bool:
    """Every team must attend at least one of the two cover days."""
    a, b = cover_pair
    for days in day_assignments.values():
        if a not in days and b not in days:
            return False
    return True


def check_capacity_constraint(
    day: int,
    block_assignments_for_day: dict,   # {team_id: block_id}
    teams_by_id: dict,
    blocks_by_id: dict,
) -> bool:
    """Sum of team sizes per block on a given day must not exceed capacity."""
    load: dict = {}
    for team_id, block_id in block_assignments_for_day.items():
        load[block_id] = load.get(block_id, 0) + teams_by_id[team_id].size
    for block_id, used in load.items():
        if used > blocks_by_id[block_id].capacity:
            return False
    return True


def check_all_hard_constraints(
    cover_pair: tuple,
    day_assignments: dict,              # {team_id: (day_a, day_b)}
    block_assignments: dict,            # {(team_id, day): block_id}
    teams_by_id: dict,
    blocks_by_id: dict,
) -> tuple:
    """
    Run all hard constraint checks.
    Returns (is_valid, list_of_violation_messages).
    """
    violations = []

    # Constraint: each team comes exactly 2 days
    for team_id, days in day_assignments.items():
        if len(set(days)) != 2:
            violations.append(f"Team {team_id} does not have exactly 2 distinct days: {days}")

    # Constraint: cover pair
    if not check_cover_constraint(cover_pair, day_assignments):
        violations.append(f"Cover constraint violated: not all teams attend cover days {cover_pair}")

    # Constraint: capacity per day
    for day in DAYS:
        day_block_map = {
            team_id: block_id
            for (team_id, d), block_id in block_assignments.items()
            if d == day
        }
        if not check_capacity_constraint(day, day_block_map, teams_by_id, blocks_by_id):
            violations.append(f"Capacity constraint violated on day {day}")

    return (len(violations) == 0, violations)
