from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .models import Assignment, Block, Configuration, Day, OfficeMap, Team


@dataclass(frozen=True)
class TeamOptions:
    team_id: str
    size: int
    # List of (day1, block1_id, day2, block2_id)
    assignments: List[Tuple[Day, str, Day, str]]

DayPair = Tuple[Day, Day]  # always stored as (min_day, max_day)


def _compute_team_options(
    teams: Dict[str, Team],
    office_map: OfficeMap,
    days: List[Day],
) -> List[TeamOptions]:
    blocks: List[Block] = office_map.all_blocks()

    # Precompute feasible blocks per team (capacity filter)
    feasible_blocks: Dict[str, List[Block]] = {}
    for team in teams.values():
        eligible = [b for b in blocks if b.capacity >= team.size]
        feasible_blocks[team.id] = eligible

    options: List[TeamOptions] = []
    for team in teams.values():
        blocks_for_team = feasible_blocks[team.id]
        if not blocks_for_team:
            # No possible placement for this team at all
            return []

        assignment_options: List[Tuple[Day, str, Day, str]] = []
        n_days = len(days)
        for i in range(n_days):
            for j in range(i + 1, n_days):
                d1 = days[i]
                d2 = days[j]
                for b1 in blocks_for_team:
                    for b2 in blocks_for_team:
                        assignment_options.append((d1, b1.id, d2, b2.id))

        if not assignment_options:
            return []

        options.append(
            TeamOptions(
                team_id=team.id,
                size=team.size,
                assignments=assignment_options,
            )
        )

    # Sort teams by descending size to place larger teams first
    options.sort(key=lambda o: o.size, reverse=True)
    return options


def _all_distinct_day_pairs(days: List[Day]) -> List[DayPair]:
    pairs: List[DayPair] = []
    for i in range(len(days)):
        for j in range(i + 1, len(days)):
            d1 = days[i]
            d2 = days[j]
            pairs.append((d1, d2))
    return pairs


def _satisfies_coverage_constraint(
    assignments: List[Assignment],
    all_team_ids: List[str],
    days: List[Day],
) -> bool:
    if not assignments:
        return False

    team_set = set(all_team_ids)
    teams_on_day: Dict[Day, set[str]] = {d: set() for d in days}
    for a in assignments:
        teams_on_day[a.day1].add(a.team_id)
        teams_on_day[a.day2].add(a.team_id)

    day_list = list(days)
    n = len(day_list)
    for i in range(n):
        for j in range(i + 1, n):
            d1 = day_list[i]
            d2 = day_list[j]
            if teams_on_day[d1].union(teams_on_day[d2]) == team_set:
                return True

    return False


def _satisfies_coverage_constraint_temporal(
    team_day_pairs: Dict[str, DayPair],
    all_team_ids: Iterable[str],
    days: List[Day],
) -> bool:
    team_set = set(all_team_ids)
    teams_on_day: Dict[Day, set[str]] = {d: set() for d in days}
    for team_id, (d1, d2) in team_day_pairs.items():
        teams_on_day[d1].add(team_id)
        teams_on_day[d2].add(team_id)

    day_list = list(days)
    for i in range(len(day_list)):
        for j in range(i + 1, len(day_list)):
            d1 = day_list[i]
            d2 = day_list[j]
            if teams_on_day[d1].union(teams_on_day[d2]) == team_set:
                return True
    return False


def _enumerate_temporal_mappings(
    teams: Dict[str, Team],
    days: List[Day],
    total_capacity_per_day: int,
) -> Iterator[Dict[str, DayPair]]:
    """
    Enumerate all per-team (day1, day2) assignments (ignoring blocks) that satisfy:
    - each team appears on exactly two distinct days
    - for each day, the sum of sizes of teams present that day does not exceed total office capacity
    - the coverage constraint (union over some 2 days covers all teams)
    """
    team_list = sorted(teams.values(), key=lambda t: t.size, reverse=True)
    all_day_pairs = _all_distinct_day_pairs(days)

    # State
    present_size_by_day: Dict[Day, int] = {d: 0 for d in days}
    team_day_pairs: Dict[str, DayPair] = {}

    # Enumerate by coverage pair to enforce the coverage constraint early:
    # pick two days (c1, c2) such that every team is present on at least one of them.
    # If this holds, the original "exists two days whose union covers all teams" is satisfied.
    for c1, c2 in all_day_pairs:
        allowed_for_coverage = [
            (d1, d2) for (d1, d2) in all_day_pairs if (d1 in (c1, c2) or d2 in (c1, c2))
        ]
        # Reset state between coverage pairs
        for d in days:
            present_size_by_day[d] = 0
        team_day_pairs.clear()
        if not team_list:
            yield {}
            continue

        # Iterative DFS (no recursion)
        n = len(team_list)
        next_choice_idx: List[int] = [0] * n
        chosen_pair: List[DayPair | None] = [None] * n

        def undo(i: int) -> None:
            pair = chosen_pair[i]
            if pair is None:
                return
            team = team_list[i]
            d1, d2 = pair
            present_size_by_day[d1] -= team.size
            present_size_by_day[d2] -= team.size
            team_day_pairs.pop(team.id, None)
            chosen_pair[i] = None

        idx = 0
        while idx >= 0:
            if idx == n:
                # Coverage constraint is guaranteed by allowed_for_coverage restriction.
                yield dict(team_day_pairs)
                idx -= 1
                if idx >= 0:
                    undo(idx)
                continue

            team = team_list[idx]
            assigned = False
            k = next_choice_idx[idx]
            while k < len(allowed_for_coverage):
                d1, d2 = allowed_for_coverage[k]
                add1 = present_size_by_day[d1] + team.size
                if add1 > total_capacity_per_day:
                    k += 1
                    continue
                add2 = present_size_by_day[d2] + team.size
                if add2 > total_capacity_per_day:
                    k += 1
                    continue

                # Apply
                present_size_by_day[d1] = add1
                present_size_by_day[d2] = add2
                team_day_pairs[team.id] = (d1, d2)
                chosen_pair[idx] = (d1, d2)
                next_choice_idx[idx] = k + 1  # next option when we revisit this idx

                idx += 1
                if idx < n:
                    next_choice_idx[idx] = 0
                assigned = True
                break

            if not assigned:
                next_choice_idx[idx] = 0
                idx -= 1
                if idx >= 0:
                    undo(idx)


def _enumerate_spatial_arrangements_for_day(
    teams_on_day: List[Team],
    blocks: List[Block],
) -> Iterator[Dict[str, str]]:
    """
    For a specific day, enumerate all assignments team_id -> block_id such that
    per-block used capacity does not exceed block.capacity and each team fits.
    """
    if not teams_on_day:
        yield {}
        return

    # Filter blocks that can seat at least one team that day.
    max_team_size = max(t.size for t in teams_on_day)
    eligible_blocks = [b for b in blocks if b.capacity >= max_team_size or any(b.capacity >= t.size for t in teams_on_day)]
    if not eligible_blocks:
        return

    # Heuristic: place larger teams first; fail fast.
    day_teams = sorted(teams_on_day, key=lambda t: t.size, reverse=True)

    used_by_block: Dict[str, int] = {b.id: 0 for b in eligible_blocks}

    blocks_by_id = {b.id: b for b in eligible_blocks}
    eligible_block_ids_by_team: List[List[str]] = []
    for t in day_teams:
        ids = [b.id for b in eligible_blocks if b.capacity >= t.size]
        if not ids:
            return
        eligible_block_ids_by_team.append(ids)

    assignment: Dict[str, str] = {}

    n = len(day_teams)
    next_choice_idx: List[int] = [0] * n
    chosen_block: List[str | None] = [None] * n

    def undo(i: int) -> None:
        b_id = chosen_block[i]
        if b_id is None:
            return
        t = day_teams[i]
        used_by_block[b_id] -= t.size
        assignment.pop(t.id, None)
        chosen_block[i] = None

    i = 0
    while i >= 0:
        if i == n:
            yield dict(assignment)
            i -= 1
            if i >= 0:
                undo(i)
            continue

        t = day_teams[i]
        options = eligible_block_ids_by_team[i]
        assigned = False
        k = next_choice_idx[i]
        while k < len(options):
            b_id = options[k]
            b = blocks_by_id[b_id]
            new_used = used_by_block[b_id] + t.size
            if new_used > b.capacity:
                k += 1
                continue

            used_by_block[b_id] = new_used
            assignment[t.id] = b_id
            chosen_block[i] = b_id
            next_choice_idx[i] = k + 1

            i += 1
            if i < n:
                next_choice_idx[i] = 0
            assigned = True
            break

        if not assigned:
            next_choice_idx[i] = 0
            i -= 1
            if i >= 0:
                undo(i)

    return


def find_all_configurations(
    teams: Dict[str, Team],
    office_map: OfficeMap,
    days: Optional[List[Day]] = None,
    max_solutions: Optional[int] = None,
) -> List[Configuration]:
    """Enumerate all legal seating configurations.

    A configuration is legal if:
    - Each team is assigned to exactly two distinct days.
    - On each (day, block), the sum of team sizes does not exceed block capacity.
    - There exist at least two days whose union of present teams is the full team set.
    """
    if not teams:
        return []

    if days is None:
        days = [1, 2, 3, 4, 5]

    blocks = office_map.all_blocks()
    if not blocks:
        return []

    total_capacity_per_day = sum(b.capacity for b in blocks)

    # Phase 1: temporal enumeration (team -> 2 distinct days)
    # Phase 2: for each temporal mapping, lazily enumerate per-day spatial arrangements,
    # then combine day-arrangements into full configurations.

    solutions: List[Configuration] = []
    day_list = list(days)

    any_temporal = False
    for temporal in _enumerate_temporal_mappings(
        teams=teams,
        days=days,
        total_capacity_per_day=total_capacity_per_day,
    ):
        any_temporal = True
        if max_solutions is not None and len(solutions) >= max_solutions:
            break

        teams_on_day: Dict[Day, List[Team]] = {d: [] for d in day_list}
        for team_id, (d1, d2) in temporal.items():
            t = teams[team_id]
            teams_on_day[d1].append(t)
            teams_on_day[d2].append(t)

        # Combine day-wise arrangements lazily (days are independent), without recursion
        m = len(day_list)
        if m == 0:
            continue

        chosen_by_day: Dict[Day, Dict[str, str]] = {}
        iterators: List[Iterator[Dict[str, str]]] = [
            _enumerate_spatial_arrangements_for_day(teams_on_day[day_list[0]], blocks)
        ]
        day_idx = 0

        while day_idx >= 0:
            if max_solutions is not None and len(solutions) >= max_solutions:
                break

            try:
                arr = next(iterators[day_idx])
                chosen_by_day[day_list[day_idx]] = arr

                if day_idx == m - 1:
                    assignments: List[Assignment] = []
                    for team_id, (d1, d2) in temporal.items():
                        b1_id = chosen_by_day[d1][team_id]
                        b2_id = chosen_by_day[d2][team_id]
                        assignments.append(
                            Assignment(
                                team_id=team_id,
                                day1=d1,
                                block1_id=b1_id,
                                day2=d2,
                                block2_id=b2_id,
                            )
                        )
                    solutions.append(Configuration(assignments=assignments))
                else:
                    day_idx += 1
                    it = _enumerate_spatial_arrangements_for_day(teams_on_day[day_list[day_idx]], blocks)
                    if day_idx == len(iterators):
                        iterators.append(it)
                    else:
                        iterators[day_idx] = it
            except StopIteration:
                chosen_by_day.pop(day_list[day_idx], None)
                day_idx -= 1

    if not any_temporal:
        return []

    return solutions

