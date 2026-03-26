import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.models import Block, Team, TeamDayAssignment, TeamBlockAssignment, Solution, DAYS


def test_block_manhattan_distance():
    b1 = Block("B0", 0, 1, 9)
    b2 = Block("B1", 0, 3, 12)
    assert b1.manhattan_distance(b2) == 2

    b3 = Block("B2", 2, 0, 8)
    assert b1.manhattan_distance(b3) == 3


def test_block_frozen():
    b = Block("B0", 0, 1, 9)
    try:
        b.capacity = 99
        assert False, "Should have raised"
    except Exception:
        pass


def test_team_frozen():
    t = Team("t1", "T1", "D1", 5)
    try:
        t.size = 99
        assert False, "Should have raised"
    except Exception:
        pass


def test_solution_get_day_view():
    da = [TeamDayAssignment("t1", (1, 2))]
    ba = [
        TeamBlockAssignment("t1", 1, "B0"),
        TeamBlockAssignment("t1", 2, "B1"),
    ]
    sol = Solution("abc", "2024-01-01", (1, 2), da, ba, 0.8, {}, {})
    view = sol.get_day_view(1)
    assert view == {"B0": ["t1"]}
    view2 = sol.get_day_view(2)
    assert view2 == {"B1": ["t1"]}


def test_solution_get_team_block():
    da = [TeamDayAssignment("t1", (1, 3))]
    ba = [TeamBlockAssignment("t1", 1, "B0"), TeamBlockAssignment("t1", 3, "B0")]
    sol = Solution("abc", "2024-01-01", (1, 3), da, ba, 1.0, {}, {})
    assert sol.get_team_block("t1", 1) == "B0"
    assert sol.get_team_block("t1", 3) == "B0"
    assert sol.get_team_block("t1", 2) is None
