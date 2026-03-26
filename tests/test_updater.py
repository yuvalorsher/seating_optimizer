import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import copy
from seating_optimizer.loader import load_office_map, load_teams
from seating_optimizer.solver import Solver
from seating_optimizer.updater import SolutionUpdater
from seating_optimizer.constraints import check_all_hard_constraints
from seating_optimizer.models import Team

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _get_solution(seed=42):
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    solver = Solver(blocks, teams, n_solutions=1, max_iterations_per_cover=150, seed=seed)
    solutions = solver.solve()
    assert solutions, "Solver found no solutions — test cannot continue"
    return blocks, teams, solutions[0]


def test_update_no_change():
    blocks, teams, sol = _get_solution()
    # No size changes → updated solution should satisfy hard constraints
    updater = SolutionUpdater(blocks, teams, teams)
    updated = updater.update(sol)
    teams_by_id = {t.team_id: t for t in teams}
    blocks_by_id = {b.block_id: b for b in blocks}
    da = {da.team_id: da.days for da in updated.day_assignments}
    ba = {(ba.team_id, ba.day): ba.block_id for ba in updated.block_assignments}
    valid, violations = check_all_hard_constraints(updated.cover_pair, da, ba, teams_by_id, blocks_by_id)
    assert valid, violations


def test_update_with_small_size_increase():
    blocks, old_teams, sol = _get_solution()
    # Increase one team's size by 1
    new_teams = list(old_teams)
    t0 = new_teams[0]
    new_teams[0] = Team(t0.team_id, t0.name, t0.department, t0.size + 1)

    updater = SolutionUpdater(blocks, old_teams, new_teams)
    updated = updater.update(sol)
    new_teams_by_id = {t.team_id: t for t in new_teams}
    blocks_by_id = {b.block_id: b for b in blocks}
    da = {da.team_id: da.days for da in updated.day_assignments}
    ba = {(ba.team_id, ba.day): ba.block_id for ba in updated.block_assignments}
    valid, violations = check_all_hard_constraints(updated.cover_pair, da, ba, new_teams_by_id, blocks_by_id)
    assert valid, violations


def test_update_preserves_derived_from():
    blocks, teams, sol = _get_solution()
    updater = SolutionUpdater(blocks, teams, teams)
    updated = updater.update(sol)
    assert updated.metadata.get("derived_from") == sol.solution_id
