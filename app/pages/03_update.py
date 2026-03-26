import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
import tempfile
import streamlit as st
import pandas as pd
from pathlib import Path

from seating_optimizer.loader import load_office_map, load_teams
from seating_optimizer.updater import SolutionUpdater
from seating_optimizer.persistence import save_solution, SOLUTIONS_DIR
from app.components.solution_selector import render_solution_selector
from app.components.grid_widget import render_grid

st.set_page_config(page_title="Update — Seating Optimizer", layout="wide")
st.title("Update Solution")

# Load static data
data_dir = Path("data")
try:
    blocks = load_office_map(str(data_dir / "office_map.csv"))
    old_teams = load_teams(str(data_dir / "teams.json"))
    old_teams_by_id = {t.team_id: t for t in old_teams}
except Exception as e:
    st.error(f"Failed to load data files: {e}")
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Inputs")
    solution = render_solution_selector("Base solution to update")
    st.divider()
    uploaded = st.file_uploader("Upload updated teams.json", type=["json"])
    run_btn = st.button("Run Updater", type="primary", use_container_width=True, disabled=solution is None or uploaded is None)

if solution is None:
    st.write("Select a base solution and upload an updated teams.json to begin.")
    st.stop()

# ── Show change diff before running ─────────────────────────────────────────
if uploaded is not None:
    try:
        new_teams_raw = json.load(uploaded)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(new_teams_raw, tmp)
            tmp_path = tmp.name
        new_teams = load_teams(tmp_path)
        new_teams_by_id = {t.team_id: t for t in new_teams}
    except Exception as e:
        st.error(f"Failed to parse teams.json: {e}")
        st.stop()

    # Show size changes
    change_rows = []
    for tid, old_t in old_teams_by_id.items():
        new_t = new_teams_by_id.get(tid)
        old_size = old_t.size
        new_size = new_t.size if new_t else old_size
        delta = new_size - old_size

        # Check if violated on any day
        violated_days = []
        for ba in solution.block_assignments:
            if ba.team_id != tid:
                continue
            block = next((b for b in blocks if b.block_id == ba.block_id), None)
            if block is None:
                continue
            day_total = sum(
                new_teams_by_id.get(ba2.team_id, old_teams_by_id.get(ba2.team_id)).size
                for ba2 in solution.block_assignments
                if ba2.day == ba.day and ba2.block_id == ba.block_id
                and ba2.team_id in new_teams_by_id
            )
            if day_total > block.capacity:
                violated_days.append(ba.day)

        change_rows.append({
            "Team": old_t.name,
            "Dept": old_t.department,
            "Old size": old_size,
            "New size": new_size,
            "Delta": f"{'+' if delta >= 0 else ''}{delta}",
            "Status": f"VIOLATED (days {violated_days})" if violated_days else "OK",
        })

    df_changes = pd.DataFrame(change_rows)

    def highlight_status(row):
        if "VIOLATED" in str(row["Status"]):
            return ["background-color: #f8d7da"] * len(row)
        elif row["Delta"] != "+0" and row["Delta"] != "0":
            return ["background-color: #fff3cd"] * len(row)
        return [""] * len(row)

    st.subheader("Team size changes")
    st.dataframe(
        df_changes.style.apply(highlight_status, axis=1),
        use_container_width=True,
        hide_index=True,
    )

# ── Run updater ───────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner("Running updater…"):
        updater = SolutionUpdater(
            blocks=blocks,
            old_teams=old_teams,
            new_teams=new_teams,
        )
        updated_solution = updater.update(solution)

    # Count changed assignments
    old_ba = {(ba.team_id, ba.day): ba.block_id for ba in solution.block_assignments}
    new_ba = {(ba.team_id, ba.day): ba.block_id for ba in updated_solution.block_assignments}
    changed = [k for k, v in new_ba.items() if old_ba.get(k) != v]
    n_changed_teams = len({tid for tid, _ in changed})

    if n_changed_teams == 0:
        st.success("No assignments changed — all teams still fit in their current blocks.")
    else:
        st.warning(f"{n_changed_teams} team(s) were relocated across {len(changed)} (team, day) pair(s).")

    col_before, col_after = st.columns(2)

    for day in [1, 2, 3, 4]:
        col_before, col_after = st.columns(2)
        with col_before:
            st.subheader(f"Before — Day {day}")
            render_grid(blocks, solution.get_day_view(day), old_teams_by_id)
        with col_after:
            st.subheader(f"After — Day {day}")
            render_grid(blocks, updated_solution.get_day_view(day), new_teams_by_id)

    if st.button("Save updated solution"):
        path = save_solution(updated_solution, SOLUTIONS_DIR)
        st.success(f"Saved to {path}")
