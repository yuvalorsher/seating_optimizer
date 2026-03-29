from __future__ import annotations
import uuid
from datetime import datetime, timezone

from .models import (
    DAYS, Group, GroupDayAssignment, GroupBlockAssignment, Solution
)
from .scorer import compute_total_score
from .solver import SeatingAssigner, ConsistencyReconciler
from .constraints import (
    valid_day_combos_for_cover_pair, all_dept_day_assignments,
)
from .loader import get_department_map


class SolutionUpdater:
    """
    Update an existing solution when group sizes change, minimising disruption.

    Strategy (in order of preference):
    1. Keep same day assignments. Re-seat only changed groups; pin the rest.
    2. Keep same cover pair, re-run day + seat assignment (preserving unchanged
       groups' days where constraints allow).
    3. Full solver across all cover pairs.
    """

    def __init__(self, blocks: list, groups_by_id: dict):
        self.blocks = blocks
        self.blocks_by_id = {b.block_id: b for b in blocks}
        self.groups_by_id = groups_by_id

    def update(self, solution: Solution, size_overrides: dict) -> Solution:
        """
        size_overrides: {group_id: new_size}
        Returns a new Solution derived from the given one.
        """
        # Build updated group objects
        updated_groups_by_id: dict = {}
        for gid, group in self.groups_by_id.items():
            new_size = size_overrides.get(gid, group.size)
            updated_groups_by_id[gid] = Group(
                group_id=gid,
                name=group.name,
                size=new_size,
                departments=group.departments,
            )
        updated_groups = list(updated_groups_by_id.values())

        changed_gids = {
            gid for gid, ns in size_overrides.items()
            if ns != self.groups_by_id.get(gid, Group("", "", 0, frozenset())).size
        }

        orig_day_map = {da.group_id: da.days for da in solution.day_assignments}

        # --- Strategy 1: same days, minimal block repack ---
        new_bas = self._minimal_repack(
            orig_day_map, changed_gids, updated_groups_by_id, solution
        )
        if new_bas is not None:
            return self._build_solution(solution, orig_day_map, new_bas, "minimal_repack")

        # --- Strategy 2: same cover pair, re-run day + seat ---
        import random
        rng = random.Random(42)
        dept_map = get_department_map(updated_groups)
        depts = list(dept_map.keys())
        reconciler = ConsistencyReconciler()

        for dept_combo in all_dept_day_assignments(solution.cover_pair, depts):
            day_assignments = self._assign_preserving(
                solution.cover_pair, dept_combo, updated_groups,
                orig_day_map, rng
            )
            if day_assignments is None:
                continue

            seating = SeatingAssigner(self.blocks)
            all_bas, feasible = self._seat_all_days(
                day_assignments, updated_groups_by_id, seating
            )
            if not feasible:
                continue

            all_bas = reconciler.reconcile(
                day_assignments, all_bas, updated_groups_by_id, self.blocks_by_id
            )
            return self._build_solution(
                solution, day_assignments, all_bas, "same_cover_pair"
            )

        # --- Strategy 3: full solver ---
        from .solver import Solver
        solver = Solver(
            self.blocks, updated_groups,
            n_solutions=1, max_iterations_per_cover=200,
        )
        sols = solver.solve()
        if sols:
            sols[0].metadata["derived_from"] = solution.solution_id
            return sols[0]

        raise RuntimeError("No feasible updated solution found.")

    # ------------------------------------------------------------------

    def _minimal_repack(
        self,
        orig_day_map: dict,
        changed_gids: set,
        updated_groups_by_id: dict,
        solution: Solution,
    ):
        """
        Keep same day assignments. Pin unchanged groups in existing blocks.
        Re-seat changed groups in remaining space.
        Returns list[GroupBlockAssignment] or None if infeasible.
        """
        all_bas: list = []

        for day in DAYS:
            current_load = {b.block_id: 0 for b in self.blocks}
            groups_on_day_ids = [
                gid for gid, days in orig_day_map.items() if day in days
            ]

            # Pin unchanged groups first (keep exact block assignments)
            for gid in groups_on_day_ids:
                if gid in changed_gids:
                    continue
                for block_id, count in solution.get_group_blocks(gid, day):
                    all_bas.append(GroupBlockAssignment(
                        group_id=gid, day=day, block_id=block_id, count=count,
                    ))
                    current_load[block_id] += count

            # Re-seat changed groups
            changed_today = sorted(
                [
                    updated_groups_by_id[gid]
                    for gid in groups_on_day_ids
                    if gid in changed_gids and gid in updated_groups_by_id
                ],
                key=lambda g: -g.size,
            )

            for group in changed_today:
                existing = solution.get_group_blocks(group.group_id, day)
                placed = self._try_place_in_existing(
                    group, existing, current_load, all_bas, day
                )
                if not placed:
                    seating = SeatingAssigner(self.blocks)
                    assignment = seating._place_group(group, current_load)
                    if assignment is None:
                        return None
                    for block_id, count in assignment:
                        all_bas.append(GroupBlockAssignment(
                            group_id=group.group_id, day=day,
                            block_id=block_id, count=count,
                        ))
                        current_load[block_id] += count

        return all_bas

    def _try_place_in_existing(
        self, group, existing: list, current_load: dict, all_bas: list, day: int
    ) -> bool:
        """Try to fit group within its existing blocks. Returns True on success."""
        if not existing:
            return False
        existing_bids = [bid for bid, _ in existing]
        total_avail = sum(
            self.blocks_by_id[bid].capacity - current_load[bid]
            for bid in existing_bids
            if bid in self.blocks_by_id
        )
        if total_avail < group.size:
            return False
        remaining = group.size
        for bid in existing_bids:
            if bid not in self.blocks_by_id:
                continue
            avail = self.blocks_by_id[bid].capacity - current_load[bid]
            take = min(remaining, avail)
            if take > 0:
                all_bas.append(GroupBlockAssignment(
                    group_id=group.group_id, day=day, block_id=bid, count=take,
                ))
                current_load[bid] += take
                remaining -= take
        return remaining == 0

    def _assign_preserving(
        self,
        cover_pair: tuple,
        dept_combo: dict,
        updated_groups: list,
        orig_day_map: dict,
        rng,
    ):
        """Assign days, preferring original assignments where constraints allow."""
        valid_combos = valid_day_combos_for_cover_pair(cover_pair)
        result: dict = {}

        for group in updated_groups:
            mandatory = set()
            for dept in group.departments:
                if dept in dept_combo:
                    mandatory.add(dept_combo[dept])

            if len(mandatory) > 2:
                return None

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
                orig = orig_day_map.get(group.group_id)
                result[group.group_id] = (
                    orig if orig and orig in eligible
                    else rng.choice(eligible)
                )

            else:
                orig = orig_day_map.get(group.group_id)
                result[group.group_id] = (
                    orig if orig and orig in valid_combos
                    else rng.choice(valid_combos)
                )

        return result

    def _seat_all_days(
        self, day_assignments: dict, groups_by_id_updated: dict, seating: SeatingAssigner
    ) -> tuple:
        """Returns (all_bas, feasible)."""
        all_bas: list = []
        for day in DAYS:
            groups_on_day = [
                groups_by_id_updated[gid]
                for gid, days in day_assignments.items()
                if day in days
            ]
            day_result = seating.assign_day(groups_on_day)
            if day_result is None:
                return [], False
            for ba in day_result:
                ba.day = day
            all_bas.extend(day_result)
        return all_bas, True

    def _build_solution(
        self,
        orig: Solution,
        day_assignments,
        block_assignments: list,
        strategy: str,
    ) -> Solution:
        if isinstance(day_assignments, dict):
            da_list = [
                GroupDayAssignment(group_id=gid, days=days)
                for gid, days in day_assignments.items()
            ]
            day_map = day_assignments
        else:
            da_list = list(day_assignments)
            day_map = {da.group_id: da.days for da in da_list}

        score, breakdown = compute_total_score(day_map, block_assignments)

        return Solution(
            solution_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=orig.cover_pair,
            day_assignments=da_list,
            block_assignments=list(block_assignments),
            score=score,
            score_breakdown=breakdown,
            metadata={
                "derived_from": orig.solution_id,
                "update_strategy": strategy,
            },
        )
