from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import DAYS, Solution, TeamDayAssignment, TeamBlockAssignment
from .loader import get_department_map
from .solver import ConsistencyReconciler, Solver
from .scorer import compute_total_score
from .persistence import solution_to_dict, solution_from_dict


class SolutionUpdater:
    """
    Given an existing Solution and updated team sizes, produce a new Solution
    with the minimal number of reassignments.
    """

    def __init__(self, blocks: list, old_teams: list, new_teams: list):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        self.old_teams_by_id = {t.team_id: t for t in old_teams}
        self.new_teams_by_id = {t.team_id: t for t in new_teams}
        self.dept_map = get_department_map(new_teams)

    def update(self, existing_solution: Solution) -> Solution:
        """
        Returns a new Solution derived from existing_solution with minimal changes.
        """
        # Rebuild dicts from solution
        day_assignments: dict = {
            da.team_id: da.days for da in existing_solution.day_assignments
        }
        block_assignments: dict = {
            (ba.team_id, ba.day): ba.block_id
            for ba in existing_solution.block_assignments
        }

        # Detect violated (team, day) pairs
        violated = self._find_violated_teams(
            existing_solution, self.new_teams_by_id, self.blocks_by_id
        )

        if not violated:
            # No changes needed; just update sizes in metadata and recompute score
            score, breakdown = compute_total_score(
                day_assignments, block_assignments,
                self.new_teams_by_id, self.blocks_by_id, self.dept_map
            )
            return self._wrap_solution(
                existing_solution.cover_pair,
                day_assignments,
                block_assignments,
                score,
                breakdown,
                existing_solution.solution_id,
            )

        # Sort violated pairs by severity (larger overflow first)
        def severity(item):
            team_id, days_list = item
            team = self.new_teams_by_id[team_id]
            worst = 0
            for day in days_list:
                load = self._compute_block_loads(day, block_assignments, self.new_teams_by_id)
                block_id = block_assignments.get((team_id, day))
                if block_id:
                    cap = self.blocks_by_id[block_id].capacity
                    worst = max(worst, load[block_id] - cap)
            return worst

        sorted_violated = sorted(violated.items(), key=severity, reverse=True)

        # Greedily relocate each violated (team, day)
        needs_partial_resolve: list = []
        for team_id, days_list in sorted_violated:
            for day in days_list:
                # Release team from current block
                old_block = block_assignments.get((team_id, day))
                if old_block:
                    del block_assignments[(team_id, day)]

                load = self._compute_block_loads(day, block_assignments, self.new_teams_by_id)
                team = self.new_teams_by_id[team_id]
                best = self._find_best_block_for_team(
                    team, day, load, self.blocks_by_id, self.dept_map, block_assignments
                )
                if best:
                    block_assignments[(team_id, day)] = best
                else:
                    needs_partial_resolve.append((team_id, day))

        if needs_partial_resolve:
            block_assignments = self._partial_resolve(
                day_assignments, block_assignments, needs_partial_resolve
            )

        # Re-run consistency reconciler on all teams
        reconciler = ConsistencyReconciler()
        block_assignments = reconciler.reconcile(
            day_assignments, block_assignments, self.new_teams_by_id, self.blocks_by_id
        )

        score, breakdown = compute_total_score(
            day_assignments, block_assignments,
            self.new_teams_by_id, self.blocks_by_id, self.dept_map
        )
        return self._wrap_solution(
            existing_solution.cover_pair,
            day_assignments,
            block_assignments,
            score,
            breakdown,
            existing_solution.solution_id,
        )

    # ------------------------------------------------------------------ helpers

    def _find_violated_teams(
        self,
        solution: Solution,
        new_teams_by_id: dict,
        blocks_by_id: dict,
    ) -> dict:
        """Return {team_id: [day, ...]} for days where capacity is exceeded."""
        # Build day -> {block_id: [team_id, ...]}
        day_block_teams: dict = {d: {} for d in DAYS}
        for ba in solution.block_assignments:
            day_block_teams[ba.day].setdefault(ba.block_id, []).append(ba.team_id)

        violated: dict = {}
        for day, block_map in day_block_teams.items():
            for block_id, team_ids in block_map.items():
                total = sum(
                    new_teams_by_id[tid].size
                    for tid in team_ids
                    if tid in new_teams_by_id
                )
                if total > blocks_by_id[block_id].capacity:
                    for tid in team_ids:
                        violated.setdefault(tid, []).append(day)

        return violated

    def _compute_block_loads(
        self,
        day: int,
        block_assignments: dict,
        teams_by_id: dict,
    ) -> dict:
        """Return {block_id: seats_used} for a specific day."""
        load: dict = {b.block_id: 0 for b in self.blocks}
        for (tid, d), bid in block_assignments.items():
            if d == day and tid in teams_by_id:
                load[bid] = load.get(bid, 0) + teams_by_id[tid].size
        return load

    def _find_best_block_for_team(
        self,
        team,
        day: int,
        current_loads: dict,
        blocks_by_id: dict,
        dept_map: dict,
        block_assignments: dict,
    ) -> Optional[str]:
        """
        Find the best available block for team on day.
        Score: +2 same-dept already in block, +1 per seat used (prefer fuller),
               must have capacity for team.size.
        Returns block_id or None.
        """
        candidates = [
            b for b in self.blocks
            if b.capacity - current_loads.get(b.block_id, 0) >= team.size
        ]
        if not candidates:
            return None

        def block_score(b: object) -> float:
            score = 0
            for (tid, d), bid in block_assignments.items():
                if bid == b.block_id and d == day:
                    other = self.new_teams_by_id.get(tid)
                    if other and other.department == team.department:
                        score += 2
                    elif other:
                        score += 0.1
            # Prefer less wasted space
            waste = b.capacity - current_loads.get(b.block_id, 0) - team.size
            score -= waste * 0.01
            return score

        return max(candidates, key=block_score).block_id

    def _partial_resolve(
        self,
        day_assignments: dict,
        block_assignments: dict,
        unplaced: list,   # [(team_id, day), ...]
    ) -> dict:
        """
        Fall back to Solver for unplaced teams, keeping all other assignments fixed.
        """
        unplaced_team_ids = {tid for tid, _ in unplaced}
        anchored_teams = [
            t for t in self.new_teams_by_id.values()
            if t.team_id not in unplaced_team_ids
        ]
        unplaced_teams = [self.new_teams_by_id[tid] for tid in unplaced_team_ids]

        # Compute loads from anchored assignments
        for team_id, _ in unplaced:
            for day in DAYS:
                block_assignments.pop((team_id, day), None)

        # Re-solve just the unplaced teams
        if unplaced_teams:
            sub_solver = Solver(
                blocks=self.blocks,
                teams=unplaced_teams,
                n_solutions=1,
                max_iterations_per_cover=100,
            )
            # Pass pre-occupied loads as preferred_blocks hint for SeatingAssigner
            sub_solutions = sub_solver.solve()
            if sub_solutions:
                for ba in sub_solutions[0].block_assignments:
                    block_assignments[(ba.team_id, ba.day)] = ba.block_id

        return block_assignments

    def _wrap_solution(
        self,
        cover_pair: tuple,
        day_assignments: dict,
        block_assignments: dict,
        score: float,
        breakdown: dict,
        derived_from: str,
    ) -> Solution:
        da_list = [
            TeamDayAssignment(team_id=tid, days=days)
            for tid, days in day_assignments.items()
        ]
        ba_list = [
            TeamBlockAssignment(team_id=tid, day=day, block_id=bid)
            for (tid, day), bid in block_assignments.items()
        ]
        return Solution(
            solution_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=cover_pair,
            day_assignments=da_list,
            block_assignments=ba_list,
            score=score,
            score_breakdown=breakdown,
            metadata={"derived_from": derived_from},
        )
