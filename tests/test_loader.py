import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.loader import load_office_map, load_teams, get_department_map

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def test_load_office_map():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    assert len(blocks) == 6
    assert all(b.capacity > 0 for b in blocks)
    capacities = sorted(b.capacity for b in blocks)
    assert capacities == sorted([9, 12, 8, 12, 10, 8])
    ids = [b.block_id for b in blocks]
    assert ids == [f"B{i}" for i in range(6)]


def test_load_teams():
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    assert len(teams) == 22
    assert all(t.size > 0 for t in teams)
    assert all(t.department in {"D1", "D2", "D3", "D4"} for t in teams)


def test_get_department_map():
    teams = load_teams(os.path.join(DATA_DIR, "teams.json"))
    dept_map = get_department_map(teams)
    assert set(dept_map.keys()) == {"D1", "D2", "D3", "D4"}
    total = sum(len(v) for v in dept_map.values())
    assert total == 22
