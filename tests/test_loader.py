import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seating_optimizer.loader import (
    load_office_map, load_employees, get_groups, get_department_map,
    get_employees_by_group,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
EMPLOYEES_CSV = os.path.join(DATA_DIR, "Employees list for seating with fake department.csv")


def test_load_office_map():
    blocks = load_office_map(os.path.join(DATA_DIR, "office_map.csv"))
    assert len(blocks) == 6
    assert all(b.capacity > 0 for b in blocks)
    ids = [b.block_id for b in blocks]
    assert ids == [f"B{i}" for i in range(6)]


def test_load_employees():
    employees = load_employees(EMPLOYEES_CSV)
    assert len(employees) == 122
    assert all(e.name for e in employees)
    assert all(e.group_id for e in employees)
    assert all(e.department for e in employees)
    # All employee_ids are unique
    ids = [e.employee_id for e in employees]
    assert len(ids) == len(set(ids))


def test_get_groups():
    employees = load_employees(EMPLOYEES_CSV)
    groups = get_groups(employees)
    group_ids = {g.group_id for g in groups}
    assert "AI" in group_ids
    assert "Data" in group_ids
    assert "Marketing" in group_ids
    # Sizes should be positive
    assert all(g.size > 0 for g in groups)
    # Departments frozenset should be non-empty
    assert all(len(g.departments) > 0 for g in groups)
    # Total employees across groups = 122
    assert sum(g.size for g in groups) == 122


def test_get_department_map():
    employees = load_employees(EMPLOYEES_CSV)
    groups = get_groups(employees)
    dept_map = get_department_map(groups)
    assert "R&D" in dept_map
    assert "N&R&D" in dept_map
    assert "N&R&D2" in dept_map
    # AI is in R&D
    assert "AI" in dept_map["R&D"]


def test_get_employees_by_group():
    employees = load_employees(EMPLOYEES_CSV)
    by_group = get_employees_by_group(employees)
    assert "AI" in by_group
    assert len(by_group["AI"]) == 10
    assert all(e.group_id == "AI" for e in by_group["AI"])
