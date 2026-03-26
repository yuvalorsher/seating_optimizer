import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd
from pathlib import Path

from seating_optimizer.loader import load_office_map, load_teams
from seating_optimizer.solver import Solver
from seating_optimizer.persistence import save_solution, SOLUTIONS_DIR
from seating_optimizer.models import DAYS

st.set_page_config(page_title="Solve — Seating Optimizer", layout="wide")
st.title("Run Solver")

# ── Sidebar controls ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Solver settings")
    n_solutions = st.slider("Number of solutions to find", 1, 20, 5)
    max_iters = st.slider("Max iterations per cover pair", 50, 500, 200, step=50)
    seed_input = st.number_input("Random seed (0 = random)", min_value=0, value=42)
    seed = int(seed_input) if seed_input > 0 else None

    st.divider()
    data_dir = Path("data")
    office_map_path = st.text_input("Office map CSV", str(data_dir / "office_map.csv"))
    teams_path = st.text_input("Teams JSON", str(data_dir / "teams.json"))

    run_btn = st.button("Run Solver", type="primary", use_container_width=True)

# ── Main area ────────────────────────────────────────────────────────────────
if run_btn:
    try:
        blocks = load_office_map(office_map_path)
        teams = load_teams(teams_path)
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    st.info(
        f"Loaded {len(blocks)} seating blocks "
        f"(total capacity {sum(b.capacity for b in blocks)}) "
        f"and {len(teams)} teams "
        f"(total {sum(t.size for t in teams)} employees)."
    )

    progress_bar = st.progress(0)
    status_text = st.empty()
    total_iters = 6 * max_iters

    def progress_callback(done, total):
        pct = min(done / total, 1.0)
        progress_bar.progress(pct)
        status_text.text(f"Searching… iteration {done}/{total}")

    solver = Solver(
        blocks=blocks,
        teams=teams,
        n_solutions=n_solutions,
        max_iterations_per_cover=max_iters,
        seed=seed,
    )
    solutions = solver.solve(progress_callback=progress_callback)
    progress_bar.progress(1.0)
    status_text.text(f"Done. Found {len(solutions)} solution(s).")

    st.session_state["last_solutions"] = solutions
    st.success(f"Found {len(solutions)} solution(s). Showing top results below.")

    teams_by_id = {t.team_id: t for t in teams}
    blocks_by_id = {b.block_id: b for b in blocks}

    for idx, sol in enumerate(solutions):
        with st.expander(
            f"Solution {idx + 1}  |  Score: {sol.score:.3f}  "
            f"(consistency={sol.score_breakdown.get('consistency', 0):.2f}, "
            f"dept_proximity={sol.score_breakdown.get('dept_proximity', 0):.2f})  "
            f"|  Cover days: {sol.cover_pair}",
            expanded=(idx == 0),
        ):
            col_save, col_info = st.columns([1, 3])
            with col_save:
                if st.button(f"Save solution {idx + 1}", key=f"save_{idx}"):
                    path = save_solution(sol, SOLUTIONS_DIR)
                    st.success(f"Saved to {path}")

            with col_info:
                # Day assignment table
                rows = []
                for da in sol.day_assignments:
                    team = teams_by_id.get(da.team_id)
                    b_day1 = sol.get_team_block(da.team_id, da.days[0])
                    b_day2 = sol.get_team_block(da.team_id, da.days[1])
                    rows.append({
                        "Team": team.name if team else da.team_id,
                        "Dept": team.department if team else "?",
                        "Size": team.size if team else "?",
                        f"Day {da.days[0]}": b_day1 or "-",
                        f"Day {da.days[1]}": b_day2 or "-",
                        "Same block": "Yes" if b_day1 == b_day2 else "No",
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

elif "last_solutions" in st.session_state:
    st.info("Showing results from previous run. Press 'Run Solver' to find new solutions.")
    solutions = st.session_state["last_solutions"]
    teams_by_id: dict = {}
    for sol in solutions:
        for da in sol.day_assignments:
            if da.team_id not in teams_by_id:
                teams_by_id[da.team_id] = type(
                    "T", (), {"name": da.team_id, "department": "?", "size": "?"}
                )()
    for idx, sol in enumerate(solutions):
        with st.expander(
            f"Solution {idx + 1}  |  Score: {sol.score:.3f}  "
            f"|  Cover days: {sol.cover_pair}",
        ):
            if st.button(f"Save solution {idx + 1}", key=f"save_cached_{idx}"):
                path = save_solution(sol, SOLUTIONS_DIR)
                st.success(f"Saved to {path}")
else:
    st.write("Configure settings in the sidebar and press **Run Solver**.")
