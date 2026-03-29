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
- `loader.py` — `load_office_map()` parses the CSV into `Block` objects (non-zero cells only, IDs B0–BN in row-major order). `load_employees()` parses the employee CSV (columns: Display name, Group, Department). `get_groups()` aggregates employees into `Group` objects. `get_employees_by_group()` returns `{group_id: [Employee, ...]}`. `load_cold_seats(path)` parses a `Group,Block` CSV into `{group_id: block_id}`.
- `constraints.py` — Hard constraint checkers. Key functions:
  - `valid_day_combos_for_cover_pair(cover_pair)` — 5 valid 2-day combos for a cover pair.
  - `all_dept_day_assignments(cover_pair, depts)` — enumerates all 2^N ways to assign a common day (from cover pair) to each dept.
  - `check_dept_overlap_constraint(dept_map, day_assignments)` — every pair of groups in the same dept must share ≥1 day.
  - `check_column_distance_constraint(block_assignments, blocks_by_id)` — group members in different blocks must be ≤4 columns apart.
  - `check_cold_seats_constraint(block_assignments, cold_seats)` — groups with a designated block must only appear in that block.
- `scorer.py` — `compute_total_score()` = 0.6 × compactness + 0.4 × consistency. Compactness = fraction of (group, day) pairs where the group fits in a single block. Consistency = fraction of groups with the same block(s) on both their days.
- `solver.py` — Three-phase pipeline run inside `Solver.solve()`:
  1. **`DayAssigner`** — assigns day combos to groups using a **dept-common-day strategy**: each dept gets a common day from the cover pair, and every group with members in that dept must attend it. This satisfies the dept-overlap constraint (rule d) and cover constraint by construction. Groups spanning two depts have both mandatory days fixed; single-dept groups pick their second day freely. The solver enumerates all 2^N_depts dept-day combinations. Accepts `mandatory_overrides: dict` — `{group_id: [allowed_combos]}` — for the triangle strategy (see Tier-2 below).
  2. **`SeatingAssigner`** — per-day bin-packing by group: tries to fit each group in a single block (tightest fit); if too large, splits across blocks within the same column group (column distance ≤ 4). `_compute_column_groups()` pre-computes which blocks are within 4 columns of each other. Cold-seated groups are pinned to their required block; if it has insufficient capacity the group fails.
  3. **`ConsistencyReconciler`** — post-processes to maximise single-block groups that share the same block on both days. Skips multi-block groups and cold-seated groups.
  - **Tier-1 strategy**: single common day per dept × all cover pairs. Works when each dept fits within total office capacity.
  - **Tier-2 strategy** (fallback): triangle partitioning for all depts with ≥2 groups. Three sub-batches on day combos (X,Y), (X,Z), (Y,Z) guarantee pairwise overlap; max load = 2/3 × dept_total. Handles depts up to 1.5× capacity. `_valid_triangles_for_cover_pair()` and `_enumerate_triangle_configs()` support this.
- `updater.py` — `SolutionUpdater(blocks, groups_by_id)` — updates an existing solution when group sizes change, with a 3-tier fallback strategy:
  1. **Minimal repack** — keep same day assignments; pin unchanged groups in their existing blocks; re-seat only changed groups in remaining space.
  2. **Same cover pair** — if capacity fails, re-run full day + seat assignment using the original cover pair, preserving unchanged groups' day assignments wherever constraints allow.
  3. **Full solver** — fallback across all cover pairs. Returns a new `Solution` with `metadata["derived_from"]` = original `solution_id`.
- `persistence.py` — JSON serialization of `Solution` objects; `SOLUTIONS_DIR = Path("solutions")`. The GUI overrides the directory to `~/Library/Application Support/Seating Optimizer/solutions/`. `GroupBlockAssignment` includes a `count` field (employees seated in that block).

### Desktop GUI (`gui/`)

**Entry point**: `gui/main.py` — run with `.venv/bin/python -m gui.main`.

**Data flow**: `AppState` (shared state + Qt signals) → tab widgets → `OfficeGridView` (interactive grid).

#### `gui/app_state.py` — `AppState(QObject)`
Central owner of all runtime state. Holds `blocks`, `employees`, `groups`, `groups_by_id`, `employees_by_group`, `dept_map`, `cold_seats`. Signals: `solution_list_changed`, `active_solution_changed(object)`, `active_day_changed(int)`. Solutions dir: `~/Library/Application Support/Seating Optimizer/solutions/` (via `QStandardPaths`). Also checks local `solutions/` for backwards compat. File paths persisted via `QSettings("SeatingOptimizer", "SeatingOptimizer")` — keys: `office_map_path`, `employees_path`, `cold_seats_path`. `group_color(group_id)` returns a stable color hex per group (hash-based from `DEPT_COLORS` palette).

#### `gui/main_window.py` — `MainWindow(QMainWindow)`
Five-tab layout (Solve / Visualize / Update / Dept Overlap / Manual). Connects `currentChanged` to trigger `_fit_in_view()` when Visualize tab becomes active. File menu opens office map / employees CSV. Status bar shows block/group/employee/solution counts.

#### `gui/tabs/solve_tab.py` — `SolveTab`
Settings panel (office map path, employees CSV path, cold seats CSV path, n_solutions, max_iters, seed) + Run Solver button. Spawns `SolverThread`; progress bar connected to `progress` signal. Results list with Save / Delete / Visualize buttons. Schedule table shows: Group, Dept(s), Size, Day 1 → block(s), Day 2 → block(s), Single Block.

#### `gui/tabs/visualize_tab.py` — `VisualizeTab`
Solution combo + day selector (1–4 toggle buttons) + metrics bar (Score, Compactness, Consistency, Cover Days, ID) + group legend + `OfficeGridView` + block/group summary tables + **Export PDF** button. **Important**: `_select_solution_in_combo()` holds `_refreshing_combo` guard to prevent `currentIndexChanged` re-entrancy. All updates go through `_display_solution()` — never re-emit signals from within update handlers.

#### `gui/pdf_exporter.py` — `export_pdf()`
Exports the active solution to a 6-page A4 PDF (more if departments overflow). Pages 1–4: one per day, showing the office grid (rendered via `QGraphicsScene` with read-only `BlockItem`s) with a title and group count. Page 5: solution summary (ID, score, compactness, consistency, cover days), a department meeting days table (each dept's common day derived from the intersection of its groups' day assignments), and the full group schedule table. Page 6+: department attendance tables — one compact table per department showing which days each group attends (cells filled in the group's color). Uses `QPdfWriter` at 96 DPI — critical: do not change this. The default 1200 DPI causes `BlockItem` fonts to inflate ~9× relative to cell size because Qt scales point-size fonts with the painter world transform during `scene.render()`.

#### `gui/tabs/update_tab.py` — `UpdateTab`
Solution selector (combo sorted by score) + group sizes table (editable via spinboxes) + "Update Solution" button. Spawns `UpdaterThread`; on completion populates a **diff table** showing every group's changes: size (blue highlight), days (red if changed), block assignments (green if changed). "Save New Solution" persists the result and emits `solution_list_changed`. "Export PDF" exports the updated solution. **Important**: size_overrides only includes groups where the spinbox value differs from the current group size.

#### `gui/tabs/dept_overlap_tab.py` — `DeptOverlapTab`
Solution combo + department combo. Renders a read-only attendance grid: rows = groups in the selected department, columns = Day 1–4, cells filled in the group's color when the group attends that day (light grey otherwise). Syncs with `active_solution_changed` and `solution_list_changed`.

#### `gui/tabs/manual_tab.py` — `ManualTab`
Placeholder — not yet updated for the employee/group model.

#### `gui/widgets/block_item.py` — `BlockItem(QGraphicsObject)`
Paints one seating block: rounded rect, block ID, capacity bar (green/orange/red), group chips. Each chip shows `"GroupName ×N"` colored by group. Hover over a chip shows a tooltip with employee names (`employees_by_group` passed at construction). Initiates drag via `QDrag` with MIME `application/x-team-chip` = `{"team_id": group_id, "from_block_id": "..."}`. **Important**: `QGraphicsItem.ItemIsDropEnabled` flag does not exist in PySide6 6.10 — use `setAcceptDrops(True)` only. Accepts hover events (`setAcceptHoverEvents(True)`) for tooltip display.

#### `gui/widgets/office_grid.py` — `OfficeGridView(QGraphicsView)`
Interactive office grid. `load(solution, day, blocks, groups_by_id, group_color_fn, employees_by_group)` builds a `QGraphicsScene` with `BlockItem` objects. Grid dimensions computed dynamically: `max(b.row)+1` × `max(b.col)+1`. **Important**: `fitInView` uses `QTimer.singleShot(0, ...)` everywhere — the viewport size is not reliable until the event loop runs. `setAcceptDrops(True)` must be set on both the view and each `BlockItem`. `highlight_for_group(group_id, day)` / `clear_highlights()` set external highlights on all block items.

#### `gui/threads/`
- `SolverThread(QThread)` — wraps `Solver.solve(progress_callback)`; takes `blocks` and `groups`; signals: `progress(int, int)`, `finished(list)`, `error(str)`.
- `UpdaterThread(QThread)` — wraps `SolutionUpdater.update(solution, size_overrides)`; takes `blocks`, `groups_by_id`, `solution`, `size_overrides`; signals: `finished(object)`, `error(str)`.

### Key constraints

| Rule | Description | How enforced |
|------|-------------|--------------|
| a | Each employee attends exactly 2 days | Group gets exactly 2-day combo |
| b | Cover pair: 2 days covering everyone | All common days come from cover pair → by construction |
| c | Same group → same days | Group is the atomic scheduling unit |
| d | Every dept pair shares ≥1 day | Dept-common-day strategy (Tier-1) or triangle partitioning (Tier-2 for large depts) |
| e | Same-group employees ≤4 columns apart | SeatingAssigner only overflows within column groups |
| f | Cold-seated groups use their designated block | SeatingAssigner pins group to required block; ConsistencyReconciler skips them |

### Data files
- `data/office_map.csv` — Grid CSV; non-zero cells are seating blocks, parsed row-major into Block objects.
- `data/Employees list for seating with fake department.csv` — Employee list; columns: Start date, Display name, Group, Team, Reports to, Department. Default input file.
- `data/cold_seats.csv` — Optional; columns: `Group`, `Block`. Maps group names to their required block ID. Bundled default; user can override via the Solve tab file picker.
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
