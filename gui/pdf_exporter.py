from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen,
    QPdfWriter, QPageSize,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem

from gui.constants import CELL_W, CELL_H, CELL_GAP
from gui.widgets.block_item import BlockItem

_DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday"}

# 96 DPI keeps the scene scale factor close to 1:1 so BlockItem fonts
# (specified in points) render at approximately screen size inside each cell.
_PDF_DPI = 96


def export_pdf(
    path: str,
    solution,
    blocks: list,
    groups_by_id: dict,
    employees_by_group: dict,
    group_color_fn,
) -> None:
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(_PDF_DPI)

    page_rect = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
    margin = page_rect.width() * 0.06
    content = page_rect.adjusted(margin, margin, -margin, -margin)

    painter = QPainter()
    if not painter.begin(writer):
        raise RuntimeError("Failed to open PDF for writing")

    try:
        for day in range(1, 5):
            if day > 1:
                writer.newPage()
            _render_day_page(
                painter, solution, day,
                blocks, groups_by_id, employees_by_group, group_color_fn,
                content,
            )

        writer.newPage()
        _render_metadata_page(painter, solution, groups_by_id, content)

        writer.newPage()
        _render_dept_overlap_page(painter, writer, solution, groups_by_id, group_color_fn, content)
    finally:
        painter.end()


# ------------------------------------------------------------------ day pages

def _build_day_scene(solution, day, blocks, groups_by_id, group_color_fn, employees_by_group):
    scene = QGraphicsScene()
    grid_rows = max(b.row for b in blocks) + 1
    grid_cols = max(b.col for b in blocks) + 1
    block_map = {(b.row, b.col): b for b in blocks}
    day_view = solution.get_day_view(day)

    for row in range(grid_rows):
        for col in range(grid_cols):
            x = col * (CELL_W + CELL_GAP)
            y = row * (CELL_H + CELL_GAP)
            if (row, col) in block_map:
                block = block_map[(row, col)]
                item = BlockItem(
                    block,
                    groups_by_id,
                    group_color_fn or (lambda _: "#888888"),
                    employees_by_group=employees_by_group,
                    read_only=True,
                )
                item.setPos(x, y)
                item.set_groups(day_view.get(block.block_id, []))
                scene.addItem(item)
            else:
                placeholder = QGraphicsRectItem(0, 0, CELL_W, CELL_H)
                placeholder.setBrush(QBrush(QColor("#dde1e7")))
                placeholder.setPen(Qt.NoPen)
                placeholder.setPos(x, y)
                scene.addItem(placeholder)

    total_w = grid_cols * (CELL_W + CELL_GAP) - CELL_GAP
    total_h = grid_rows * (CELL_H + CELL_GAP) - CELL_GAP
    scene.setSceneRect(0, 0, total_w, total_h)
    return scene


def _render_day_page(painter, solution, day, blocks, groups_by_id, employees_by_group, group_color_fn, content):
    y = content.top()

    # Title
    title_font = QFont()
    title_font.setPointSize(16)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#222222"))
    title_h = painter.fontMetrics().height() * 1.8
    painter.drawText(
        QRectF(content.left(), y, content.width(), title_h),
        Qt.AlignLeft | Qt.AlignVCenter,
        f"Day {day} \u2014 {_DAY_NAMES.get(day, f'Day {day}')}",
    )
    y += title_h

    # Subtitle: group count
    sub_font = QFont()
    sub_font.setPointSize(9)
    painter.setFont(sub_font)
    painter.setPen(QColor("#555555"))
    n_groups = sum(1 for da in solution.day_assignments if day in da.days)
    sub_h = painter.fontMetrics().height() * 1.6
    painter.drawText(
        QRectF(content.left(), y, content.width(), sub_h),
        Qt.AlignLeft | Qt.AlignVCenter,
        f"{n_groups} group(s) in office",
    )
    y += sub_h + 6

    # Grid — scale scene to fill the remaining page area
    scene = _build_day_scene(solution, day, blocks, groups_by_id, group_color_fn, employees_by_group)
    src = scene.sceneRect()
    grid_area = QRectF(content.left(), y, content.width(), content.bottom() - y)

    if src.width() > 0 and src.height() > 0:
        scale = min(grid_area.width() / src.width(), grid_area.height() / src.height())
        target_w = src.width() * scale
        target_h = src.height() * scale
        target = QRectF(
            grid_area.left() + (grid_area.width() - target_w) / 2,
            grid_area.top(),
            target_w,
            target_h,
        )
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        scene.render(painter, target, src)
        painter.restore()


# ------------------------------------------------------------------ metadata page

def _render_metadata_page(painter, solution, groups_by_id, content):
    left = content.left()
    width = content.width()
    y = content.top()

    def _draw(text, size=11, bold=False, color="#222222", gap_before=0):
        nonlocal y
        font = QFont()
        font.setPointSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        h = painter.fontMetrics().height()
        y += gap_before
        painter.drawText(int(left), int(y + h), text)
        y += h * 1.6

    _draw("Solution Summary", size=18, bold=True)
    y += 10

    breakdown = solution.score_breakdown or {}
    cover = solution.cover_pair
    cover_str = f"Day {cover[0]} & Day {cover[1]}" if cover else "N/A"

    _draw(f"Solution ID:    {solution.solution_id}")
    _draw(f"Created:        {solution.created_at[:10]}")
    _draw(f"Score:          {solution.score:.3f}")
    _draw(f"Compactness:    {breakdown.get('compactness', 0):.3f}")
    _draw(f"Consistency:    {breakdown.get('consistency', 0):.3f}")
    _draw(f"Cover Days:     {cover_str}")
    y += 20

    # Department meeting days
    dept_common: dict[str, set] = {}
    for da in solution.day_assignments:
        group = groups_by_id.get(da.group_id)
        if group is None:
            continue
        for dept in group.departments:
            if dept not in dept_common:
                dept_common[dept] = set(da.days)
            else:
                dept_common[dept] &= set(da.days)

    if dept_common:
        _draw("Department Meeting Days", size=13, bold=True)
        y += 4
        dept_font = QFont()
        dept_font.setPointSize(9)
        painter.setFont(dept_font)
        dept_row_h = painter.fontMetrics().height() * 1.8
        dept_col_fracs = [0.45, 0.55]
        dept_col_x = [left + width * sum(dept_col_fracs[:i]) for i in range(2)]
        dept_col_w = [width * f for f in dept_col_fracs]

        # Header
        dept_hdr_font = QFont()
        dept_hdr_font.setPointSize(9)
        dept_hdr_font.setBold(True)
        painter.setFont(dept_hdr_font)
        painter.fillRect(QRectF(left, y, width, dept_row_h), QColor("#e0e0e0"))
        painter.setPen(QColor("#222222"))
        for i, hdr in enumerate(["Department", "Common Day(s)"]):
            painter.drawText(
                QRectF(dept_col_x[i] + 4, y, dept_col_w[i] - 8, dept_row_h),
                Qt.AlignLeft | Qt.AlignVCenter, hdr,
            )
        y += dept_row_h

        painter.setFont(dept_font)
        for didx, (dept, days) in enumerate(sorted(dept_common.items())):
            day_str = ", ".join(
                f"Day {d} ({_DAY_NAMES.get(d, str(d))})" for d in sorted(days)
            ) if days else "None"
            bg = QColor("#f5f5f5") if didx % 2 == 0 else QColor("#ffffff")
            painter.fillRect(QRectF(left, y, width, dept_row_h), bg)
            painter.setPen(QColor("#222222"))
            for i, val in enumerate([dept, day_str]):
                painter.drawText(
                    QRectF(dept_col_x[i] + 4, y, dept_col_w[i] - 8, dept_row_h),
                    Qt.AlignLeft | Qt.AlignVCenter, val,
                )
            painter.setPen(QPen(QColor("#dddddd"), 0.5))
            painter.drawLine(QPointF(left, y + dept_row_h), QPointF(left + width, y + dept_row_h))
            y += dept_row_h
        y += 20

    _draw("Group Schedule", size=13, bold=True)
    y += 6

    # Table — row height derived from font so it always fits the text
    headers = ["Group", "Dept(s)", "Size", "Day 1", "Day 2", "Single Block"]
    col_fracs = [0.19, 0.20, 0.06, 0.20, 0.20, 0.15]
    col_x = [left + width * sum(col_fracs[:i]) for i in range(len(headers))]
    col_w = [width * f for f in col_fracs]

    hdr_font = QFont()
    hdr_font.setPointSize(9)
    hdr_font.setBold(True)
    painter.setFont(hdr_font)
    hdr_row_h = painter.fontMetrics().height() * 1.8

    painter.fillRect(QRectF(left, y, width, hdr_row_h), QColor("#e0e0e0"))
    painter.setPen(QColor("#222222"))
    for i, col in enumerate(headers):
        painter.drawText(
            QRectF(col_x[i] + 4, y, col_w[i] - 8, hdr_row_h),
            Qt.AlignLeft | Qt.AlignVCenter,
            col,
        )
    y += hdr_row_h

    cell_font = QFont()
    cell_font.setPointSize(8)
    painter.setFont(cell_font)
    row_h = painter.fontMetrics().height() * 1.8

    for idx, da in enumerate(solution.day_assignments):
        group = groups_by_id.get(da.group_id)
        if group is None:
            continue
        d1, d2 = da.days
        bl1 = solution.get_group_blocks(da.group_id, d1)
        bl2 = solution.get_group_blocks(da.group_id, d2)

        def _fmt(bl):
            if not bl:
                return "?"
            if len(bl) == 1:
                return bl[0][0]
            return "+".join(f"{bid}({cnt})" for bid, cnt in bl)

        single = len(bl1) == 1 and len(bl2) == 1 and bl1[0][0] == bl2[0][0]
        values = [
            group.name,
            ", ".join(sorted(group.departments)),
            str(group.size),
            f"Day {d1} \u2192 {_fmt(bl1)}",
            f"Day {d2} \u2192 {_fmt(bl2)}",
            "Yes" if single else "No",
        ]

        bg = QColor("#f5f5f5") if idx % 2 == 0 else QColor("#ffffff")
        painter.fillRect(QRectF(left, y, width, row_h), bg)

        for i, val in enumerate(values):
            painter.setPen(
                QColor("#2d7d46") if (i == 5 and single)
                else QColor("#856404") if (i == 5)
                else QColor("#222222")
            )
            painter.drawText(
                QRectF(col_x[i] + 4, y, col_w[i] - 8, row_h),
                Qt.AlignLeft | Qt.AlignVCenter,
                val,
            )

        painter.setPen(QPen(QColor("#dddddd"), 0.5))
        painter.drawLine(QPointF(left, y + row_h), QPointF(left + width, y + row_h))
        y += row_h

        if y + row_h > content.bottom():
            break


# --------------------------------------------------------- dept overlap pages

def _render_dept_overlap_page(painter, writer, solution, groups_by_id, group_color_fn, content):
    from seating_optimizer.models import DAYS

    # Build dept_map and day lookup
    dept_map: dict = {}
    for group in groups_by_id.values():
        for dept in group.departments:
            dept_map.setdefault(dept, []).append(group.group_id)
    day_map = {da.group_id: set(da.days) for da in solution.day_assignments}

    left = content.left()
    width = content.width()
    y = content.top()

    # Measure row heights once up front
    title_font = QFont()
    title_font.setPointSize(16)
    title_font.setBold(True)
    painter.setFont(title_font)
    title_h = painter.fontMetrics().height() * 1.8

    dept_font = QFont()
    dept_font.setPointSize(10)
    dept_font.setBold(True)
    painter.setFont(dept_font)
    dept_label_h = painter.fontMetrics().height() * 1.8

    cell_font = QFont()
    cell_font.setPointSize(8)
    painter.setFont(cell_font)
    row_h = painter.fontMetrics().height() * 1.8

    col_name_w = width * 0.38
    day_col_w = (width - col_name_w) / len(DAYS)

    # Page title
    painter.setFont(title_font)
    painter.setPen(QColor("#222222"))
    painter.drawText(
        QRectF(left, y, width, title_h),
        Qt.AlignLeft | Qt.AlignVCenter,
        "Department Attendance",
    )
    y += title_h + 8

    for dept in sorted(dept_map.keys()):
        group_ids = [gid for gid in dept_map[dept] if gid in day_map]
        if not group_ids:
            continue

        # Space needed: dept label + header row + one row per group
        needed = dept_label_h + row_h * (1 + len(group_ids)) + 14
        if y + needed > content.bottom():
            writer.newPage()
            y = content.top()

        # Department label
        painter.setFont(dept_font)
        painter.setPen(QColor("#222222"))
        painter.drawText(
            QRectF(left, y, width, dept_label_h),
            Qt.AlignLeft | Qt.AlignVCenter,
            dept,
        )
        y += dept_label_h

        # Column headers
        hdr_font = QFont()
        hdr_font.setPointSize(8)
        hdr_font.setBold(True)
        painter.setFont(hdr_font)
        painter.fillRect(QRectF(left, y, width, row_h), QColor("#e0e0e0"))
        painter.setPen(QColor("#222222"))
        painter.drawText(
            QRectF(left + 4, y, col_name_w - 8, row_h),
            Qt.AlignLeft | Qt.AlignVCenter, "Group",
        )
        for di, day in enumerate(DAYS):
            cx = left + col_name_w + di * day_col_w
            painter.drawText(
                QRectF(cx, y, day_col_w, row_h),
                Qt.AlignCenter, f"Day {day}",
            )
        y += row_h

        # Group rows
        painter.setFont(cell_font)
        for ridx, gid in enumerate(group_ids):
            row_bg = QColor("#f5f5f5") if ridx % 2 == 0 else QColor("#ffffff")
            painter.fillRect(QRectF(left, y, width, row_h), row_bg)

            painter.setPen(QColor("#222222"))
            painter.drawText(
                QRectF(left + 4, y, col_name_w - 8, row_h),
                Qt.AlignLeft | Qt.AlignVCenter, gid,
            )

            days = day_map[gid]
            for di, day in enumerate(DAYS):
                cx = left + col_name_w + di * day_col_w
                pad = 3
                cell_rect = QRectF(cx + pad, y + pad, day_col_w - pad * 2, row_h - pad * 2)
                if day in days:
                    painter.fillRect(cell_rect, QColor(group_color_fn(gid)))
                else:
                    painter.fillRect(cell_rect, QColor("#EBEBEB"))

            painter.setPen(QPen(QColor("#dddddd"), 0.5))
            painter.drawLine(
                QPointF(left, y + row_h), QPointF(left + width, y + row_h)
            )
            y += row_h

        y += 14  # gap between departments
