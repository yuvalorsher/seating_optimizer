import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.constraints import (
    ALL_COVER_PAIRS,
    valid_day_combos_for_cover_pair,
    check_cover_constraint,
    check_dept_overlap_constraint,
    check_capacity_constraint,
    check_column_distance_constraint,
    all_dept_day_assignments,
)
from seating_optimizer.models import DAYS, GroupBlockAssignment, Block


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
    da = {"g1": (1, 3), "g2": (2, 4), "g3": (1, 2)}
    assert check_cover_constraint((1, 2), da) is True


def test_check_cover_constraint_fail():
    da = {"g1": (1, 3), "g2": (3, 4)}
    assert check_cover_constraint((1, 2), da) is False


def test_check_dept_overlap_pass():
    dept_map = {"D1": ["g1", "g2"]}
    da = {"g1": (1, 3), "g2": (1, 4)}  # share day 1
    assert check_dept_overlap_constraint(dept_map, da) is True


def test_check_dept_overlap_fail():
    dept_map = {"D1": ["g1", "g2"]}
    da = {"g1": (1, 2), "g2": (3, 4)}  # no shared day
    assert check_dept_overlap_constraint(dept_map, da) is False


def test_check_capacity_constraint_pass():
    blocks_by_id = {"B0": Block("B0", 0, 1, 10)}
    bas = [GroupBlockAssignment("g1", 1, "B0", 5), GroupBlockAssignment("g2", 1, "B0", 4)]
    assert check_capacity_constraint(1, bas, blocks_by_id) is True


def test_check_capacity_constraint_fail():
    blocks_by_id = {"B0": Block("B0", 0, 1, 8)}
    bas = [GroupBlockAssignment("g1", 1, "B0", 5), GroupBlockAssignment("g2", 1, "B0", 4)]
    assert check_capacity_constraint(1, bas, blocks_by_id) is False


def test_check_column_distance_pass():
    blocks_by_id = {
        "B0": Block("B0", 0, 0, 18),
        "B2": Block("B2", 2, 0, 8),
    }
    bas = [
        GroupBlockAssignment("g1", 1, "B0", 10),
        GroupBlockAssignment("g1", 1, "B2", 8),  # same column, distance 0
    ]
    assert check_column_distance_constraint(bas, blocks_by_id) is True


def test_check_column_distance_fail():
    blocks_by_id = {
        "B0": Block("B0", 0, 0, 18),
        "B1": Block("B1", 0, 6, 24),
    }
    bas = [
        GroupBlockAssignment("g1", 1, "B0", 10),
        GroupBlockAssignment("g1", 1, "B1", 8),  # distance 6 > 4
    ]
    assert check_column_distance_constraint(bas, blocks_by_id) is False


def test_all_dept_day_assignments():
    combos = all_dept_day_assignments((1, 2), ["D1", "D2"])
    assert len(combos) == 4  # 2^2
    for c in combos:
        assert set(c.keys()) == {"D1", "D2"}
        assert all(v in (1, 2) for v in c.values())
