import json
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def load_office_map(csv_path: Path) -> Tuple[List[List[int]], int, int]:
    """
    Load office map from CSV.

    The CSV is expected to contain a grid of integers where:
    - each value is the seating capacity of a block
    - 0 means "no block" at that grid position
    """
    grid: List[List[int]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            row = [int(x) for x in stripped.split(",")]
            grid.append(row)

    if not grid:
        return [], 0, 0

    rows = len(grid)
    cols = len(grid[0])
    return grid, rows, cols


def load_configurations(config_path: Path) -> List[Dict]:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_block_capacity_map(
    grid: List[List[int]],
) -> Dict[str, int]:
    """
    Build mapping from block_id (e.g. r0_c1) to capacity.
    """
    block_capacity: Dict[str, int] = {}
    for r, row in enumerate(grid):
        for c, cap in enumerate(row):
            if cap <= 0:
                continue
            block_id = f"r{r}_c{c}"
            block_capacity[block_id] = cap
    return block_capacity


def teams_by_day_and_block(config: Dict) -> Dict[int, Dict[str, List[Dict]]]:
    """
    From a single configuration dict (as stored in configurations.json),
    build mapping: day -> block_id -> list of team dicts.
    """
    result: Dict[int, Dict[str, List[Dict]]] = {}

    for a in config.get("assignments", []):
        day1 = int(a["day1"])
        block1 = a["block1"]
        day2 = int(a["day2"])
        block2 = a["block2"]

        for day, block in ((day1, block1), (day2, block2)):
            day_map = result.setdefault(day, {})
            day_map.setdefault(block, []).append(a)

    return result


def render_day_grid(
    day: int,
    grid: List[List[int]],
    rows: int,
    cols: int,
    block_capacity: Dict[str, int],
    day_blocks: Dict[str, List[Dict]],
) -> None:
    """
    Render a seating grid for a single day using Streamlit columns.
    """
    st.subheader(f"Day {day}")

    for r in range(rows):
        cols_container = st.columns(cols)
        for c in range(cols):
            with cols_container[c]:
                capacity = grid[r][c]
                if capacity <= 0:
                    st.markdown(
                        "<div style='border:1px solid #ddd; padding:0.75rem; "
                        "background-color:#f5f5f5; text-align:center;'>"
                        "<span style='color:#999;'>No block</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    continue

                block_id = f"r{r}_c{c}"
                teams_here = day_blocks.get(block_id, [])

                used = sum(t["size"] for t in teams_here)
                cap = block_capacity.get(block_id, capacity)

                header = f"Block {block_id}"
                subtitle = f"{used}/{cap} seats used"

                box_color = "#e8f5e9" if used <= cap else "#ffebee"

                html_parts = [
                    f"<div style='border:1px solid #ccc; padding:0.75rem; "
                    f"border-radius:0.5rem; background-color:{box_color};'>",
                    f"<div style='font-weight:600; margin-bottom:0.25rem;'>{header}</div>",
                    f"<div style='font-size:0.85rem; color:#555; margin-bottom:0.5rem;'>{subtitle}</div>",
                ]

                if teams_here:
                    html_parts.append(
                        "<ul style='padding-left:1.1rem; margin:0; font-size:0.85rem;'>"
                    )
                    for t in teams_here:
                        team_label = f"{t['team_name']} ({t['team_id']})"
                        dept = t.get("department")
                        dept_str = f", {dept}" if dept else ""
                        html_parts.append(
                            f"<li>{team_label}: {t['size']} people{dept_str}</li>"
                        )
                    html_parts.append("</ul>")
                else:
                    html_parts.append(
                        "<div style='font-size:0.8rem; color:#777;'>No teams assigned</div>"
                    )

                html_parts.append("</div>")
                st.markdown("".join(html_parts), unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Seating Configurations Viewer", layout="wide")
    st.title("Seating Configurations Viewer")

    office_map_path = DATA_DIR / "office_map.csv"
    configs_path = OUTPUT_DIR / "configurations.json"

    if not office_map_path.exists():
        st.error(f"Office map CSV not found at `{office_map_path}`.")
        return
    if not configs_path.exists():
        st.error(f"Configurations file not found at `{configs_path}`.")
        return

    grid, rows, cols = load_office_map(office_map_path)
    if not grid:
        st.error("Office map CSV appears to be empty.")
        return

    configurations = load_configurations(configs_path)
    if not configurations:
        st.error("No configurations found in `configurations.json`.")
        return

    n_configs = len(configurations)

    st.sidebar.header("Configuration navigation")
    st.sidebar.write(f"Total configurations: **{n_configs}**")

    # Primary navigator: slider
    slider_value = st.sidebar.slider(
        "Browse configurations",
        min_value=1,
        max_value=n_configs,
        value=1,
        step=1,
        help="Use this slider to move between different seating configurations.",
    )

    # Direct input: configuration number
    direct_value = st.sidebar.number_input(
        "Go to configuration #",
        min_value=1,
        max_value=n_configs,
        value=slider_value,
        step=1,
        help="Type a configuration number to jump directly to it.",
    )

    # Final chosen configuration index (1-based for users, 0-based internally)
    selected_config_num = int(direct_value)
    selected_config_idx = selected_config_num - 1

    st.sidebar.markdown(
        f"Currently showing **configuration {selected_config_num} / {n_configs}**"
    )

    config = configurations[selected_config_idx]
    per_day = teams_by_day_and_block(config)

    all_days = sorted(per_day.keys())
    if not all_days:
        st.warning("Selected configuration has no day assignments.")
        return

    # Day selector
    day_labels = [f"Day {d}" for d in all_days]
    selected_day_label = st.selectbox(
        "Select day to view",
        options=day_labels,
        index=0,
        help="Choose which day of this configuration to visualize.",
    )
    selected_day = all_days[day_labels.index(selected_day_label)]

    block_capacity = build_block_capacity_map(grid)
    day_blocks = per_day.get(selected_day, {})

    # Summary at top
    teams = {a["team_id"] for a in config.get("assignments", [])}
    st.markdown(
        f"**Configuration {selected_config_num}** – "
        f"{len(teams)} teams, {len(all_days)} days in this configuration."
    )

    render_day_grid(
        day=selected_day,
        grid=grid,
        rows=rows,
        cols=cols,
        block_capacity=block_capacity,
        day_blocks=day_blocks,
    )


if __name__ == "__main__":
    main()

