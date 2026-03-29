import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from seating_optimizer.updater import SolutionUpdater
from seating_optimizer.models import Block, Group, GroupDayAssignment, GroupBlockAssignment, Solution


def _make_solution():
    blocks = [
        Block("B0", 0, 0, 10),
        Block("B1", 0, 1, 10),
    ]
    groups_by_id = {
        "G1": Group("G1", "Alpha", 3, frozenset(["Dept1"])),
        "G2": Group("G2", "Beta",  4, frozenset(["Dept1"])),
    }
    day_assignments = [
        GroupDayAssignment("G1", (1, 2)),
        GroupDayAssignment("G2", (1, 2)),
    ]
    block_assignments = [
        GroupBlockAssignment("G1", 1, "B0", 3),
        GroupBlockAssignment("G1", 2, "B0", 3),
        GroupBlockAssignment("G2", 1, "B1", 4),
        GroupBlockAssignment("G2", 2, "B1", 4),
    ]
    solution = Solution(
        solution_id="test0001",
        created_at="2026-01-01T00:00:00+00:00",
        cover_pair=(1, 2),
        day_assignments=day_assignments,
        block_assignments=block_assignments,
        score=0.9,
        score_breakdown={"compactness": 1.0, "consistency": 0.75},
        metadata={},
    )
    return blocks, groups_by_id, solution


def test_updater_no_changes():
    """With no size changes the solution structure should be preserved."""
    blocks, groups_by_id, solution = _make_solution()
    updater = SolutionUpdater(blocks, groups_by_id)
    new_sol = updater.update(solution, {})
    assert new_sol is not None
    assert new_sol.solution_id != solution.solution_id
    assert new_sol.metadata.get("derived_from") == "test0001"
    assert len(new_sol.day_assignments) == 2


def test_updater_size_increase():
    """Growing a group should produce a valid solution."""
    blocks, groups_by_id, solution = _make_solution()
    updater = SolutionUpdater(blocks, groups_by_id)
    new_sol = updater.update(solution, {"G1": 5})
    assert new_sol is not None
    assert new_sol.metadata.get("derived_from") == "test0001"


def test_updater_size_decrease():
    """Shrinking a group should produce a valid solution."""
    blocks, groups_by_id, solution = _make_solution()
    updater = SolutionUpdater(blocks, groups_by_id)
    new_sol = updater.update(solution, {"G2": 2})
    assert new_sol is not None
