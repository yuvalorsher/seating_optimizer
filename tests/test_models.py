import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.models import (
    Block, Employee, Group, GroupDayAssignment, GroupBlockAssignment, Solution, DAYS
)


def test_block_manhattan_distance():
    b1 = Block("B0", 0, 1, 9)
    b2 = Block("B1", 0, 3, 12)
    assert b1.manhattan_distance(b2) == 2

    b3 = Block("B2", 2, 0, 8)
    assert b1.manhattan_distance(b3) == 3


def test_block_col_distance():
    b1 = Block("B0", 0, 0, 18)
    b2 = Block("B1", 0, 6, 24)
    assert b1.col_distance(b2) == 6


def test_block_frozen():
    b = Block("B0", 0, 1, 9)
    try:
        b.capacity = 99
        assert False, "Should have raised"
    except Exception:
        pass


def test_employee_frozen():
    e = Employee("e0_alice", "Alice", "AI", "R&D")
    try:
        e.name = "Bob"
        assert False, "Should have raised"
    except Exception:
        pass


def test_group_frozen():
    g = Group("AI", "AI", 10, frozenset(["R&D"]))
    try:
        g.size = 99
        assert False, "Should have raised"
    except Exception:
        pass


def test_solution_get_day_view():
    da = [GroupDayAssignment("AI", (1, 2))]
    ba = [
        GroupBlockAssignment("AI", 1, "B0", 10),
        GroupBlockAssignment("AI", 2, "B1", 10),
    ]
    sol = Solution("abc", "2024-01-01", (1, 2), da, ba, 0.8, {}, {})
    view1 = sol.get_day_view(1)
    assert view1 == {"B0": [("AI", 10)]}
    view2 = sol.get_day_view(2)
    assert view2 == {"B1": [("AI", 10)]}


def test_solution_get_group_blocks():
    da = [GroupDayAssignment("AI", (1, 3))]
    ba = [
        GroupBlockAssignment("AI", 1, "B0", 10),
        GroupBlockAssignment("AI", 3, "B0", 10),
    ]
    sol = Solution("abc", "2024-01-01", (1, 3), da, ba, 1.0, {}, {})
    assert sol.get_group_blocks("AI", 1) == [("B0", 10)]
    assert sol.get_group_blocks("AI", 3) == [("B0", 10)]
    assert sol.get_group_blocks("AI", 2) == []


def test_solution_get_group_days():
    da = [GroupDayAssignment("AI", (2, 4))]
    ba = []
    sol = Solution("abc", "2024-01-01", (2, 4), da, ba, 0.5, {}, {})
    assert sol.get_group_days("AI") == (2, 4)
    assert sol.get_group_days("Unknown") is None
