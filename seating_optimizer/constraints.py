from __future__ import annotations
from itertools import combinations

from .models import DAYS

# All C(4,2) = 6 cover-pair candidates
ALL_COVER_PAIRS: list = list(combinations(DAYS, 2))

MAX_COL_DISTANCE = 4   # maximum column distance between blocks used by the same group


def valid_day_combos_for_cover_pair(cover_pair: tuple) -> list:
    """
    Return all 2-day combinations from DAYS that include at least one day
    from cover_pair.  For cover_pair=(1,2), the excluded combo is (3,4).
    """
    a, b = cover_pair
    excluded = tuple(sorted(d for d in DAYS if d != a and d != b))
    return [c for c in combinations(DAYS, 2) if c != excluded]


def all_dept_day_assignments(cover_pair: tuple, depts: list) -> list:
    """
    Enumerate all ways to assign a common day (from cover_pair) to each dept.
    Returns list of dicts {dept: day}.
    With N depts and 2 cover days, yields 2^N combinations.
    """
    a, b = cover_pair
    results = [{}]
    for dept in depts:
        new_results = []
        for partial in results:
            for day in (a, b):
                new_partial = dict(partial)
                new_partial[dept] = day
                new_results.append(new_partial)
        results = new_results
    return results


def check_cover_constraint(
    cover_pair: tuple,
    day_assignments: dict,   # {group_id: (day_a, day_b)}
) -> bool:
    """Every group must attend at least one of the two cover days."""
    a, b = cover_pair
    for days in day_assignments.values():
        if a not in days and b not in days:
            return False
    return True


def check_dept_overlap_constraint(
    dept_map: dict,           # {dept: [group_id, ...]}
    day_assignments: dict,    # {group_id: (day_a, day_b)}
) -> bool:
    """
    For each dept, every pair of groups with members in that dept must share
    at least one common day.
    """
    for dept, group_ids in dept_map.items():
        present = [gid for gid in group_ids if gid in day_assignments]
        for gid1, gid2 in combinations(present, 2):
            days1 = set(day_assignments[gid1])
            days2 = set(day_assignments[gid2])
            if not days1 & days2:
                return False
    return True


def check_capacity_constraint(
    day: int,
    block_assignments_for_day: list,   # list[GroupBlockAssignment] for this day
    blocks_by_id: dict,
) -> bool:
    """Sum of counts per block on a given day must not exceed capacity."""
    load: dict = {}
    for ba in block_assignments_for_day:
        load[ba.block_id] = load.get(ba.block_id, 0) + ba.count
    for block_id, used in load.items():
        if used > blocks_by_id[block_id].capacity:
            return False
    return True


def check_column_distance_constraint(
    block_assignments: list,   # all GroupBlockAssignment objects
    blocks_by_id: dict,
    max_col_dist: int = MAX_COL_DISTANCE,
) -> bool:
    """
    For each (group, day), all blocks used by the group must be within
    max_col_dist columns of each other.
    """
    from collections import defaultdict
    group_day_cols: dict = defaultdict(set)
    for ba in block_assignments:
        col = blocks_by_id[ba.block_id].col
        group_day_cols[(ba.group_id, ba.day)].add(col)

    for (group_id, day), cols in group_day_cols.items():
        if max(cols) - min(cols) > max_col_dist:
            return False
    return True


def check_cold_seats_constraint(
    block_assignments: list,   # list[GroupBlockAssignment]
    cold_seats: dict,          # {group_id: required_block_id}
) -> bool:
    """
    For each group in cold_seats, all of its block assignments must use the
    required block and only that block.
    """
    from collections import defaultdict
    group_blocks: dict = defaultdict(set)
    for ba in block_assignments:
        if ba.group_id in cold_seats:
            group_blocks[ba.group_id].add(ba.block_id)
    for group_id, required_block in cold_seats.items():
        used = group_blocks.get(group_id, set())
        if used and used != {required_block}:
            return False
    return True


def check_all_hard_constraints(
    cover_pair: tuple,
    day_assignments: dict,       # {group_id: (day_a, day_b)}
    block_assignments: list,     # list[GroupBlockAssignment]
    groups_by_id: dict,
    blocks_by_id: dict,
    dept_map: dict,
    cold_seats: dict = None,     # {group_id: required_block_id}
) -> tuple:
    """
    Run all hard constraint checks.
    Returns (is_valid, list_of_violation_messages).
    """
    violations = []

    # Constraint: each group comes exactly 2 days
    for group_id, days in day_assignments.items():
        if len(set(days)) != 2:
            violations.append(f"Group {group_id} does not have exactly 2 distinct days: {days}")

    # Constraint: cover pair
    if not check_cover_constraint(cover_pair, day_assignments):
        violations.append(f"Cover constraint violated: not all groups attend cover days {cover_pair}")

    # Constraint: dept overlap
    if not check_dept_overlap_constraint(dept_map, day_assignments):
        violations.append("Dept overlap constraint violated: some dept pair shares no day")

    # Constraint: capacity per day
    for day in DAYS:
        day_bas = [ba for ba in block_assignments if ba.day == day]
        if not check_capacity_constraint(day, day_bas, blocks_by_id):
            violations.append(f"Capacity constraint violated on day {day}")

    # Constraint: column distance
    if not check_column_distance_constraint(block_assignments, blocks_by_id):
        violations.append("Column distance constraint violated: group members >4 columns apart")

    # Constraint: cold seats
    if cold_seats:
        if not check_cold_seats_constraint(block_assignments, cold_seats):
            violations.append("Cold-seats constraint violated: group not in required block")

    return (len(violations) == 0, violations)
