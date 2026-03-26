# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
.venv/bin/python -m pytest tests/ -v

# Run a single test file
.venv/bin/python -m pytest tests/test_solver.py -v

# Run a single test
.venv/bin/python -m pytest tests/test_solver.py::test_solutions_satisfy_hard_constraints -v

# Launch the Streamlit app (from project root)
.venv/bin/streamlit run app/main.py

# Install dependencies
.venv/bin/pip install -r requirements.txt
```

## Architecture

The app is split into a core logic package (`seating_optimizer/`) and a Streamlit UI (`app/`).

### Core package (`seating_optimizer/`)

**Data flow**: `loader.py` → `models.py` → `solver.py` → `persistence.py`

- `models.py` — Frozen dataclasses `Block`, `Team`; mutable `Solution`, `TeamDayAssignment`, `TeamBlockAssignment`. All modules share these types.
- `loader.py` — `load_office_map()` parses the CSV into `Block` objects (non-zero cells only, IDs B0–B5 in row-major order). `load_teams()` parses teams.json.
- `constraints.py` — Hard constraint checkers. Key function: `valid_day_combos_for_cover_pair(cover_pair)` returns the 5 valid 2-day combos for a given cover pair (excludes the one combo {C,D} that contains neither cover day).
- `scorer.py` — `compute_total_score()` = 0.6 × consistency + 0.4 × dept_proximity. Consistency = fraction of teams with the same block on both days. Dept proximity = 1 − avg pairwise Manhattan distance / 8, averaged over all (day, dept) pairs with ≥2 teams.
- `solver.py` — Three-phase pipeline run inside `Solver.solve()`:
  1. **`DayAssigner`** — samples day combos per team; by sampling only from `valid_day_combos_for_cover_pair`, the cover constraint is satisfied by construction (no post-check needed).
  2. **`SeatingAssigner`** — per-day bin-packing: groups teams by dept, tries to fit each dept group into one block (tightest fit), splits greedily if needed, then runs `_local_swap_pass` for cross-dept swaps. **Important**: same-dept swaps are skipped in `_local_swap_pass` because the gain formula spuriously returns >0 for them (both teams count each other as a potential teammate), which causes an infinite loop.
  3. **`ConsistencyReconciler`** — post-processes to maximise teams sharing the same block on both days via direct moves.
- `updater.py` — `SolutionUpdater.update()` detects violated (team, day) pairs (where new team size exceeds block capacity), greedily relocates them, and falls back to a partial re-solve via `Solver` for teams that can't be placed. Sets `metadata["derived_from"]` to the source solution ID.
- `persistence.py` — JSON serialization of `Solution` objects; `SOLUTIONS_DIR = Path("solutions")`.

### Streamlit app (`app/`)

- `app/main.py` — Entry point / home page. Run with `streamlit run app/main.py`.
- `app/pages/01_solve.py` — Runs `Solver`, shows results in expanders, saves via `persistence.save_solution()`.
- `app/pages/02_visualize.py` — Loads a saved solution, renders the office grid per day using `grid_widget.render_grid()`.
- `app/pages/03_update.py` — Loads a solution + new teams.json, runs `SolutionUpdater`, shows before/after grid diff.
- `app/components/grid_widget.py` — Renders the 5×5 office grid using `st.columns` + HTML. Dept colors are hardcoded in `DEPT_COLORS`.
- `app/components/solution_selector.py` — `@st.cache_data`-backed selectbox over `solutions/`.

### Key constraint: Cover pair
The cover constraint (constraint 3) says two specific days A, B must exist such that every team comes on A, B, or both. The solver handles this by fixing a cover pair and only allowing teams to pick day combos that include A or B — making the constraint structurally impossible to violate rather than checking it after the fact. The outer loop cycles through all 6 possible cover pairs.

### Data files
- `data/office_map.csv` — 5×5 grid; non-zero cells are seating blocks (6 blocks, capacities 8–12, total 59 seats).
- `data/teams.json` — 22 teams across 4 departments (D1–D4), sizes 2–5, total ~70 employees.
- `solutions/` — Runtime output; solution JSON files named `solution_<id>.json`.
