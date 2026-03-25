# Seating Optimizer (Office)

Generate **all legal seating configurations** for an office, given:

- A set of **teams** (each has a fixed size and a department).
- An **office map** (grid) whose non-zero cells are **seating blocks** with fixed capacity.
- A 5-day work week (days are represented as integers **1..5**).

This project currently focuses on **enumeration** (not “best” optimization): it finds and optionally saves **every** configuration that satisfies the rules below.

## Problem definition (constraints)

A **configuration** assigns each team to **two** `(day, block)` pairs:

`(day_1, block_1)` and `(day_2, block_2)` where:

1. **Exactly 2 distinct days per team**: `day_1 != day_2`, both in `1..5`.
2. **Capacity per block per day**: for every `(day, block)`,
   the sum of team sizes assigned to that `(day, block)` does not exceed the block’s capacity.
3. **Coverage constraint (two-day union)**: there exist **at least two distinct days** `d1 != d2` such that
   the union of the teams present on those two days equals the full team set.

## Core approach (how enumeration works)

The enumerator uses **backtracking with pruning**:

- Precompute per-team feasible options:
  - Choose 2 days out of 5 (10 pairs)
  - For each chosen day, choose a block whose capacity is at least the team size
- Search teams in **descending size order** to fail fast on capacity constraints.
- Maintain incremental state while backtracking:
  - `usage[day][block_id]`: current used seats on that day/block
  - `assignments`: partial list of team assignments
- When a full assignment is constructed, validate the **coverage constraint** and record the configuration.

For practical runs, you can cap enumeration with `--max-solutions`.

## Repository structure

Recommended “definition files” locations:

- `data/teams.json`: teams definition
- `data/office_map.csv`: office seating blocks definition (grid)

Output location:

- `output/configurations.json`: all configurations (JSON array)

Code:

- `seating_optimizer/models.py`: entity dataclasses (`Team`, `Block`, `OfficeMap`, `Assignment`, `Configuration`)
- `seating_optimizer/io.py`: input loaders (`load_teams`, `load_office_map`)
- `seating_optimizer/optimizer.py`: core enumeration (`find_all_configurations`)
- `seating_optimizer/api.py`: convenience API + serialization (`save_configurations`, `run_optimization_from_files`)
- `main.py`: CLI entry point

## Input formats

### Teams (`data/teams.json`)

JSON object mapping `team_id` to team info:

```json
{
  "team_alpha": { "name": "Team Alpha", "size": 5, "department": "Engineering" },
  "team_beta":  { "name": "Team Beta",  "size": 4, "department": "Product" }
}
```

Required fields per team:

- `name` (string)
- `size` (positive integer)

Optional field:

- `department` (string; defaults to `""`)

### Office map (`data/office_map.csv`)

CSV matrix of integers:

- `0` means **not a seating block**
- Positive integer means a **seating block** with that **capacity**

Example:

```text
4,4,0
0,4,4
```

Each non-zero cell becomes a `Block` with ID `r{row}_c{col}` (0-based indices).

## Running

### CLI

From the project root:

```bash
python main.py --teams data/teams.json --office-map data/office_map.csv --output output/configurations.json
```

Optionally cap solutions:

```bash
python main.py --max-solutions 100
```

### As a library

```python
from seating_optimizer.api import run_optimization_from_files, save_configurations

result = run_optimization_from_files("data/teams.json", "data/office_map.csv", max_solutions=100)
teams = result["teams"]
configs = result["configurations"]

save_configurations(configs, teams, "output/configurations.json")
```

## Notes / future extensions

- Enumeration can grow quickly with more teams/blocks; consider adding:
  - symmetry reduction,
  - stronger pruning using coverage feasibility checks during partial assignment,
  - or switching to a constraint solver if you later want “best” schedules instead of “all”.

