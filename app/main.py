import streamlit as st

st.set_page_config(
    page_title="Seating Optimizer",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Seating Optimizer")
st.markdown(
    """
Welcome to the **Seating Optimizer** — a tool to schedule teams across office seating blocks
while satisfying occupancy constraints and optimizing departmental proximity.

### Navigate using the sidebar:

| Page | What it does |
|------|-------------|
| **01 Solve** | Run the solver to find N seating solutions |
| **02 Visualize** | Inspect a saved solution day-by-day on the office map |
| **03 Update** | Re-optimize an existing solution after team sizes change |

---

### Constraints enforced:
1. All members of a team sit in the same block on the same day.
2. Each team comes in exactly **2 days** out of 4.
3. There exist two "cover days" whose union equals the set of all teams.
4. No block is overloaded beyond its capacity.

### Soft preferences optimized:
- A team occupies the **same block on both its days** (weight 60%).
- Teams in the **same department sit close together** per day (weight 40%).
"""
)
