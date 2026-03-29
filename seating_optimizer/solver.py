from __future__ import annotations
import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .models import DAYS, GroupDayAssignment, GroupBlockAssignment, Solution
from .constraints import (
    ALL_COVER_PAIRS, valid_day_combos_for_cover_pair,
    all_dept_day_assignments, MAX_COL_DISTANCE,
)
from .scorer import compute_total_score
from .loader import get_department_map


# ---------------------------------------------------------------------------
# Phase 1: Day Assignment
# ---------------------------------------------------------------------------

class DayAssigner:
    """
    Assign each group to exactly 2 days, satisfying:
    - Cover constraint (by construction, all common days are from the cover pair)
    - Dept overlap: all groups in each dept share at least one day (via common day per dept)
    """

    def __init__(self, groups: list, rng: random.Random):
        self.groups = groups
        self.rng = rng

    def assign(self, cover_pair: tuple, dept_common_days: dict) -> Optional[dict]:
        """
        Assign days to groups given dept_common_days {dept: day}.
        All common days are from cover_pair, so cover constraint is auto-satisfied.

        Returns {group_id: (day_a, day_b)} or None if infeasible.
        """
        valid_combos = valid_day_combos_for_cover_pair(cover_pair)
        result = {}

        for group in self.groups:
            # Mandatory days = union of common days for all depts this group has members in
            mandatory = set()
            for dept in group.departments:
                if dept in dept_common_days:
                    mandatory.add(dept_common_days[dept])

            if len(mandatory) > 2:
                return None   # group would need to attend 3+ days: impossible

            if len(mandatory) == 2:
                days = tuple(sorted(mandatory))
                if days not in valid_combos:
                    return None
                result[group.group_id] = days

            elif len(mandatory) == 1:
                fixed = next(iter(mandatory))
                eligible = [c for c in valid_combos if fixed in c]
                if not eligible:
                    return None
                result[group.group_id] = self.rng.choice(eligible)

            else:
                # No dept constraint: pick any valid combo
                result[group.group_id] = self.rng.choice(valid_combos)

        return result

    def assign_load_balanced(self, cover_pair: tuple, dept_common_days: dict) -> Optional[dict]:
        """
        Like assign(), but for free-choice groups, prefer combos that balance load.
        """
        valid_combos = valid_day_combos_for_cover_pair(cover_pair)
        result = {}
        day_load: dict = {d: 0 for d in DAYS}

        for group in sorted(self.groups, key=lambda g: -g.size):
            mandatory = set()
            for dept in group.departments:
                if dept in dept_common_days:
                    mandatory.add(dept_common_days[dept])

            if len(mandatory) > 2:
                return None

            if len(mandatory) == 2:
                days = tuple(sorted(mandatory))
                if days not in valid_combos:
                    return None
                result[group.group_id] = days
                for d in days:
                    day_load[d] += group.size

            elif len(mandatory) == 1:
                fixed = next(iter(mandatory))
                eligible = [c for c in valid_combos if fixed in c]
                if not eligible:
                    return None
                combos = list(eligible)
                self.rng.shuffle(combos)
                best, best_cost = None, float("inf")
                for combo in combos:
                    trial = dict(day_load)
                    for d in combo:
                        trial[d] += group.size
                    cost = _variance(list(trial.values()))
                    if cost < best_cost:
                        best_cost = cost
                        best = combo
                result[group.group_id] = best
                for d in best:
                    day_load[d] += group.size

            else:
                combos = list(valid_combos)
                self.rng.shuffle(combos)
                best, best_cost = None, float("inf")
                for combo in combos:
                    trial = dict(day_load)
                    for d in combo:
                        trial[d] += group.size
                    cost = _variance(list(trial.values()))
                    if cost < best_cost:
                        best_cost = cost
                        best = combo
                result[group.group_id] = best
                for d in best:
                    day_load[d] += group.size

        return result


# ---------------------------------------------------------------------------
# Phase 2: Seating Assignment (one day at a time)
# ---------------------------------------------------------------------------

class SeatingAssigner:
    """
    Bin-pack groups into blocks for a single day, keeping each group together
    (in one block if possible, else in adjacent blocks within MAX_COL_DISTANCE columns).
    """

    def __init__(self, blocks: list):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        # Pre-compute column groups: sets of blocks all within MAX_COL_DISTANCE of each other
        self._col_groups = _compute_column_groups(blocks, MAX_COL_DISTANCE)

    def assign_day(
        self,
        groups_on_day: list,            # [Group, ...]
        preferred_assignments: Optional[dict] = None,   # {group_id: [(block_id, count), ...]}
    ) -> Optional[list]:
        """
        Returns list[GroupBlockAssignment] for all groups on this day, or None if infeasible.
        preferred_assignments: hints from consistency reconciler (anchors).
        """
        if not groups_on_day:
            return []

        current_load: dict = {b.block_id: 0 for b in self.blocks}
        result: list = []   # [GroupBlockAssignment]

        # Apply preferred assignments first (anchors from consistency reconciler)
        remaining_groups = list(groups_on_day)
        if preferred_assignments:
            still_remaining = []
            for group in groups_on_day:
                pref = preferred_assignments.get(group.group_id)
                if pref is not None:
                    # Check if preferred assignment fits
                    fits = all(
                        current_load[block_id] + count <= self.blocks_by_id[block_id].capacity
                        for block_id, count in pref
                        if block_id in self.blocks_by_id
                    )
                    if fits and all(block_id in self.blocks_by_id for block_id, _ in pref):
                        for block_id, count in pref:
                            result.append(GroupBlockAssignment(
                                group_id=group.group_id,
                                day=0,  # day filled in by caller
                                block_id=block_id,
                                count=count,
                            ))
                            current_load[block_id] += count
                        continue
                still_remaining.append(group)
            remaining_groups = still_remaining

        # Sort remaining groups by size descending (pack largest first)
        remaining_groups.sort(key=lambda g: -g.size)

        for group in remaining_groups:
            assignment = self._place_group(group, current_load)
            if assignment is None:
                return None   # infeasible

            for block_id, count in assignment:
                result.append(GroupBlockAssignment(
                    group_id=group.group_id,
                    day=0,   # day filled in by caller
                    block_id=block_id,
                    count=count,
                ))
                current_load[block_id] += count

        return result

    def _place_group(self, group, current_load: dict) -> Optional[list]:
        """
        Try to place a group. Returns [(block_id, count), ...] or None.
        Attempts: (1) single block, (2) split within each column group.
        """
        # Attempt 1: fit in a single block (tightest fit)
        candidates = [
            b for b in self.blocks
            if b.capacity - current_load[b.block_id] >= group.size
        ]
        if candidates:
            best = min(candidates, key=lambda b: b.capacity - current_load[b.block_id] - group.size)
            return [(best.block_id, group.size)]

        # Attempt 2: split across a column group
        for col_group in self._col_groups:
            avail_total = sum(
                b.capacity - current_load[b.block_id] for b in col_group
            )
            if avail_total < group.size:
                continue

            # Greedily fill blocks in this column group (most space first)
            assignment = _fill_column_group(group.size, col_group, current_load)
            if assignment is not None:
                return assignment

        return None   # infeasible


def _compute_column_groups(blocks: list, max_col_dist: int) -> list:
    """
    Return a list of block groups where within each group, all blocks are
    within max_col_dist columns of each other.
    Groups are ordered by total capacity descending (best first).
    """
    sorted_cols = sorted(set(b.col for b in blocks))
    block_by_col: dict = defaultdict(list)
    for b in blocks:
        block_by_col[b.col].append(b)

    # Greedy grouping: extend current group while next column is within range
    groups = []
    current_min_col = sorted_cols[0]
    current_blocks = list(block_by_col[sorted_cols[0]])

    for col in sorted_cols[1:]:
        if col - current_min_col <= max_col_dist:
            current_blocks.extend(block_by_col[col])
        else:
            groups.append(list(current_blocks))
            current_min_col = col
            current_blocks = list(block_by_col[col])

    groups.append(current_blocks)

    # Sort groups by total capacity descending so we try the best option first
    groups.sort(key=lambda g: sum(b.capacity for b in g), reverse=True)
    return groups


def _fill_column_group(size: int, col_group: list, current_load: dict) -> Optional[list]:
    """
    Greedily fill blocks in a column group to seat 'size' employees.
    Returns [(block_id, count), ...] or None.
    """
    remaining = size
    result = []
    sorted_blocks = sorted(
        col_group,
        key=lambda b: b.capacity - current_load[b.block_id],
        reverse=True,
    )
    for b in sorted_blocks:
        avail = b.capacity - current_load[b.block_id]
        if avail <= 0:
            continue
        take = min(remaining, avail)
        result.append((b.block_id, take))
        remaining -= take
        if remaining == 0:
            break

    if remaining > 0:
        return None
    return result


# ---------------------------------------------------------------------------
# Phase 3: Consistency Reconciliation
# ---------------------------------------------------------------------------

class ConsistencyReconciler:
    """
    Post-process block_assignments to maximise groups that use the same
    block(s) on both their days.  Only operates on single-block groups.
    """

    def reconcile(
        self,
        day_assignments: dict,       # {group_id: (d1, d2)}
        block_assignments: list,     # list[GroupBlockAssignment]
        groups_by_id: dict,
        blocks_by_id: dict,
    ) -> list:
        """Returns updated block_assignments list."""
        # Build mutable load map per (block_id, day)
        load: dict = defaultdict(int)
        for ba in block_assignments:
            load[(ba.block_id, ba.day)] += ba.count

        bas = list(block_assignments)

        improved = True
        while improved:
            improved = False
            for group_id, (d1, d2) in day_assignments.items():
                blocks_d1 = [(ba.block_id, ba.count) for ba in bas
                             if ba.group_id == group_id and ba.day == d1]
                blocks_d2 = [(ba.block_id, ba.count) for ba in bas
                             if ba.group_id == group_id and ba.day == d2]

                # Only process single-block groups
                if len(blocks_d1) != 1 or len(blocks_d2) != 1:
                    continue

                b1, count1 = blocks_d1[0]
                b2, count2 = blocks_d2[0]

                if b1 == b2:
                    continue

                group_size = count1  # == count2 for single-block groups

                # Try to move to b1 on d2
                avail_b1_d2 = blocks_by_id[b1].capacity - load[(b1, d2)]
                if avail_b1_d2 >= group_size:
                    # Apply: release b2 on d2, take b1 on d2
                    load[(b2, d2)] -= group_size
                    load[(b1, d2)] += group_size
                    for ba in bas:
                        if ba.group_id == group_id and ba.day == d2:
                            ba.block_id = b1
                    improved = True
                    continue

                # Try to move to b2 on d1
                avail_b2_d1 = blocks_by_id[b2].capacity - load[(b2, d1)]
                if avail_b2_d1 >= group_size:
                    load[(b1, d1)] -= group_size
                    load[(b2, d1)] += group_size
                    for ba in bas:
                        if ba.group_id == group_id and ba.day == d1:
                            ba.block_id = b2
                    improved = True
                    continue

        return bas


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Solver:
    """Find N feasible, high-scoring solutions."""

    def __init__(
        self,
        blocks: list,
        groups: list,
        n_solutions: int = 5,
        max_iterations_per_cover: int = 200,
        seed: Optional[int] = None,
    ):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        self.groups = groups
        self.groups_by_id = {g.group_id: g for g in groups}
        self.dept_map = get_department_map(groups)
        self.n_solutions = n_solutions
        self.max_iterations = max_iterations_per_cover
        self.rng = random.Random(seed)
        self._seed = seed

    def solve(self, progress_callback=None) -> list:
        """
        Main entry point. Returns list[Solution] (up to n_solutions),
        sorted by score descending.
        """
        pool: list = []
        seen_signatures: set = set()
        depts = list(self.dept_map.keys())

        # Outer iterations: cover_pairs × dept_day_combos × random seeds
        # For each (cover_pair, dept_day_combo), do a small number of seating iterations
        iters_per_dept_combo = max(4, self.max_iterations // max(1, 2 ** len(depts)))
        total_iters = len(ALL_COVER_PAIRS) * (2 ** len(depts)) * iters_per_dept_combo
        done_count = 0

        for cover_pair in ALL_COVER_PAIRS:
            dept_combos = all_dept_day_assignments(cover_pair, depts)

            for dept_day_combo in dept_combos:
                if len(pool) >= self.n_solutions * 3:
                    break

                assigner = DayAssigner(self.groups, self.rng)
                seating = SeatingAssigner(self.blocks)
                reconciler = ConsistencyReconciler()

                for iteration in range(iters_per_dept_combo):
                    if progress_callback:
                        progress_callback(done_count, total_iters)
                    done_count += 1

                    # Phase 1 — day assignment
                    if iteration < iters_per_dept_combo // 2:
                        day_assignments = assigner.assign(cover_pair, dept_day_combo)
                    else:
                        day_assignments = assigner.assign_load_balanced(
                            cover_pair, dept_day_combo
                        )

                    if day_assignments is None:
                        continue   # this dept_day_combo is infeasible for some group

                    # Phase 2 — seating per day
                    all_bas: list = []
                    feasible = True
                    for day in DAYS:
                        groups_on_day = [
                            self.groups_by_id[gid]
                            for gid, days in day_assignments.items()
                            if day in days
                        ]
                        day_result = seating.assign_day(groups_on_day)
                        if day_result is None:
                            feasible = False
                            break
                        # Set the day on each assignment
                        for ba in day_result:
                            ba.day = day
                        all_bas.extend(day_result)

                    if not feasible:
                        continue

                    # Phase 3 — consistency reconciliation
                    all_bas = reconciler.reconcile(
                        day_assignments, all_bas, self.groups_by_id, self.blocks_by_id
                    )

                    # Score
                    score, breakdown = compute_total_score(day_assignments, all_bas)

                    sig = _solution_signature(day_assignments, all_bas)
                    if sig in seen_signatures:
                        continue
                    seen_signatures.add(sig)

                    sol = self._build_solution(
                        cover_pair, day_assignments, all_bas,
                        score, breakdown, iteration,
                    )
                    pool.append(sol)

                    if len(pool) >= self.n_solutions * 10:
                        break

            if len(pool) >= self.n_solutions * 3:
                break

        pool.sort(key=lambda s: s.score, reverse=True)
        return pool[: self.n_solutions]

    def _build_solution(
        self,
        cover_pair: tuple,
        day_assignments: dict,
        block_assignments: list,
        score: float,
        score_breakdown: dict,
        iteration: int,
    ) -> Solution:
        da_list = [
            GroupDayAssignment(group_id=gid, days=days)
            for gid, days in day_assignments.items()
        ]
        return Solution(
            solution_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=cover_pair,
            day_assignments=da_list,
            block_assignments=list(block_assignments),
            score=score,
            score_breakdown=score_breakdown,
            metadata={
                "solver_seed": self.rng.randint(0, 10 ** 9),
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


def _solution_signature(day_assignments: dict, block_assignments: list) -> frozenset:
    """Canonical fingerprint to detect duplicate solutions."""
    # For each group: (group_id, days, frozenset of (block_id, count) per day)
    group_day_blocks: dict = defaultdict(dict)
    for ba in block_assignments:
        group_day_blocks[ba.group_id].setdefault(ba.day, []).append((ba.block_id, ba.count))

    parts = []
    for gid, days in day_assignments.items():
        d1_blocks = frozenset(group_day_blocks[gid].get(days[0], []))
        d2_blocks = frozenset(group_day_blocks[gid].get(days[1], []))
        parts.append((gid, days, d1_blocks, d2_blocks))

    return frozenset(parts)
