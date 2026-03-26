from __future__ import annotations
import streamlit as st

DEPT_COLORS: dict = {
    "D1": "#4A90D9",
    "D2": "#27AE60",
    "D3": "#F5A623",
    "D4": "#D0021B",
}
DEFAULT_COLOR = "#888888"


def render_grid(
    blocks: list,
    block_assignments_for_day: dict,  # {block_id: [team_id, ...]}
    teams_by_id: dict,
    grid_rows: int = 5,
    grid_cols: int = 5,
) -> None:
    """
    Render a grid_rows × grid_cols office map.
    Each seating block cell shows capacity bar + team chips.
    Empty cells are muted gray boxes.
    """
    # Build lookup: (row, col) -> Block
    block_at: dict = {(b.row, b.col): b for b in blocks}

    for row in range(grid_rows):
        cols = st.columns(grid_cols)
        for col in range(grid_cols):
            with cols[col]:
                block = block_at.get((row, col))
                if block is None:
                    st.markdown(
                        "<div style='background:#e8e8e8;border-radius:6px;"
                        "min-height:90px;margin:2px;'></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    teams_here = block_assignments_for_day.get(block.block_id, [])
                    used = sum(teams_by_id[tid].size for tid in teams_here if tid in teams_by_id)
                    html = _build_cell_html(block, teams_here, used, teams_by_id)
                    st.markdown(html, unsafe_allow_html=True)


def _build_cell_html(block, team_ids: list, used: int, teams_by_id: dict) -> str:
    pct = min(100, int(used / block.capacity * 100)) if block.capacity > 0 else 0
    bar_color = "#2ecc71" if pct < 70 else ("#f39c12" if pct < 95 else "#e74c3c")

    chips = ""
    for tid in team_ids:
        team = teams_by_id.get(tid)
        if team is None:
            continue
        color = DEPT_COLORS.get(team.department, DEFAULT_COLOR)
        chips += (
            f"<span style='display:inline-block;background:{color};color:#fff;"
            f"border-radius:4px;padding:1px 5px;margin:1px;font-size:11px;'>"
            f"{team.name} ({team.size})</span>"
        )

    bar_html = _build_capacity_bar_html(used, block.capacity, bar_color)

    return (
        f"<div style='background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;"
        f"padding:6px;min-height:90px;margin:2px;'>"
        f"<div style='font-weight:bold;font-size:12px;margin-bottom:3px;'>"
        f"{block.block_id} <span style='color:#666;font-weight:normal;'>"
        f"cap={block.capacity}</span></div>"
        f"{bar_html}"
        f"<div style='margin-top:4px;'>{chips}</div>"
        f"</div>"
    )


def _build_capacity_bar_html(used: int, capacity: int, color: str) -> str:
    pct = min(100, int(used / capacity * 100)) if capacity > 0 else 0
    return (
        f"<div style='background:#e0e0e0;border-radius:3px;height:8px;width:100%;'>"
        f"<div style='background:{color};border-radius:3px;height:8px;"
        f"width:{pct}%;'></div></div>"
        f"<div style='font-size:10px;color:#555;'>{used}/{capacity} seats</div>"
    )
