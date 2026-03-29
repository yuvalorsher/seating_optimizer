from __future__ import annotations
import csv
import re
from pathlib import Path

from .models import Block, Employee, Group


def load_office_map(path: str) -> list:
    """
    Parse a CSV where non-zero values are seating block capacities.
    Returns list[Block] in row-major order, IDs B0, B1, …
    """
    blocks = []
    block_idx = 0
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row_idx, row in enumerate(reader):
            for col_idx, cell in enumerate(row):
                capacity = int(cell.strip())
                if capacity > 0:
                    blocks.append(Block(
                        block_id=f"B{block_idx}",
                        row=row_idx,
                        col=col_idx,
                        capacity=capacity,
                    ))
                    block_idx += 1
    return blocks


def _slugify(name: str) -> str:
    """Convert a name to a safe identifier (lowercase, underscores)."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def load_employees(path: str) -> list:
    """
    Parse an employee CSV file.
    Required columns: Display name, Group, Department.
    Returns list[Employee].
    """
    employees = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            name = row["Display name"].strip()
            group = row["Group"].strip()
            department = row["Department"].strip()
            if not name:
                continue
            employees.append(Employee(
                employee_id=f"e{i}_{_slugify(name)}",
                name=name,
                group_id=group,   # keep original group name as ID
                department=department,
            ))
    return employees


def get_groups(employees: list) -> list:
    """
    Aggregate employees by group → list[Group].
    """
    group_data: dict = {}  # group_id -> {"size": int, "depts": set}
    for emp in employees:
        gid = emp.group_id
        if gid not in group_data:
            group_data[gid] = {"size": 0, "depts": set()}
        group_data[gid]["size"] += 1
        group_data[gid]["depts"].add(emp.department)

    return [
        Group(
            group_id=gid,
            name=gid,
            size=data["size"],
            departments=frozenset(data["depts"]),
        )
        for gid, data in group_data.items()
    ]


def get_department_map(groups: list) -> dict:
    """Return {dept: [group_id, ...]} for groups with members in each dept."""
    dept_map: dict = {}
    for group in groups:
        for dept in group.departments:
            dept_map.setdefault(dept, []).append(group.group_id)
    return dept_map


def get_employees_by_group(employees: list) -> dict:
    """Return {group_id: [Employee, ...]}."""
    result: dict = {}
    for emp in employees:
        result.setdefault(emp.group_id, []).append(emp)
    return result


def load_cold_seats(path: str) -> dict:
    """
    Parse a cold-seats CSV with columns 'Group' and 'Block'.
    Returns {group_id: block_id} for groups that must sit in a specific block.
    """
    cold_seats: dict = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            group = row["Group"].strip()
            block = row["Block"].strip()
            if group and block:
                cold_seats[group] = block
    return cold_seats
