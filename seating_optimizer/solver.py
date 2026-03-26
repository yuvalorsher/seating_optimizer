from __future__ import annotations
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import DAYS, Block, Team, TeamDayAssignment, TeamBlockAssignment, Solution
from .constraints import ALL_COVER_PAIRS, valid_day_combos_for_cover_pair
from .scorer import compute_total_score
from .loader import get_department_map


# ---------------------------------------------------------------------------
# Phase 1: Day Assignment
# ---------------------------------------------------------------------------

class DayAssigner:
    """
    Assign each team to exactly 2 days, satisfying the cover constraint
    by construction: every team's days include at least one of (A, B).
    """

    def __init__(self, teams: list, seed: Optional[int] = None):
        self.teams = teams
        self.rng = random.Random(seed)

    def assign(self, cover_pair: tuple) -> dict:
        """Random uniform sampling from valid combos for each team."""
        valid_combos = valid_day_combos_for_cover_pair(cover_pair)
        return {t.team_id: self.rng.choice(valid_combos) for t in self.teams}

    def assign_with_load_balance(self, cover_pair: tuple, blocks: list) -> dict:
        """
        Biased sampling: weight day combos by how much they balance the total
        employee-days across days.  Falls back to assign() if teams list is empty.
        """
        valid_combos = valid_day_combos_for_cover_pair(cover_pair)
        if not self.teams:
            return {}

        # Greedy: pick combo that minimises the variance of load per day so far.
        result = {}
        day_load: dict = {d: 0 for d in DAYS}

        for team in sorted(self.teams, key=lambda t: -t.size):
            best_combo = None
            best_cost = float("inf")
            combos = list(valid_combos)
            self.rng.shuffle(combos)
            for combo in combos:
                # Simulate adding this team to this combo
                trial = dict(day_load)
                for d in combo:
                    trial[d] += team.size
                variance = _variance(list(trial.values()))
                if variance < best_cost:
                    best_cost = variance
                    best_combo = combo
            result[team.team_id] = best_combo
            for d in best_combo:
                day_load[d] += team.size

        return result


# ---------------------------------------------------------------------------
# Phase 2: Seating Assignment (one day at a time)
# ---------------------------------------------------------------------------

class SeatingAssigner:
    """
    Bin-pack teams into blocks for a single day, with department-grouping
    preference.
    """

    def __init__(self, blocks: list, teams_by_id: dict):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        self.teams_by_id = teams_by_id

    def assign_day(
        self,
        day: int,
        teams_on_day: list,                   # [team_id, ...]
        dept_map: dict,                        # {dept: [Team, ...]}
        preferred_blocks: Optional[dict] = None,  # {team_id: block_id} hints
    ) -> Optional[dict]:
        """
        Returns {team_id: block_id} for all teams on this day, or None if
        infeasible.
        """
        if not teams_on_day:
            return {}

        current_load: dict = {b.block_id: 0 for b in self.blocks}
        assignment: dict = {}

        # If preferred_blocks provided, try to satisfy them first as anchors
        if preferred_blocks:
            for team_id in list(teams_on_day):
                pref = preferred_blocks.get(team_id)
                if pref and pref in current_load:
                    team = self.teams_by_id[team_id]
                    if current_load[pref] + team.size <= self.blocks_by_id[pref].capacity:
                        assignment[team_id] = pref
                        current_load[pref] += team.size

        remaining = [tid for tid in teams_on_day if tid not in assignment]

        # Group remaining by dept, sort dept groups by total size DESC
        dept_groups: dict = {}
        for team_id in remaining:
            dept = self.teams_by_id[team_id].department
            dept_groups.setdefault(dept, []).append(self.teams_by_id[team_id])

        sorted_groups = sorted(
            dept_groups.values(),
            key=lambda g: sum(t.size for t in g),
            reverse=True,
        )

        for group in sorted_groups:
            group_size = sum(t.size for t in group)

            # Attempt 1: fit entire dept in one block
            result = self._try_fit_dept_group(group, current_load)
            if result is not None:
                for team_id, block_id in result.items():
                    assignment[team_id] = block_id
                    current_load[block_id] += self.teams_by_id[team_id].size
            else:
                # Attempt 2: greedy split
                result = self._greedy_split(group, current_load)
                if result is None:
                    return None  # infeasible
                for team_id, block_id in result.items():
                    assignment[team_id] = block_id
                    current_load[block_id] += self.teams_by_id[team_id].size

        # Local swap pass to improve dept cohesion
        assignment = self._local_swap_pass(assignment, current_load, dept_map)
        return assignment

    def _try_fit_dept_group(
        self,
        teams: list,
        current_load: dict,
        exclude_blocks: Optional[set] = None,
    ) -> Optional[dict]:
        """Try to place all teams in a single block. Return mapping or None."""
        group_size = sum(t.size for t in teams)
        candidates = [
            b for b in self.blocks
            if (exclude_blocks is None or b.block_id not in exclude_blocks)
            and b.capacity - current_load[b.block_id] >= group_size
        ]
        if not candidates:
            return None
        # Tightest fit: minimise wasted space
        best = min(candidates, key=lambda b: b.capacity - current_load[b.block_id] - group_size)
        return {t.team_id: best.block_id for t in teams}

    def _greedy_split(self, teams: list, current_load: dict) -> Optional[dict]:
        """Place teams largest-first into the most available block."""
        sorted_teams = sorted(teams, key=lambda t: t.size, reverse=True)
        result = {}
        load = dict(current_load)  # local copy

        for team in sorted_teams:
            eligible = [
                b for b in self.blocks
                if b.capacity - load[b.block_id] >= team.size
            ]
            if not eligible:
                return None
            # Prefer block with most remaining space (leaves room for remaining)
            chosen = max(eligible, key=lambda b: b.capacity - load[b.block_id])
            result[team.team_id] = chosen.block_id
            load[chosen.block_id] += team.size

        return result

    def _local_swap_pass(
        self,
        assignment: dict,
        current_load: dict,
        dept_map: dict,
    ) -> dict:
        """
        Try pairwise swaps between teams in different blocks that would improve
        dept cohesion, without violating capacity.  Repeat until no improvement.
        """
        improved = True
        load = dict(current_load)
        team_ids = list(assignment.keys())

        while improved:
            improved = False
            for i in range(len(team_ids)):
                for j in range(i + 1, len(team_ids)):
                    t1 = self.teams_by_id[team_ids[i]]
                    t2 = self.teams_by_id[team_ids[j]]
                    b1 = assignment[t1.team_id]
                    b2 = assignment[t2.team_id]
                    if b1 == b2:
                        continue
                    # Same-dept swaps never change cohesion (one leaves, one arrives,
                    # net count per block unchanged) but the gain formula spuriously
                    # returns >0, causing an infinite loop. Skip them.
                    if t1.department == t2.department:
                        continue
                    # Check if swap is capacity-feasible
                    if (
                        load[b1] - t1.size + t2.size <= self.blocks_by_id[b1].capacity
                        and load[b2] - t2.size + t1.size <= self.blocks_by_id[b2].capacity
                    ):
                        gain = _dept_cohesion_gain(
                            t1, t2, b1, b2, assignment, self.teams_by_id
                        )
                        if gain > 0:
                            # Apply swap
                            assignment[t1.team_id] = b2
                            assignment[t2.team_id] = b1
                            load[b1] = load[b1] - t1.size + t2.size
                            load[b2] = load[b2] - t2.size + t1.size
                            improved = True

        return assignment


# ---------------------------------------------------------------------------
# Phase 3: Consistency Reconciliation
# ---------------------------------------------------------------------------

class ConsistencyReconciler:
    """
    Post-process block_assignments to maximise teams that use the same
    block on both their days.
    """

    def reconcile(
        self,
        day_assignments: dict,       # {team_id: (d1, d2)}
        block_assignments: dict,     # {(team_id, day): block_id}
        teams_by_id: dict,
        blocks_by_id: dict,
    ) -> dict:
        """Returns updated block_assignments."""
        ba = dict(block_assignments)

        # Compute current load per (block, day)
        load: dict = {}  # {(block_id, day): seats_used}
        for block in blocks_by_id.values():
            for day in DAYS:
                load[(block.block_id, day)] = 0
        for (team_id, day), block_id in ba.items():
            load[(block_id, day)] = load.get((block_id, day), 0) + teams_by_id[team_id].size

        improved = True
        while improved:
            improved = False
            for team_id, (d1, d2) in day_assignments.items():
                b1 = ba.get((team_id, d1))
                b2 = ba.get((team_id, d2))
                if b1 is None or b2 is None or b1 == b2:
                    continue

                team_size = teams_by_id[team_id].size

                # Try to move team to b1 on d2
                avail_b1_d2 = (
                    blocks_by_id[b1].capacity
                    - load.get((b1, d2), 0)
                )
                if avail_b1_d2 >= team_size:
                    # Apply: release b2 on d2, take b1 on d2
                    load[(b2, d2)] -= team_size
                    load[(b1, d2)] = load.get((b1, d2), 0) + team_size
                    ba[(team_id, d2)] = b1
                    improved = True
                    continue

                # Try to move team to b2 on d1
                avail_b2_d1 = (
                    blocks_by_id[b2].capacity
                    - load.get((b2, d1), 0)
                )
                if avail_b2_d1 >= team_size:
                    load[(b1, d1)] -= team_size
                    load[(b2, d1)] = load.get((b2, d1), 0) + team_size
                    ba[(team_id, d1)] = b2
                    improved = True
                    continue

        return ba


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Solver:
    """Find N feasible, high-scoring solutions."""

    def __init__(
        self,
        blocks: list,
        teams: list,
        n_solutions: int = 5,
        max_iterations_per_cover: int = 200,
        seed: Optional[int] = None,
    ):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        self.teams = teams
        self.teams_by_id = {t.team_id: t for t in teams}
        self.dept_map = get_department_map(teams)
        self.n_solutions = n_solutions
        self.max_iterations = max_iterations_per_cover
        self.rng = random.Random(seed)
        self._seed = seed

    def solve(self, progress_callback=None) -> list:
        """
        Main entry point. Returns list[Solution] (up to n_solutions),
        sorted by score descending.

        progress_callback(iteration, total) called each iteration if provided.
        """
        pool: list = []
        seen_signatures: set = set()

        total_iters = len(ALL_COVER_PAIRS) * self.max_iterations

        for cover_pair in ALL_COVER_PAIRS:
            if len(pool) >= self.n_solutions * 3:
                break  # have plenty of candidates
            assigner = DayAssigner(self.teams, seed=self.rng.randint(0, 10**9))
            seating = SeatingAssigner(self.blocks, self.teams_by_id)
            reconciler = ConsistencyReconciler()

            for iteration in range(self.max_iterations):
                if progress_callback:
                    done = (ALL_COVER_PAIRS.index(cover_pair) * self.max_iterations + iteration)
                    progress_callback(done, total_iters)

                # Phase 1 — day assignment
                if iteration < self.max_iterations // 2:
                    day_assignments = assigner.assign(cover_pair)
                else:
                    day_assignments = assigner.assign_with_load_balance(cover_pair, self.blocks)

                # Phase 2 — seating per day
                block_assignments: dict = {}
                feasible = True
                for day in DAYS:
                    teams_on_day = self._collect_teams_for_day(day, day_assignments)
                    day_result = seating.assign_day(day, teams_on_day, self.dept_map)
                    if day_result is None:
                        feasible = False
                        break
                    for team_id, block_id in day_result.items():
                        block_assignments[(team_id, day)] = block_id

                if not feasible:
                    continue

                # Phase 3 — consistency reconciliation
                block_assignments = reconciler.reconcile(
                    day_assignments, block_assignments, self.teams_by_id, self.blocks_by_id
                )

                # Score
                score, breakdown = compute_total_score(
                    day_assignments, block_assignments,
                    self.teams_by_id, self.blocks_by_id, self.dept_map
                )

                sig = _solution_signature(day_assignments, block_assignments)
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)

                sol = self._build_solution(
                    cover_pair, day_assignments, block_assignments,
                    score, breakdown,
                    seed=self.rng.randint(0, 10**9),
                    iteration=iteration,
                )
                pool.append(sol)

                if len(pool) >= self.n_solutions * 10:
                    break

        pool.sort(key=lambda s: s.score, reverse=True)
        return pool[: self.n_solutions]

    def _collect_teams_for_day(self, day: int, day_assignments: dict) -> list:
        return [tid for tid, days in day_assignments.items() if day in days]

    def _build_solution(
        self,
        cover_pair: tuple,
        day_assignments: dict,
        block_assignments: dict,
        score: float,
        score_breakdown: dict,
        seed: int,
        iteration: int,
    ) -> Solution:
        da_list = [
            TeamDayAssignment(team_id=tid, days=days)
            for tid, days in day_assignments.items()
        ]
        ba_list = [
            TeamBlockAssignment(team_id=tid, day=day, block_id=block_id)
            for (tid, day), block_id in block_assignments.items()
        ]
        return Solution(
            solution_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=cover_pair,
            day_assignments=da_list,
            block_assignments=ba_list,
            score=score,
            score_breakdown=score_breakdown,
            metadata={
                "solver_seed": seed,
                "cover_pair_tried": list(cover_pair),
                "iteration": iteration,
                "derived_from": None,
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _variance(values: list) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _dept_cohesion_gain(
    t1, t2, b1: str, b2: str, assignment: dict, teams_by_id: dict
) -> int:
    """
    Count how many same-dept teammates t1 gains in b2 (and t2 in b1),
    minus what each loses.  Positive = beneficial swap.
    """
    def same_dept_count(team, target_block, assignment, teams_by_id):
        return sum(
            1 for tid, bid in assignment.items()
            if bid == target_block
            and teams_by_id[tid].department == team.department
            and tid != team.team_id
        )

    t1_gain = same_dept_count(t1, b2, assignment, teams_by_id) - same_dept_count(t1, b1, assignment, teams_by_id)
    t2_gain = same_dept_count(t2, b1, assignment, teams_by_id) - same_dept_count(t2, b2, assignment, teams_by_id)
    return t1_gain + t2_gain


def _solution_signature(day_assignments: dict, block_assignments: dict) -> frozenset:
    """Canonical fingerprint to detect duplicate solutions."""
    return frozenset(
        (tid, days, block_assignments.get((tid, days[0])), block_assignments.get((tid, days[1])))
        for tid, days in day_assignments.items()
    )
