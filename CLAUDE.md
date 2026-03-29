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

- `models.py` — Frozen dataclasses `Block`, `Employee`, `Group`; mutable `Solution`, `GroupDayAssignment`, `GroupBlockAssignment`. All modules share these types.
- `loader.py` — `load_office_map()` parses the CSV into `Block` objects (non-zero cells only, IDs B0–BN in row-major order). `load_employees()` parses the employee CSV (columns: Display name, Group, Department). `get_groups()` aggregates employees into `Group` objects. `get_employees_by_group()` returns `{group_id: [Employee, ...]}`.
- `constraints.py` — Hard constraint checkers. Key functions:
  - `valid_day_combos_for_cover_pair(cover_pair)` — 5 valid 2-day combos for a cover pair.
  - `all_dept_day_assignments(cover_pair, depts)` — enumerates all 2^N ways to assign a common day (from cover pair) to each dept.
  - `check_dept_overlap_constraint(dept_map, day_assignments)` — every pair of groups in the same dept must share ≥1 day.
  - `check_column_distance_constraint(block_assignments, blocks_by_id)` — group members in different blocks must be ≤4 columns apart.
- `scorer.py` — `compute_total_score()` = 0.6 × compactness + 0.4 × consistency. Compactness = fraction of (group, day) pairs where the group fits in a single block. Consistency = fraction of groups with the same block(s) on both their days.
- `solver.py` — Three-phase pipeline run inside `Solver.solve()`:
  1. **`DayAssigner`** — assigns day combos to groups using a **dept-common-day strategy**: each dept gets a common day from the cover pair, and every group with members in that dept must attend it. This satisfies the dept-overlap constraint (rule d) and cover constraint by construction. Groups spanning two depts have both mandatory days fixed; single-dept groups pick their second day freely. The solver enumerates all 2^N_depts dept-day combinations.
  2. **`SeatingAssigner`** — per-day bin-packing by group: tries to fit each group in a single block (tightest fit); if too large, splits across blocks within the same column group (column distance ≤ 4). `_compute_column_groups()` pre-computes which blocks are within 4 columns of each other.
  3. **`ConsistencyReconciler`** — post-processes to maximise single-block groups that share the same block on both days. Skips multi-block groups.
- `updater.py` — Stub only; raises `NotImplementedError`. Not yet updated for the employee/group model.
- `persistence.py` — JSON serialization of `Solution` objects; `SOLUTIONS_DIR = Path("solutions")`. The GUI overrides the directory to `~/Library/Application Support/Seating Optimizer/solutions/`. `GroupBlockAssignment` includes a `count` field (employees seated in that block).

### Desktop GUI (`gui/`)

**Entry point**: `gui/main.py` — run with `.venv/bin/python -m gui.main`.

**Data flow**: `AppState` (shared state + Qt signals) → tab widgets → `OfficeGridView` (interactive grid).

#### `gui/app_state.py` — `AppState(QObject)`
Central owner of all runtime state. Holds `blocks`, `employees`, `groups`, `groups_by_id`, `employees_by_group`, `dept_map`. Signals: `solution_list_changed`, `active_solution_changed(object)`, `active_day_changed(int)`. Solutions dir: `~/Library/Application Support/Seating Optimizer/solutions/` (via `QStandardPaths`). Also checks local `solutions/` for backwards compat. File paths persisted via `QSettings("SeatingOptimizer", "SeatingOptimizer")` — keys: `office_map_path`, `employees_path`. `group_color(group_id)` returns a stable color hex per group (hash-based from `DEPT_COLORS` palette).

#### `gui/main_window.py` — `MainWindow(QMainWindow)`
Four-tab layout (Solve / Visualize / Update / Manual). Connects `currentChanged` to trigger `_fit_in_view()` when Visualize tab becomes active. File menu opens office map / employees CSV. Status bar shows block/group/employee/solution counts.

#### `gui/tabs/solve_tab.py` — `SolveTab`
Settings panel (office map path, employees CSV path, n_solutions, max_iters, seed) + Run Solver button. Spawns `SolverThread`; progress bar connected to `progress` signal. Results list with Save / Delete / Visualize buttons. Schedule table shows: Group, Dept(s), Size, Day 1 → block(s), Day 2 → block(s), Single Block.

#### `gui/tabs/visualize_tab.py` — `VisualizeTab`
Solution combo + day selector (1–4 toggle buttons) + metrics bar (Score, Compactness, Consistency, Cover Days, ID) + group legend + `OfficeGridView` + block/group summary tables. **Important**: `_select_solution_in_combo()` holds `_refreshing_combo` guard to prevent `currentIndexChanged` re-entrancy. All updates go through `_display_solution()` — never re-emit signals from within update handlers.

#### `gui/tabs/update_tab.py` — `UpdateTab`
Placeholder — not yet updated for the employee/group model.

#### `gui/tabs/manual_tab.py` — `ManualTab`
Placeholder — not yet updated for the employee/group model.

#### `gui/widgets/block_item.py` — `BlockItem(QGraphicsObject)`
Paints one seating block: rounded rect, block ID, capacity bar (green/orange/red), group chips. Each chip shows `"GroupName ×N"` colored by group. Hover over a chip shows a tooltip with employee names (`employees_by_group` passed at construction). Initiates drag via `QDrag` with MIME `application/x-team-chip` = `{"team_id": group_id, "from_block_id": "..."}`. **Important**: `QGraphicsItem.ItemIsDropEnabled` flag does not exist in PySide6 6.10 — use `setAcceptDrops(True)` only. Accepts hover events (`setAcceptHoverEvents(True)`) for tooltip display.

#### `gui/widgets/office_grid.py` — `OfficeGridView(QGraphicsView)`
Interactive office grid. `load(solution, day, blocks, groups_by_id, group_color_fn, employees_by_group)` builds a `QGraphicsScene` with `BlockItem` objects. Grid dimensions computed dynamically: `max(b.row)+1` × `max(b.col)+1`. **Important**: `fitInView` uses `QTimer.singleShot(0, ...)` everywhere — the viewport size is not reliable until the event loop runs. `setAcceptDrops(True)` must be set on both the view and each `BlockItem`. `highlight_for_group(group_id, day)` / `clear_highlights()` set external highlights on all block items.

#### `gui/threads/`
- `SolverThread(QThread)` — wraps `Solver.solve(progress_callback)`; takes `blocks` and `groups`; signals: `progress(int, int)`, `finished(list)`, `error(str)`.
- `UpdaterThread(QThread)` — stub; wraps `SolutionUpdater` (which raises NotImplementedError).

### Key constraints

| Rule | Description | How enforced |
|------|-------------|--------------|
| a | Each employee attends exactly 2 days | Group gets exactly 2-day combo |
| b | Cover pair: 2 days covering everyone | All common days come from cover pair → by construction |
| c | Same group → same days | Group is the atomic scheduling unit |
| d | Every dept pair shares ≥1 day | Dept-common-day strategy: all groups in dept D attend `cd_D` |
| e | Same-group employees ≤4 columns apart | SeatingAssigner only overflows within column groups |

### Data files
- `data/office_map.csv` — Grid CSV; non-zero cells are seating blocks, parsed row-major into Block objects.
- `data/Employees list for seating with fake department.csv` — Employee list; columns: Start date, Display name, Group, Team, Reports to, Department. Default input file.
- `solutions/` — Legacy output (auto-loaded by GUI for backwards compat).
- `~/Library/Application Support/Seating Optimizer/solutions/` — Primary solutions dir when running as .app.

### Solution JSON format
```json
{
  "solution_id": "a1b2c3d4",
  "cover_pair": [1, 2],
  "day_assignments": [{"group_id": "AI", "days": [1, 3]}],
  "block_assignments": [{"group_id": "AI", "day": 1, "block_id": "B0", "count": 10}],
  "score": 0.967,
  "score_breakdown": {"compactness": 1.0, "consistency": 0.917}
}
```
A group may have **multiple** `block_assignments` for the same day if it overflows across blocks.

### Packaging
- `build.spec` — PyInstaller spec; bundles `data/` files, excludes streamlit/pandas.
- Output: `dist/SeatingOptimizer.app`. Drag to `/Applications` to install.
- Bundled data files land at `Contents/Resources/data/`; `sys._MEIPASS` points to `Contents/Resources/`.
- **After any code change, the app must be rebuilt** with `.venv/bin/pyinstaller build.spec --clean -y` before the changes are visible in `dist/SeatingOptimizer` or `dist/SeatingOptimizer.app`. Use `.venv/bin/python -m gui.main` for rapid iteration without rebuilding.
