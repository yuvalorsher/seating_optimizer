import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.loader import load_office_map, load_teams
from seating_optimizer.solver import Solver
from seating_optimizer.constraints import check_all_hard_constraints

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def test_solver_finds_solutions():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    solver = Solver(blocks, teams, n_solutions=3, max_iterations_per_cover=100, seed=42)
    solutions = solver.solve()
    assert len(solutions) >= 1


def test_solutions_satisfy_hard_constraints():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    teams_by_id = {t.team_id: t for t in teams}
    blocks_by_id = {b.block_id: b for b in blocks}
    solver = Solver(blocks, teams, n_solutions=3, max_iterations_per_cover=100, seed=42)
    solutions = solver.solve()
    for sol in solutions:
        da = {da.team_id: da.days for da in sol.day_assignments}
        ba = {(ba.team_id, ba.day): ba.block_id for ba in sol.block_assignments}
        valid, violations = check_all_hard_constraints(
            sol.cover_pair, da, ba, teams_by_id, blocks_by_id
        )
        assert valid, f"Hard constraint violated: {violations}"


def test_solution_scores_in_range():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    solver = Solver(blocks, teams, n_solutions=2, max_iterations_per_cover=50, seed=1)
    solutions = solver.solve()
    for sol in solutions:
        assert 0.0 <= sol.score <= 1.0
        assert "consistency" in sol.score_breakdown
        assert "dept_proximity" in sol.score_breakdown


def test_all_teams_assigned():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    team_ids = {t.team_id for t in teams}
    solver = Solver(blocks, teams, n_solutions=1, max_iterations_per_cover=100, seed=7)
    solutions = solver.solve()
    assert solutions
    sol = solutions[0]
    assigned_teams = {da.team_id for da in sol.day_assignments}
    assert assigned_teams == team_ids
    # Each team has exactly 2 block assignments
    for team_id in team_ids:
        team_bas = [ba for ba in sol.block_assignments if ba.team_id == team_id]
        assert len(team_bas) == 2
