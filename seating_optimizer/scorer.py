from __future__ import annotations
from collections import defaultdict

WEIGHT_COMPACTNESS = 0.6
WEIGHT_CONSISTENCY = 0.4


def score_compactness(
    day_assignments: dict,      # {group_id: (day_a, day_b)}
    block_assignments: list,    # list[GroupBlockAssignment]
) -> float:
    """
    Fraction of (group, day) pairs where the group is seated in exactly 1 block.
    Returns value in [0.0, 1.0]; higher is better.
    """
    group_day_blocks: dict = defaultdict(list)
    for ba in block_assignments:
        group_day_blocks[(ba.group_id, ba.day)].append(ba.block_id)

    total = len(day_assignments) * 2   # each group has 2 days
    if total == 0:
        return 1.0

    single = sum(
        1
        for group_id, (d1, d2) in day_assignments.items()
        for day in (d1, d2)
        if len(group_day_blocks[(group_id, day)]) == 1
    )
    return single / total


def score_consistency(
    day_assignments: dict,      # {group_id: (day_a, day_b)}
    block_assignments: list,    # list[GroupBlockAssignment]
) -> float:
    """
    Fraction of groups whose set of blocks is identical on both their days.
    Returns value in [0.0, 1.0]; higher is better.
    """
    if not day_assignments:
        return 1.0

    group_day_blockset: dict = defaultdict(dict)
    for ba in block_assignments:
        group_day_blockset[ba.group_id].setdefault(ba.day, set()).add(ba.block_id)

    consistent = 0
    for group_id, (d1, d2) in day_assignments.items():
        bs1 = frozenset(group_day_blockset[group_id].get(d1, set()))
        bs2 = frozenset(group_day_blockset[group_id].get(d2, set()))
        if bs1 and bs2 and bs1 == bs2:
            consistent += 1

    return consistent / len(day_assignments)


def compute_total_score(
    day_assignments: dict,
    block_assignments: list,
) -> tuple:
    """
    Returns (total_score, breakdown_dict).
    total_score = WEIGHT_COMPACTNESS * compactness + WEIGHT_CONSISTENCY * consistency
    """
    comp = score_compactness(day_assignments, block_assignments)
    cons = score_consistency(day_assignments, block_assignments)
    total = WEIGHT_COMPACTNESS * comp + WEIGHT_CONSISTENCY * cons
    return total, {"compactness": comp, "consistency": cons}
