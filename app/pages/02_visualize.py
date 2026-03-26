import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from seating_optimizer.loader import load_office_map, load_teams
from seating_optimizer.persistence import SOLUTIONS_DIR
from app.components.solution_selector import render_solution_selector
from app.components.grid_widget import render_grid, DEPT_COLORS
from pathlib import Path

st.set_page_config(page_title="Visualize — Seating Optimizer", layout="wide")
st.title("Visualize Solution")

# Load static data
data_dir = Path("data")
try:
    blocks = load_office_map(str(data_dir / "office_map.csv"))
    teams = load_teams(str(data_dir / "teams.json"))
    teams_by_id = {t.team_id: t for t in teams}
    blocks_by_id = {b.block_id: b for b in blocks}
except Exception as e:
    st.error(f"Failed to load data files: {e}")
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Solution")
    solution = render_solution_selector()
    if solution:
        day_choice = st.radio("Day", [1, 2, 3, 4], horizontal=True)

if solution is None:
    st.write("Select a solution in the sidebar.")
    st.stop()

# ── Metadata card ────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Score", f"{solution.score:.3f}")
col2.metric("Consistency", f"{solution.score_breakdown.get('consistency', 0):.2%}")
col3.metric("Dept proximity", f"{solution.score_breakdown.get('dept_proximity', 0):.2%}")
col4.metric("Cover days", str(solution.cover_pair))

st.caption(f"Solution ID: {solution.solution_id}  |  Created: {solution.created_at}")

st.divider()

# ── Dept legend ──────────────────────────────────────────────────────────────
depts = sorted({t.department for t in teams})
legend_html = " ".join(
    f"<span style='background:{DEPT_COLORS.get(d, '#888')};color:#fff;"
    f"border-radius:4px;padding:2px 8px;margin:2px;font-size:12px;'>{d}</span>"
    for d in depts
)
st.markdown(f"**Departments:** {legend_html}", unsafe_allow_html=True)

st.subheader(f"Office Map — Day {day_choice}")

# ── Grid ─────────────────────────────────────────────────────────────────────
day_view = solution.get_day_view(day_choice)
render_grid(blocks, day_view, teams_by_id)

st.divider()

# ── Day summary table ─────────────────────────────────────────────────────────
st.subheader("Block summary")
summary_rows = []
for block in sorted(blocks, key=lambda b: b.block_id):
    team_ids = day_view.get(block.block_id, [])
    used = sum(teams_by_id[tid].size for tid in team_ids if tid in teams_by_id)
    dept_list = sorted({teams_by_id[tid].department for tid in team_ids if tid in teams_by_id})
    summary_rows.append({
        "Block": block.block_id,
        "Position": f"({block.row},{block.col})",
        "Capacity": block.capacity,
        "Used": used,
        "Free": block.capacity - used,
        "Occupancy": f"{used/block.capacity:.0%}" if block.capacity else "0%",
        "Teams": ", ".join(
            teams_by_id[tid].name for tid in team_ids if tid in teams_by_id
        ) or "—",
        "Departments": ", ".join(dept_list) or "—",
    })
st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Team schedule table ───────────────────────────────────────────────────────
st.subheader("Full team schedule")
schedule_rows = []
for da in sorted(solution.day_assignments, key=lambda x: x.team_id):
    team = teams_by_id.get(da.team_id)
    d1, d2 = da.days
    b1 = solution.get_team_block(da.team_id, d1)
    b2 = solution.get_team_block(da.team_id, d2)
    schedule_rows.append({
        "Team": team.name if team else da.team_id,
        "Dept": team.department if team else "?",
        "Size": team.size if team else "?",
        f"Day {d1}": b1 or "-",
        f"Day {d2}": b2 or "-",
        "Same block": "Yes" if b1 == b2 else "No",
    })

df = pd.DataFrame(schedule_rows)

def highlight_same_block(row):
    color = "#d4edda" if row["Same block"] == "Yes" else "#fff3cd"
    return [f"background-color: {color}"] * len(row)

st.dataframe(
    df.style.apply(highlight_same_block, axis=1),
    use_container_width=True,
    hide_index=True,
)
