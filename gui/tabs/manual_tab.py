from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from itertools import combinations

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QColor, QBrush, QDrag, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QToolButton, QScrollArea, QSplitter,
    QDialog, QDialogButtonBox, QSpinBox, QFormLayout,
    QComboBox, QFileDialog, QMessageBox, QMenu, QCheckBox,
    QSizePolicy,
)

from seating_optimizer.models import (
    Solution, GroupDayAssignment, GroupBlockAssignment,
)
from seating_optimizer.scorer import compute_total_score
from seating_optimizer import persistence

from gui.app_state import AppState
from gui.widgets.day_selector import DaySelectorWidget
from gui.widgets.manual_office_grid import ManualOfficeGrid
from gui.widgets.manual_group_panel import ManualGroupPanel


# ---------------------------------------------------------------------------
# ManualState — single source of truth for the manual editing session
# ---------------------------------------------------------------------------

class ManualState:
    """Mutable state for a manual seating session.

    day_assignments: {group_id: [day, ...]}   0–2 entries per group
    block_assignments: list[GroupBlockAssignment]
    """

    def __init__(self):
        self.day_assignments: dict[str, list[int]] = {}
        self.block_assignments: list[GroupBlockAssignment] = []

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pending_groups(self, day: int) -> list[str]:
        """Groups assigned to day but with no block assignment on that day."""
        seated = {ba.group_id for ba in self.block_assignments if ba.day == day}
        return [
            gid for gid, days in self.day_assignments.items()
            if day in days and gid not in seated
        ]

    def get_seated_count(self, group_id: str, day: int) -> int:
        return sum(
            ba.count for ba in self.block_assignments
            if ba.group_id == group_id and ba.day == day
        )

    def get_day_view(self, day: int) -> dict[str, list[tuple[str, int]]]:
        view: dict = {}
        for ba in self.block_assignments:
            if ba.day == day:
                view.setdefault(ba.block_id, []).append((ba.group_id, ba.count))
        return view

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def assign_day(self, group_id: str, day: int) -> None:
        days = self.day_assignments.setdefault(group_id, [])
        if day not in days and len(days) < 2:
            days.append(day)
            days.sort()

    def remove_day(self, group_id: str, day: int) -> None:
        if group_id in self.day_assignments:
            self.day_assignments[group_id] = [
                d for d in self.day_assignments[group_id] if d != day
            ]
            if not self.day_assignments[group_id]:
                del self.day_assignments[group_id]
        self.block_assignments = [
            ba for ba in self.block_assignments
            if not (ba.group_id == group_id and ba.day == day)
        ]

    def seat_group(self, group_id: str, day: int, block_id: str, count: int) -> None:
        """Upsert: if (group_id, day, block_id) exists update count, else append."""
        for ba in self.block_assignments:
            if ba.group_id == group_id and ba.day == day and ba.block_id == block_id:
                ba.count = count
                return
        self.block_assignments.append(
            GroupBlockAssignment(group_id=group_id, day=day, block_id=block_id, count=count)
        )

    def unseat_from_block(self, group_id: str, day: int, block_id: str) -> None:
        """Remove block assignment; group remains pending on that day."""
        self.block_assignments = [
            ba for ba in self.block_assignments
            if not (ba.group_id == group_id and ba.day == day and ba.block_id == block_id)
        ]

    def unseat_all_blocks(self, group_id: str, day: int) -> None:
        """Remove all block assignments for (group_id, day); group goes fully pending."""
        self.block_assignments = [
            ba for ba in self.block_assignments
            if not (ba.group_id == group_id and ba.day == day)
        ]

    def clear_group(self, group_id: str) -> None:
        self.day_assignments.pop(group_id, None)
        self.block_assignments = [
            ba for ba in self.block_assignments if ba.group_id != group_id
        ]

    # ------------------------------------------------------------------
    # Cover pair detection
    # ------------------------------------------------------------------

    def detect_cover_pair(self) -> tuple[int, int] | None:
        two_day = [gid for gid, days in self.day_assignments.items() if len(days) == 2]
        if not two_day:
            return None
        for d1, d2 in combinations([1, 2, 3, 4], 2):
            if all(d1 in self.day_assignments[g] or d2 in self.day_assignments[g]
                   for g in two_day):
                return (d1, d2)
        return None

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def compute_warnings(
        self,
        groups_by_id: dict,
        blocks_by_id: dict,
        dept_map: dict,
        cold_seats: dict | None,
    ) -> list[str]:
        warnings = []

        # Groups with != 2 days
        for gid, days in self.day_assignments.items():
            if len(days) != 2:
                g = groups_by_id.get(gid)
                name = g.name if g else gid
                warnings.append(f"{name}: assigned {len(days)} day(s) — need exactly 2")

        # Dept overlap
        for dept, gids in dept_map.items():
            present = [gid for gid in gids
                       if len(self.day_assignments.get(gid, [])) == 2]
            for g1, g2 in combinations(present, 2):
                d1 = set(self.day_assignments[g1])
                d2 = set(self.day_assignments[g2])
                if not d1 & d2:
                    warnings.append(
                        f"Dept '{dept}': {g1} and {g2} share no common day"
                    )

        # Seated count per (group, day)
        for gid, days in self.day_assignments.items():
            g = groups_by_id.get(gid)
            if g is None:
                continue
            for day in days:
                seated = self.get_seated_count(gid, day)
                if seated != g.size:
                    diff = seated - g.size
                    tag = f"+{diff}" if diff > 0 else str(diff)
                    warnings.append(
                        f"{g.name} Day {day}: seated {seated}/{g.size} ({tag})"
                    )

        # Block over capacity
        load: dict[tuple, int] = {}
        for ba in self.block_assignments:
            key = (ba.block_id, ba.day)
            load[key] = load.get(key, 0) + ba.count
        for (block_id, day), used in load.items():
            block = blocks_by_id.get(block_id)
            if block and used > block.capacity:
                warnings.append(
                    f"Block {block_id} Day {day}: over capacity ({used}/{block.capacity})"
                )

        # Cold seats violations
        for gid, required_block in (cold_seats or {}).items():
            for ba in self.block_assignments:
                if ba.group_id == gid and ba.block_id != required_block:
                    g = groups_by_id.get(gid)
                    name = g.name if g else gid
                    warnings.append(
                        f"Cold-seat: {name} in {ba.block_id}, required {required_block}"
                    )
                    break

        return warnings

    # ------------------------------------------------------------------
    # Conversion to/from Solution
    # ------------------------------------------------------------------

    def to_solution(self, groups_by_id: dict) -> Solution:
        two_day = {gid: tuple(days) for gid, days in self.day_assignments.items()
                   if len(days) == 2}
        if not two_day:
            raise ValueError("No groups have 2 days assigned — nothing to save.")
        day_assignments = [
            GroupDayAssignment(group_id=gid, days=days)
            for gid, days in two_day.items()
        ]
        cover = self.detect_cover_pair() or (0, 0)
        score, breakdown = compute_total_score(two_day, self.block_assignments)
        return Solution(
            solution_id=uuid.uuid4().hex[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=cover,
            day_assignments=day_assignments,
            block_assignments=list(self.block_assignments),
            score=score,
            score_breakdown=breakdown,
            metadata={"source": "manual"},
        )

    @classmethod
    def from_solution(cls, solution: Solution) -> "ManualState":
        state = cls()
        for da in solution.day_assignments:
            state.day_assignments[da.group_id] = list(da.days)
        state.block_assignments = [
            GroupBlockAssignment(
                group_id=ba.group_id, day=ba.day,
                block_id=ba.block_id, count=ba.count,
            )
            for ba in solution.block_assignments
        ]
        return state


# ---------------------------------------------------------------------------
# _WarningsBar — collapsible top bar showing constraint status
# ---------------------------------------------------------------------------

class _WarningsBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(2)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setArrowType(Qt.RightArrow)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle_btn.setText("✓ All constraints satisfied")
        self._toggle_btn.setCheckable(False)
        self._toggle_btn.clicked.connect(self._toggle)
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer.addWidget(self._toggle_btn)

        self._detail_scroll = QScrollArea()
        self._detail_scroll.setFixedHeight(100)
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setVisible(False)
        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(4, 2, 4, 2)
        self._detail_layout.setSpacing(2)
        self._detail_layout.addStretch()
        self._detail_scroll.setWidget(self._detail_widget)
        outer.addWidget(self._detail_scroll)

    def _toggle(self):
        self._expanded = not self._expanded
        self._toggle_btn.setArrowType(Qt.DownArrow if self._expanded else Qt.RightArrow)
        self._detail_scroll.setVisible(self._expanded)

    def update_warnings(self, warnings: list[str], cover_info: str | None = None) -> None:
        # Clear detail items (keep stretch at end)
        while self._detail_layout.count() > 1:
            item = self._detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if cover_info:
            lbl = QLabel(f"✓ {cover_info}")
            lbl.setStyleSheet("color: #27AE60; font-size: 11px;")
            self._detail_layout.insertWidget(0, lbl)

        for i, w in enumerate(warnings):
            lbl = QLabel(f"⚠ {w}")
            lbl.setStyleSheet("color: #c0392b; font-size: 11px;")
            lbl.setWordWrap(True)
            self._detail_layout.insertWidget(i + (1 if cover_info else 0), lbl)

        if not warnings:
            self._toggle_btn.setText("✓ All constraints satisfied")
            self.setStyleSheet("background: #d4edda;")
        else:
            self._toggle_btn.setText(f"⚠ {len(warnings)} warning(s) — click to expand")
            self.setStyleSheet("background: #fff3cd;")
            if not self._expanded:
                self._expanded = True
                self._toggle_btn.setArrowType(Qt.DownArrow)
                self._detail_scroll.setVisible(True)


# ---------------------------------------------------------------------------
# _CountDialog — ask how many employees to seat/move
# ---------------------------------------------------------------------------

class _CountDialog(QDialog):
    def __init__(self, title: str, label: str, min_val: int, max_val: int,
                 default: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._spin = QSpinBox()
        self._spin.setRange(min_val, max_val)
        self._spin.setValue(min(default, max_val))
        form.addRow(label, self._spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def count(self) -> int:
        return self._spin.value()


# ---------------------------------------------------------------------------
# _PendingPanel — shows pending groups for the current day; accepts drops
# ---------------------------------------------------------------------------

class _PendingPanel(QWidget):
    unseat_requested = Signal(str, str)      # group_id, from_block_id
    assign_day_requested = Signal(str)       # group_id  (from panel drag, day = current)
    remove_day_requested = Signal(str, int)  # group_id, day
    clear_group_requested = Signal(str)      # group_id

    def __init__(self, group_color_fn, parent=None):
        super().__init__(parent)
        self._group_color_fn = group_color_fn
        self._current_day = 1
        self.setAcceptDrops(True)
        self.setFixedHeight(120)
        self.setStyleSheet("background: #f8f9fa; border-top: 1px solid #dee2e6;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        self._label = QLabel("Pending — Day 1")
        self._label.setStyleSheet("font-weight: bold; font-size: 11px; color: #555;")
        outer.addWidget(self._label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(2, 2, 2, 2)
        self._chips_layout.setSpacing(6)
        self._chips_layout.addStretch()
        scroll.setWidget(self._chips_widget)
        outer.addWidget(scroll)

    def set_current_day(self, day: int) -> None:
        self._current_day = day

    def refresh(self, manual_state, current_day: int) -> None:
        self._current_day = current_day
        self._label.setText(f"Pending — Day {current_day}")

        # Remove old chips
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for gid in manual_state.get_pending_groups(current_day):
            chip = _PendingChip(
                gid,
                self._group_color_fn(gid),
                current_day,
                parent=self._chips_widget,
            )
            chip.remove_day_requested.connect(self.remove_day_requested)
            chip.clear_group_requested.connect(self.clear_group_requested)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-team-chip"):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-team-chip"):
            event.accept()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-team-chip"):
            event.ignore()
            return
        try:
            data = json.loads(
                bytes(event.mimeData().data("application/x-team-chip")).decode()
            )
            group_id = data.get("team_id")
            from_block_id = data.get("from_block_id")
            source = data.get("source", "block")
            event.accept()
            if from_block_id:  # came from a block → unseat
                self.unseat_requested.emit(group_id, from_block_id)
            elif source == "panel":  # came from group panel → assign to day
                self.assign_day_requested.emit(group_id)
        except Exception:
            event.ignore()


class _PendingChip(QFrame):
    """A colored draggable chip representing a pending group."""

    remove_day_requested = Signal(str, int)  # group_id, day
    clear_group_requested = Signal(str)

    def __init__(self, group_id: str, color_hex: str, day: int, parent=None):
        super().__init__(parent)
        self._group_id = group_id
        self._day = day
        self._drag_start: QPoint | None = None

        self.setFixedHeight(28)
        self.setMinimumWidth(60)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_right_click)

        bg = QColor(color_hex)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        lbl = QLabel(group_id)
        lbl.setStyleSheet(f"color: white; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl)

        r, g, b = bg.red(), bg.green(), bg.blue()
        self.setStyleSheet(
            f"QFrame {{ background: rgb({r},{g},{b}); border-radius: 4px; }}"
        )

    def _on_right_click(self, pos: QPoint) -> None:
        menu = QMenu(self)
        remove_action = menu.addAction(f"Remove from Day {self._day}")
        remove_action.triggered.connect(
            lambda: self.remove_day_requested.emit(self._group_id, self._day)
        )
        menu.addSeparator()
        clear_action = menu.addAction("Clear all group assignments")
        clear_action.triggered.connect(
            lambda: self.clear_group_requested.emit(self._group_id)
        )
        # Open above the click point so the menu doesn't go off-screen at the bottom
        global_pos = self.mapToGlobal(pos)
        menu.adjustSize()
        adjusted = global_pos - QPoint(0, menu.sizeHint().height())
        menu.exec(adjusted)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start is not None
            and (event.pos() - self._drag_start).manhattanLength() > 8
        ):
            mime = QMimeData()
            payload = json.dumps({
                "team_id": self._group_id,
                "from_block_id": None,
                "source": "pending",
            }).encode("utf-8")
            mime.setData("application/x-team-chip", payload)
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
            self._drag_start = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# ManualTab — main tab widget
# ---------------------------------------------------------------------------

class ManualTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._manual_state = ManualState()
        self._current_day = 1
        self._no_cold_seats = False
        self._settings_expanded = True

        self._build_ui()
        self._connect_signals()
        state.solution_list_changed.connect(self._refresh_solution_combo)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Left settings pane ---
        self._settings_pane = self._build_settings_pane()
        root.addWidget(self._settings_pane)

        # --- Center ---
        center_frame = QWidget()
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(6, 6, 6, 6)
        center_layout.setSpacing(4)

        # Warnings bar
        self._warnings_bar = _WarningsBar()
        center_layout.addWidget(self._warnings_bar)

        # Day selector
        day_row = QHBoxLayout()
        day_row.setSpacing(8)
        self._day_selector = DaySelectorWidget()
        day_row.addWidget(self._day_selector)
        day_row.addStretch()
        center_layout.addLayout(day_row)

        # Grid + pending splitter
        splitter = QSplitter(Qt.Vertical)
        self._grid_widget = ManualOfficeGrid()
        splitter.addWidget(self._grid_widget)
        self._pending_panel = _PendingPanel(self._state.group_color)
        splitter.addWidget(self._pending_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([500, 120])
        center_layout.addWidget(splitter, stretch=1)

        root.addWidget(center_frame, stretch=1)

        # --- Right group panel ---
        self._group_panel = ManualGroupPanel(self._state.group_color)
        root.addWidget(self._group_panel)

    def _build_settings_pane(self) -> QFrame:
        pane = QFrame()
        pane.setFrameShape(QFrame.StyledPanel)
        pane.setFixedWidth(270)

        outer = QVBoxLayout(pane)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # Toggle button
        toggle_row = QHBoxLayout()
        self._settings_toggle = QToolButton()
        self._settings_toggle.setArrowType(Qt.LeftArrow)
        self._settings_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._settings_toggle.setText("Settings")
        self._settings_toggle.clicked.connect(self._toggle_settings)
        toggle_row.addWidget(self._settings_toggle)
        toggle_row.addStretch()
        outer.addLayout(toggle_row)

        # Inner collapsible content
        self._settings_inner = QWidget()
        inner = QVBoxLayout(self._settings_inner)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(6)

        def _path_row(label_text: str) -> tuple[QLabel, QPushButton]:
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel("—")
            lbl.setStyleSheet("font-size: 10px; color: #555;")
            lbl.setWordWrap(True)
            btn = QPushButton("Browse")
            btn.setFixedWidth(60)
            btn.setFixedHeight(22)
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            row_layout.addWidget(QLabel(label_text))
            sub = QHBoxLayout()
            sub.addWidget(lbl, stretch=1)
            sub.addWidget(btn)
            row_layout.addLayout(sub)
            inner.addWidget(row_widget)
            return lbl, btn

        self._map_lbl, self._map_btn = _path_row("Office Map:")
        self._emp_lbl, self._emp_btn = _path_row("Employees CSV:")

        # Cold seats row
        cs_widget = QWidget()
        cs_layout = QVBoxLayout(cs_widget)
        cs_layout.setContentsMargins(0, 0, 0, 0)
        cs_layout.setSpacing(2)
        cs_layout.addWidget(QLabel("Cold Seats CSV:"))
        cs_sub = QHBoxLayout()
        self._cs_lbl = QLabel("—")
        self._cs_lbl.setStyleSheet("font-size: 10px; color: #555;")
        self._cs_lbl.setWordWrap(True)
        self._cs_btn = QPushButton("Browse")
        self._cs_btn.setFixedWidth(60)
        self._cs_btn.setFixedHeight(22)
        cs_sub.addWidget(self._cs_lbl, stretch=1)
        cs_sub.addWidget(self._cs_btn)
        cs_layout.addLayout(cs_sub)
        self._no_cs_chk = QCheckBox("No cold seats")
        cs_layout.addWidget(self._no_cs_chk)
        inner.addWidget(cs_widget)

        # Base solution combo
        inner.addWidget(QLabel("Base Solution:"))
        self._solution_combo = QComboBox()
        self._solution_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        inner.addWidget(self._solution_combo)

        # Load button
        self._load_btn = QPushButton("Load")
        self._load_btn.setStyleSheet(
            "QPushButton { background: #4A90D9; color: white; font-weight: bold; "
            "padding: 5px; border-radius: 4px; }"
            "QPushButton:hover { background: #2c6fad; }"
        )
        inner.addWidget(self._load_btn)

        inner.addStretch()

        # Save button
        self._save_btn = QPushButton("Save Solution")
        self._save_btn.setStyleSheet(
            "QPushButton { background: #27AE60; color: white; font-weight: bold; "
            "padding: 5px; border-radius: 4px; }"
            "QPushButton:hover { background: #1e8449; }"
        )
        inner.addWidget(self._save_btn)

        outer.addWidget(self._settings_inner)

        self._update_path_labels()
        self._refresh_solution_combo()
        return pane

    def _update_path_labels(self):
        import os
        def _short(p: str) -> str:
            return os.path.basename(p) if p else "—"
        self._map_lbl.setText(_short(self._state.office_map_path))
        self._emp_lbl.setText(_short(self._state.employees_path))
        self._cs_lbl.setText(_short(self._state.cold_seats_path))

    def _toggle_settings(self):
        self._settings_expanded = not self._settings_expanded
        self._settings_inner.setVisible(self._settings_expanded)
        self._settings_pane.setFixedWidth(270 if self._settings_expanded else 32)
        self._settings_toggle.setArrowType(
            Qt.LeftArrow if self._settings_expanded else Qt.RightArrow
        )

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self._day_selector.day_changed.connect(self._on_day_changed)
        self._grid_widget.drop_requested.connect(self._on_drop_requested)
        self._grid_widget.chip_right_clicked.connect(self._on_chip_right_clicked)
        self._pending_panel.unseat_requested.connect(self._on_unseat_from_block)
        self._pending_panel.assign_day_requested.connect(
            lambda gid: self._on_assign_day(gid, self._current_day)
        )
        self._pending_panel.remove_day_requested.connect(self._on_remove_day)
        self._pending_panel.clear_group_requested.connect(self._on_clear_group)
        self._group_panel.day_assignment_requested.connect(self._on_assign_day)
        self._group_panel.clear_group_requested.connect(self._on_clear_group)
        self._map_btn.clicked.connect(self._browse_map)
        self._emp_btn.clicked.connect(self._browse_employees)
        self._cs_btn.clicked.connect(self._browse_cold_seats)
        self._no_cs_chk.toggled.connect(self._on_no_cold_seats_toggled)
        self._load_btn.clicked.connect(self._on_load)
        self._save_btn.clicked.connect(self._on_save)

    # ------------------------------------------------------------------
    # Core refresh
    # ------------------------------------------------------------------

    def _refresh_all(self):
        self._reload_grid()
        self._pending_panel.refresh(self._manual_state, self._current_day)
        self._group_panel.refresh(self._manual_state, self._state.groups_by_id, self._current_day)
        self._reload_warnings()

    def _reload_grid(self):
        if not self._state.blocks:
            return
        day_assignments = [
            GroupDayAssignment(group_id=gid, days=tuple(days))
            for gid, days in self._manual_state.day_assignments.items()
            if days
        ]
        stub = Solution(
            solution_id="__manual__",
            created_at="",
            cover_pair=(0, 0),
            day_assignments=day_assignments,
            block_assignments=list(self._manual_state.block_assignments),
            score=0.0,
            score_breakdown={},
            metadata={},
        )
        self._grid_widget.load(
            stub,
            self._current_day,
            self._state.blocks,
            self._state.groups_by_id,
            group_color_fn=self._state.group_color,
            employees_by_group=self._state.employees_by_group,
        )

    def _reload_warnings(self):
        cold_seats = None if self._no_cold_seats else self._state.cold_seats
        warnings = self._manual_state.compute_warnings(
            self._state.groups_by_id,
            self._state.blocks_by_id,
            self._state.dept_map,
            cold_seats,
        )
        cover = self._manual_state.detect_cover_pair()
        cover_info = f"Cover pair: Day {cover[0]} & Day {cover[1]}" if cover else None
        self._warnings_bar.update_warnings(warnings, cover_info)

    # ------------------------------------------------------------------
    # Day change
    # ------------------------------------------------------------------

    def _on_day_changed(self, day: int):
        self._current_day = day
        self._refresh_all()

    # ------------------------------------------------------------------
    # Drop handler (block targets)
    # ------------------------------------------------------------------

    def _on_drop_requested(self, group_id: str, from_source, to_block_id: str):
        group = self._state.groups_by_id.get(group_id)
        if group is None:
            return

        if not from_source or from_source in ("panel", "pending"):
            # External source → seat dialog
            already_seated = self._manual_state.get_seated_count(group_id, self._current_day)
            remaining = group.size - already_seated
            if remaining <= 0:
                # Allow over-seating (user chose to exceed group size)
                remaining = group.size

            dlg = _CountDialog(
                title=f"Seat {group_id} in {to_block_id}",
                label=f"Employees to seat (group size: {group.size}, already seated: {already_seated}):",
                min_val=1,
                max_val=max(group.size * 2, already_seated + group.size),
                default=max(1, remaining),
                parent=self,
            )
            if dlg.exec() != QDialog.Accepted:
                return
            count = dlg.count()
            # Ensure day is assigned
            if self._current_day not in self._manual_state.day_assignments.get(group_id, []):
                self._manual_state.assign_day(group_id, self._current_day)
            self._manual_state.seat_group(group_id, self._current_day, to_block_id, count)

        else:
            # Block-to-block move
            from_block_id = from_source
            existing_count = next(
                (ba.count for ba in self._manual_state.block_assignments
                 if ba.group_id == group_id and ba.day == self._current_day
                 and ba.block_id == from_block_id),
                0,
            )
            if existing_count == 0:
                return
            dlg = _CountDialog(
                title=f"Move {group_id} to {to_block_id}",
                label=f"Employees to move from {from_block_id}:",
                min_val=1,
                max_val=existing_count,
                default=existing_count,
                parent=self,
            )
            if dlg.exec() != QDialog.Accepted:
                return
            count = dlg.count()
            self._manual_state.unseat_from_block(group_id, self._current_day, from_block_id)
            if count < existing_count:
                self._manual_state.seat_group(
                    group_id, self._current_day, from_block_id, existing_count - count
                )
            self._manual_state.seat_group(group_id, self._current_day, to_block_id, count)

        self._refresh_all()

    # ------------------------------------------------------------------
    # Block chip right-click menu
    # ------------------------------------------------------------------

    def _on_chip_right_clicked(self, group_id: str, block_id: str):
        days = self._manual_state.day_assignments.get(group_id, [])

        menu = QMenu(self)

        add_menu = menu.addMenu("Add to day")
        for day in range(1, 5):
            action = add_menu.addAction(f"Day {day}")
            action.setEnabled(day not in days and len(days) < 2)
            action.triggered.connect(
                lambda checked=False, d=day, gid=group_id: self._on_assign_day(gid, d)
            )

        menu.addSeparator()

        # Move to pending
        blocks_on_day = [
            ba for ba in self._manual_state.block_assignments
            if ba.group_id == group_id and ba.day == self._current_day
        ]
        if len(blocks_on_day) > 1:
            move_menu = menu.addMenu("Move to pending")
            move_this = move_menu.addAction(f"From {block_id} only")
            move_this.triggered.connect(
                lambda checked=False, gid=group_id, bid=block_id:
                self._on_unseat_from_block(gid, bid)
            )
            move_all = move_menu.addAction("All blocks this day")
            move_all.triggered.connect(
                lambda checked=False, gid=group_id:
                self._on_unseat_all(gid, self._current_day)
            )
        else:
            move_action = menu.addAction("Move to pending")
            move_action.triggered.connect(
                lambda checked=False, gid=group_id, bid=block_id:
                self._on_unseat_from_block(gid, bid)
            )

        # Remove from this day — submenu when seated in multiple blocks
        if len(blocks_on_day) > 1:
            remove_menu = menu.addMenu("Remove from this day")
            remove_block = remove_menu.addAction(f"From {block_id} only")
            remove_block.triggered.connect(
                lambda checked=False, gid=group_id, bid=block_id:
                self._on_unseat_from_block(gid, bid)
            )
            remove_all_day = remove_menu.addAction("All blocks this day")
            remove_all_day.triggered.connect(
                lambda checked=False, gid=group_id:
                self._on_remove_day(gid, self._current_day)
            )
        else:
            remove_action = menu.addAction("Remove from this day")
            remove_action.triggered.connect(
                lambda checked=False, gid=group_id:
                self._on_remove_day(gid, self._current_day)
            )

        menu.addSeparator()
        clear_action = menu.addAction("Clear all group assignments")
        clear_action.triggered.connect(
            lambda checked=False, gid=group_id: self._on_clear_group(gid)
        )

        menu.exec(QCursor.pos())

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _on_assign_day(self, group_id: str, day: int):
        self._manual_state.assign_day(group_id, day)
        self._refresh_all()

    def _on_remove_day(self, group_id: str, day: int):
        self._manual_state.remove_day(group_id, day)
        self._refresh_all()

    def _on_unseat_from_block(self, group_id: str, block_id: str):
        self._manual_state.unseat_from_block(group_id, self._current_day, block_id)
        self._refresh_all()

    def _on_unseat_all(self, group_id: str, day: int):
        self._manual_state.unseat_all_blocks(group_id, day)
        self._refresh_all()

    def _on_clear_group(self, group_id: str):
        self._manual_state.clear_group(group_id)
        self._refresh_all()

    # ------------------------------------------------------------------
    # Settings pane actions
    # ------------------------------------------------------------------

    def _browse_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Office Map CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_office_map_path(path)
            self._update_path_labels()
            self._reload_data_and_refresh()

    def _browse_employees(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Employees CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_employees_path(path)
            self._update_path_labels()
            self._reload_data_and_refresh()

    def _browse_cold_seats(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Cold Seats CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._state.set_cold_seats_path(path)
            self._update_path_labels()
            self._reload_data_and_refresh()

    def _reload_data_and_refresh(self):
        """Reload data files and refresh the UI without resetting ManualState."""
        try:
            self._state.load_data_files()
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load data files:\n{exc}")
            return
        self._refresh_all()

    def _on_no_cold_seats_toggled(self, checked: bool):
        self._no_cold_seats = checked
        self._reload_warnings()

    def _on_load(self):
        # Reload data files if needed
        try:
            self._state.load_data_files()
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load data files:\n{exc}")
            return

        # Build new ManualState
        idx = self._solution_combo.currentIndex()
        if idx > 0:  # 0 = "New / Empty"
            solution = self._solution_combo.itemData(idx)
            if solution is not None:
                self._manual_state = ManualState.from_solution(solution)
            else:
                self._manual_state = ManualState()
        else:
            self._manual_state = ManualState()

        self._refresh_all()

    def _on_save(self):
        try:
            sol = self._manual_state.to_solution(self._state.groups_by_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Save", str(exc))
            return
        try:
            persistence.save_solution(sol, self._state.solutions_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")
            return
        self._state.solutions.append(sol)
        self._state.solutions.sort(key=lambda s: s.score, reverse=True)
        self._state.solution_list_changed.emit()
        QMessageBox.information(self, "Saved", f"Solution {sol.solution_id} saved.")

    def _refresh_solution_combo(self):
        self._solution_combo.blockSignals(True)
        self._solution_combo.clear()
        self._solution_combo.addItem("New / Empty", userData=None)
        for sol in self._state.solutions:
            label = f"Score {sol.score:.3f} | {sol.solution_id}"
            self._solution_combo.addItem(label, userData=sol)
        self._solution_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # grid property (for main_window.py compatibility)
    # ------------------------------------------------------------------

    @property
    def _grid(self):
        return self._grid_widget


# Keep stub name alias for any lingering imports
class _DummyGrid:
    def _fit_in_view(self):
        pass
