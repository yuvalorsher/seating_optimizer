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

# Launch the desktop GUI (dev mode, from project root)
.venv/bin/python -m gui.main

# Build macOS .app bundle
.venv/bin/pyinstaller build.spec --clean -y

# Install dependencies
.venv/bin/pip install -r requirements.txt
```

## Architecture

The app is split into a core logic package (`seating_optimizer/`) and a PySide6 desktop UI (`gui/`).

### Core package (`seating_optimizer/`)

**Data flow**: `loader.py` → `models.py` → `solver.py` → `persistence.py`

- `models.py` — Frozen dataclasses `Block`, `Team`; mutable `Solution`, `TeamDayAssignment`, `TeamBlockAssignment`. All modules share these types.
- `loader.py` — `load_office_map()` parses the CSV into `Block` objects (non-zero cells only, IDs B0–BN in row-major order). `load_teams()` parses teams.json.
- `constraints.py` — Hard constraint checkers. Key function: `valid_day_combos_for_cover_pair(cover_pair)` returns the 5 valid 2-day combos for a given cover pair (excludes the one combo {C,D} that contains neither cover day).
- `scorer.py` — `compute_total_score()` = 0.6 × consistency + 0.4 × dept_proximity. Consistency = fraction of teams with the same block on both days. Dept proximity = 1 − avg pairwise Manhattan distance / 8, averaged over all (day, dept) pairs with ≥2 teams.
- `solver.py` — Three-phase pipeline run inside `Solver.solve()`:
  1. **`DayAssigner`** — samples day combos per team; by sampling only from `valid_day_combos_for_cover_pair`, the cover constraint is satisfied by construction (no post-check needed).
  2. **`SeatingAssigner`** — per-day bin-packing: groups teams by dept, tries to fit each dept group into one block (tightest fit), splits greedily if needed, then runs `_local_swap_pass` for cross-dept swaps. **Important**: same-dept swaps are skipped in `_local_swap_pass` because the gain formula spuriously returns >0 for them (both teams count each other as a potential teammate), which causes an infinite loop.
  3. **`ConsistencyReconciler`** — post-processes to maximise teams sharing the same block on both days via direct moves.
- `updater.py` — `SolutionUpdater.update()` detects violated (team, day) pairs (where new team size exceeds block capacity), greedily relocates them, and falls back to a partial re-solve via `Solver` for teams that can't be placed. Sets `metadata["derived_from"]` to the source solution ID.
- `persistence.py` — JSON serialization of `Solution` objects; `SOLUTIONS_DIR = Path("solutions")`. The GUI overrides the directory to `~/Library/Application Support/Seating Optimizer/solutions/`.

### Desktop GUI (`gui/`)

**Entry point**: `gui/main.py` — run with `.venv/bin/python -m gui.main`.

**Data flow**: `AppState` (shared state + Qt signals) → tab widgets → `OfficeGridView` (interactive grid).

#### `gui/app_state.py` — `AppState(QObject)`
Central owner of all runtime state. Signals: `solution_list_changed`, `active_solution_changed(object)`, `active_day_changed(int)`. Solutions dir: `~/Library/Application Support/Seating Optimizer/solutions/` (via `QStandardPaths`). Also checks local `solutions/` for backwards compat. File paths persisted via `QSettings("SeatingOptimizer", "SeatingOptimizer")`.

#### `gui/main_window.py` — `MainWindow(QMainWindow)`
Three-tab layout (Solve / Visualize / Update). Connects `currentChanged` to trigger `_fit_in_view()` when Visualize tab becomes active. File menu opens office map / teams JSON. Status bar shows block/team/solution counts.

#### `gui/tabs/solve_tab.py` — `SolveTab`
Settings panel (file paths, n_solutions, max_iters, seed) + Run Solver button. Spawns `SolverThread`; progress bar connected to `progress` signal. Results list with Save / Delete / Visualize buttons. Schedule table below.

#### `gui/tabs/visualize_tab.py` — `VisualizeTab`
Solution combo + day selector (1–4 toggle buttons) + metrics bar + dept legend + `OfficeGridView` + block/team summary tables. **Important**: `_select_solution_in_combo()` holds `_refreshing_combo` guard to prevent `currentIndexChanged` re-entrancy. All updates go through `_display_solution()` — never re-emit signals from within update handlers.

#### `gui/tabs/update_tab.py` — `UpdateTab`
Load base solution + new teams JSON → diff table (red = violated, yellow = changed) → `UpdaterThread` → before/after read-only grids.

#### `gui/widgets/office_grid.py` — `OfficeGridView(QGraphicsView)`
Interactive office grid. `load(solution, day, blocks, teams_by_id, dept_color_fn)` builds a `QGraphicsScene` with `BlockItem` objects. Grid dimensions computed dynamically: `max(b.row)+1` × `max(b.col)+1`. **Important**: `fitInView` uses `QTimer.singleShot(0, ...)` everywhere (in `_rebuild_scene`, `showEvent`, `resizeEvent`) — the viewport size is not reliable until the event loop runs. `setAcceptDrops(True)` must be set on both the view and each `BlockItem` for drag events to fire.

#### `gui/widgets/block_item.py` — `BlockItem(QGraphicsObject)`
Paints one seating block: rounded rect, block ID, capacity bar (green/orange/red), team chips. Initiates drag via `QDrag` with MIME `application/x-team-chip` = `{"team_id": "...", "from_block_id": "..."}`. Validates capacity in `dragEnterEvent` (green/red border highlight). Emits `team_dropped(team_id, from_block_id, to_block_id)` on valid drop. **Important**: `QGraphicsItem.ItemIsDropEnabled` flag does not exist in PySide6 6.10 — use `setAcceptDrops(True)` only.

#### `gui/threads/`
- `SolverThread(QThread)` — wraps `Solver.solve(progress_callback)`; signals: `progress(int, int)`, `finished(list)`, `error(str)`.
- `UpdaterThread(QThread)` — wraps `SolutionUpdater.update()`; signals: `finished(object)`, `error(str)`.

### Key constraint: Cover pair
The cover constraint (constraint 3) says two specific days A, B must exist such that every team comes on A, B, or both. The solver handles this by fixing a cover pair and only allowing teams to pick day combos that include A or B — making the constraint structurally impossible to violate rather than checking it after the fact. The outer loop cycles through all 6 possible cover pairs.

### Data files
- `data/office_map.csv` — Grid CSV; non-zero cells are seating blocks, parsed row-major into Block objects.
- `data/teams.json` — Teams with name, size, department.
- `solutions/` — Legacy Streamlit output (auto-loaded by GUI for backwards compat).
- `~/Library/Application Support/Seating Optimizer/solutions/` — Primary solutions dir when running as .app.

### Packaging
- `build.spec` — PyInstaller spec; bundles `data/` files, excludes streamlit/pandas.
- Output: `dist/SeatingOptimizer.app` (~88MB). Drag to `/Applications` to install.
- Bundled data files land at `Contents/Resources/data/`; `sys._MEIPASS` points to `Contents/Resources/`.
