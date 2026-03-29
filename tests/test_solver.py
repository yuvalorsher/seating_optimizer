import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.loader import (
    load_office_map, load_employees, get_groups, get_department_map,
)
from seating_optimizer.solver import Solver
from seating_optimizer.constraints import check_all_hard_constraints

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
EMPLOYEES_CSV = os.path.join(DATA_DIR, "Employees list for seating with fake department.csv")


def _load():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    employees = load_employees(EMPLOYEES_CSV)
    groups = get_groups(employees)
    return blocks, groups


def test_solver_finds_solutions():
    blocks, groups = _load()
    solver = Solver(blocks, groups, n_solutions=3, max_iterations_per_cover=8, seed=42)
    solutions = solver.solve()
    assert len(solutions) >= 1


def test_solutions_satisfy_hard_constraints():
    blocks, groups = _load()
    blocks_by_id = {b.block_id: b for b in blocks}
    groups_by_id = {g.group_id: g for g in groups}
    dept_map = get_department_map(groups)

    solver = Solver(blocks, groups, n_solutions=3, max_iterations_per_cover=8, seed=42)
    solutions = solver.solve()

    for sol in solutions:
        da = {da.group_id: da.days for da in sol.day_assignments}
        valid, violations = check_all_hard_constraints(
            sol.cover_pair, da, sol.block_assignments,
            groups_by_id, blocks_by_id, dept_map,
        )
        assert valid, f"Hard constraint violated: {violations}"


def test_solution_scores_in_range():
    blocks, groups = _load()
    solver = Solver(blocks, groups, n_solutions=2, max_iterations_per_cover=8, seed=1)
    solutions = solver.solve()
    for sol in solutions:
        assert 0.0 <= sol.score <= 1.0
        assert "compactness" in sol.score_breakdown
        assert "consistency" in sol.score_breakdown


def test_all_groups_assigned():
    blocks, groups = _load()
    group_ids = {g.group_id for g in groups}
    solver = Solver(blocks, groups, n_solutions=1, max_iterations_per_cover=10, seed=7)
    solutions = solver.solve()
    assert solutions
    sol = solutions[0]
    assigned_groups = {da.group_id for da in sol.day_assignments}
    assert assigned_groups == group_ids
    # Each group has exactly 2 days worth of block assignments
    for group_id in group_ids:
        days = sol.get_group_days(group_id)
        assert days is not None
        assert len(days) == 2
        for day in days:
            bas = sol.get_group_blocks(group_id, day)
            assert len(bas) >= 1
            assert sum(count for _, count in bas) > 0
