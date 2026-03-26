from __future__ import annotations
from pathlib import Path
from typing import Optional

import streamlit as st

from seating_optimizer.persistence import list_solutions, load_solution, SOLUTIONS_DIR
from seating_optimizer.models import Solution


@st.cache_data(show_spinner=False)
def _load_cached(path_str: str) -> Solution:
    return load_solution(path_str)


def render_solution_selector(label: str = "Select solution") -> Optional[Solution]:
    """
    Render a selectbox listing all saved solution files.
    Returns the loaded Solution object, or None if nothing is selected.
    """
    paths = list_solutions(SOLUTIONS_DIR)
    if not paths:
        st.info("No saved solutions found. Run the solver first.")
        return None

    options = {
        p.name.replace("solution_", "").replace(".json", "")
        + f" (score={_peek_score(p):.3f})": str(p)
        for p in paths
    }
    choice = st.selectbox(label, list(options.keys()))
    if choice is None:
        return None
    path_str = options[choice]
    return _load_cached(path_str)


def _peek_score(path: Path) -> float:
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        return float(data.get("score", 0.0))
    except Exception:
        return 0.0
