import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.constraints import (
    ALL_COVER_PAIRS,
    valid_day_combos_for_cover_pair,
    check_cover_constraint,
    check_capacity_constraint,
    check_all_hard_constraints,
)
from seating_optimizer.models import DAYS


def test_all_cover_pairs():
    assert len(ALL_COVER_PAIRS) == 6
    assert (1, 2) in ALL_COVER_PAIRS
    assert (3, 4) in ALL_COVER_PAIRS


def test_valid_day_combos_for_cover_pair():
    combos = valid_day_combos_for_cover_pair((1, 2))
    assert len(combos) == 5
    assert (3, 4) not in combos
    assert (1, 2) in combos
    assert (1, 3) in combos

    combos34 = valid_day_combos_for_cover_pair((3, 4))
    assert (1, 2) not in combos34
    assert len(combos34) == 5


def test_check_cover_constraint_pass():
    day_assignments = {
        "t1": (1, 3),  # has day 1
        "t2": (2, 4),  # has day 2
        "t3": (1, 2),  # has both
    }
    assert check_cover_constraint((1, 2), day_assignments) is True


def test_check_cover_constraint_fail():
    day_assignments = {
        "t1": (1, 3),
        "t2": (3, 4),  # has neither 1 nor 2
    }
    assert check_cover_constraint((1, 2), day_assignments) is False


def test_check_capacity_constraint_pass():
    from seating_optimizer.models import Block, Team
    blocks_by_id = {"B0": Block("B0", 0, 1, 10)}
    teams_by_id = {"t1": Team("t1", "T1", "D1", 5), "t2": Team("t2", "T2", "D1", 4)}
    assignments = {"t1": "B0", "t2": "B0"}
    assert check_capacity_constraint(1, assignments, teams_by_id, blocks_by_id) is True


def test_check_capacity_constraint_fail():
    from seating_optimizer.models import Block, Team
    blocks_by_id = {"B0": Block("B0", 0, 1, 8)}
    teams_by_id = {"t1": Team("t1", "T1", "D1", 5), "t2": Team("t2", "T2", "D1", 4)}
    assignments = {"t1": "B0", "t2": "B0"}
    assert check_capacity_constraint(1, assignments, teams_by_id, blocks_by_id) is False
