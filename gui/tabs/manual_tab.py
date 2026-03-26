from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal, QMimeData, QTimer
from PySide6.QtGui import QColor, QDrag, QPixmap, QIcon, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QListWidget, QListWidgetItem, QComboBox, QMessageBox, QFileDialog, QMenu,
)

from seating_optimizer.models import (
    Solution, TeamDayAssignment, TeamBlockAssignment, DAYS,
)
from seating_optimizer import persistence
from seating_optimizer.constraints import ALL_COVER_PAIRS
from seating_optimizer.scorer import compute_total_score
from seating_optimizer.loader import get_department_map

from gui.app_state import AppState
from gui.widgets.day_selector import DaySelectorWidget
from gui.widgets.office_grid import OfficeGridView


# ---------------------------------------------------------------------------
# Team list widget (left panel)
# ---------------------------------------------------------------------------

class _TeamListWidget(QListWidget):
    """Draggable team list. Also accepts drops from blocks to remove assignments."""

    team_returned = Signal(str, str)  # team_id, from_block_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setWordWrap(True)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        team_id = item.data(Qt.UserRole)
        if not team_id:
            return
        mime = QMimeData()
        payload = json.dumps({
            "team_id": team_id,
            "from_block_id": "__list__",
        }).encode("utf-8")
        mime.setData("application/x-team-chip", payload)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction | Qt.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-team-chip"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-team-chip"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-team-chip"):
            try:
                data = json.loads(
                    bytes(event.mimeData().data("application/x-team-chip")).decode()
                )
                from_block_id = data.get("from_block_id", "__list__")
                team_id = data.get("team_id", "")
                if from_block_id and from_block_id != "__list__":
                    self.team_returned.emit(team_id, from_block_id)
                    event.acceptProposedAction()
                else:
                    event.ignore()
            except Exception:
                event.ignore()
        else:
            event.ignore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dot_icon(color_hex: str) -> QIcon:
    """Small filled circle icon for context-menu colour coding."""
    pix = QPixmap(14, 14)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color_hex)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Grid view subclass that handles drops from the team list
# ---------------------------------------------------------------------------

class _ManualGridView(OfficeGridView):
    """OfficeGridView extended for manual assignment.

    • Accepts drops from the team list (from_block_id == "__list__").
    • Always accepts over-capacity drops (shows red, warns via constraint panel).
    • Right-click on a team chip → "Assign to Day N in this block" context menu.
    • Highlights all blocks green/red for the currently selected team.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._allow_oversize = True
        self._highlighted_team_id: str | None = None

    # ------------------------------------------------------------------ highlights

    def set_team_highlight(self, team_id: str | None):
        self._highlighted_team_id = team_id
        self._apply_team_highlights()

    def _apply_team_highlights(self):
        if self._highlighted_team_id is None:
            self.clear_highlights()
        else:
            self.highlight_for_team(self._highlighted_team_id, self._day)

    # ------------------------------------------------------------------ scene

    def _rebuild_scene(self):
        super()._rebuild_scene()
        # Re-apply selection highlights on the freshly-built items
        self._apply_team_highlights()
        # Wire right-click signal for every block
        for item in self._block_items.values():
            item.team_right_clicked.connect(self._on_team_right_clicked)

    # ------------------------------------------------------------------ drop handling

    def _on_team_dropped(self, team_id: str, from_block_id: str, to_block_id: str):
        if self._solution is None:
            return

        if from_block_id == "__list__":
            # Guard: team may not be placed on a 3rd distinct day
            existing_days = list(set(
                ba.day for ba in self._solution.block_assignments
                if ba.team_id == team_id
            ))
            if len(existing_days) >= 2 and self._day not in existing_days:
                self._rebuild_scene()
                return

            # Update or add block assignment for this day
            existing = next(
                (ba for ba in self._solution.block_assignments
                 if ba.team_id == team_id and ba.day == self._day),
                None,
            )
            if existing:
                if existing.block_id == to_block_id:
                    return
                existing.block_id = to_block_id
            else:
                self._solution.block_assignments.append(
                    TeamBlockAssignment(
                        team_id=team_id, day=self._day, block_id=to_block_id
                    )
                )
        else:
            # Standard within-grid move
            for ba in self._solution.block_assignments:
                if ba.team_id == team_id and ba.day == self._day:
                    ba.block_id = to_block_id
                    break

        self._recompute_score()
        self._rebuild_scene()
        self.team_moved.emit(team_id, from_block_id, to_block_id, self._day)

    def _recompute_score(self):
        if self._solution is None:
            return
        da_dict = {da.team_id: da.days for da in self._solution.day_assignments}
        ba_dict = {(ba.team_id, ba.day): ba.block_id for ba in self._solution.block_assignments}
        if da_dict and ba_dict and self._teams_by_id:
            dept_map = get_department_map(list(self._teams_by_id.values()))
            score, breakdown = compute_total_score(
                da_dict, ba_dict, self._teams_by_id, self._blocks_by_id, dept_map,
            )
            self._solution.score = score
            self._solution.score_breakdown = breakdown

    # ------------------------------------------------------------------ right-click

    def _on_team_right_clicked(self, team_id: str, block_id: str):
        if self._solution is None:
            return
        team = self._teams_by_id.get(team_id)
        block = self._blocks_by_id.get(block_id)
        if team is None or block is None:
            return

        menu = QMenu()
        header = menu.addAction(f"{team.name}")
        header.setEnabled(False)
        menu.addSeparator()

        for day in DAYS:
            if day == self._day:
                continue

            day_view = self._solution.get_day_view(day)
            already_here = team_id in day_view.get(block_id, [])

            if already_here:
                act = menu.addAction(f"Day {day}  —  already here")
                act.setEnabled(False)
                continue

            # Capacity check for target day
            occupied = sum(
                self._teams_by_id[tid].size
                for tid in day_view.get(block_id, [])
                if tid in self._teams_by_id
            )
            fits = (occupied + team.size) <= block.capacity

            label = (
                f"Day {day}  —  OK (fits)"
                if fits
                else f"Day {day}  —  over capacity (allowed)"
            )
            act = menu.addAction(_dot_icon("#27AE60" if fits else "#D0021B"), label)
            act.setData(("assign", team_id, block_id, day))

        menu.addSeparator()
        remove_act = menu.addAction(
            _dot_icon("#888888"),
            f"Remove from Day {self._day}",
        )
        remove_act.setData(("remove", team_id, block_id, self._day))

        from PySide6.QtGui import QCursor
        chosen = menu.exec(QCursor.pos())
        if chosen and chosen.data():
            action, t_id, b_id, target_day = chosen.data()
            if action == "assign":
                self._assign_to_day(t_id, b_id, target_day)
            elif action == "remove":
                self._remove_from_day(t_id, target_day)

    def _assign_to_day(self, team_id: str, block_id: str, day: int):
        """Add or move the team's assignment to block_id on the given day."""
        if self._solution is None:
            return

        # Guard: no 3rd distinct day
        existing_days = list(set(
            ba.day for ba in self._solution.block_assignments if ba.team_id == team_id
        ))
        if len(existing_days) >= 2 and day not in existing_days:
            return

        existing = next(
            (ba for ba in self._solution.block_assignments
             if ba.team_id == team_id and ba.day == day),
            None,
        )
        if existing:
            existing.block_id = block_id
        else:
            self._solution.block_assignments.append(
                TeamBlockAssignment(team_id=team_id, day=day, block_id=block_id)
            )

        self._recompute_score()
        self._rebuild_scene()
        self.team_moved.emit(team_id, "__right_click__", block_id, day)

    def _remove_from_day(self, team_id: str, day: int):
        """Remove the team's block assignment for the given day."""
        if self._solution is None:
            return
        self._solution.block_assignments = [
            ba for ba in self._solution.block_assignments
            if not (ba.team_id == team_id and ba.day == day)
        ]
        self._recompute_score()
        self._rebuild_scene()
        self.team_removed_from_day.emit(team_id, day)

    team_removed_from_day = Signal(str, int)  # team_id, day


# ---------------------------------------------------------------------------
# Manual Tab
# ---------------------------------------------------------------------------

class ManualTab(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._solution: Solution | None = None
        # Source-of-truth for manual assignments
        self._team_days: dict[str, list[int]] = {}    # team_id -> [day, ...]
        self._team_block: dict[tuple, str] = {}        # (team_id, day) -> block_id
        self._current_day: int = 1

        self._build_ui()
        self._reset_to_new()

    # ---------------------------------------------------------------------- UI

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        top_bar.addWidget(QLabel("Cover Pair:"))
        self._cover_combo = QComboBox()
        for a, b in ALL_COVER_PAIRS:
            self._cover_combo.addItem(f"Day {a} & Day {b}", userData=(a, b))
        top_bar.addWidget(self._cover_combo)
        top_bar.addStretch()

        self._new_btn = QPushButton("New")
        self._new_btn.setToolTip("Start a fresh empty solution")
        self._new_btn.clicked.connect(self._on_new)
        top_bar.addWidget(self._new_btn)


        self._load_btn = QPushButton("Load Solution…")
        self._load_btn.clicked.connect(self._on_load)
        top_bar.addWidget(self._load_btn)

        self._save_btn = QPushButton("Save Solution")
        self._save_btn.setStyleSheet(
            "QPushButton { background: #4A90D9; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #2c6fad; }"
        )
        self._save_btn.clicked.connect(self._on_save)
        top_bar.addWidget(self._save_btn)

        layout.addLayout(top_bar)

        # Warning banner (hidden when no violations)
        self._warning_banner = QLabel()
        self._warning_banner.setWordWrap(True)
        self._warning_banner.setStyleSheet(
            "QLabel { background: #f8d7da; color: #721c24; "
            "border: 1px solid #f5c6cb; border-radius: 4px; padding: 6px 10px; }"
        )
        self._warning_banner.hide()
        layout.addWidget(self._warning_banner)

        # Main horizontal splitter: team list | grid
        splitter = QSplitter(Qt.Horizontal)

        # Left: team list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)
        header_row = QHBoxLayout()
        header_row.setSpacing(4)
        lbl = QLabel("<b>Teams</b>")
        lbl.setToolTip(
            "Drag a team onto a block to assign it.\n"
            "Drag a team from a block back here to unassign it from the current day."
        )
        header_row.addWidget(lbl)
        header_row.addStretch()
        header_row.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Department", "dept")
        self._sort_combo.addItem("Size ↓", "size_desc")
        self._sort_combo.addItem("Size ↑", "size_asc")
        self._sort_combo.addItem("Name", "name")
        self._sort_combo.setFixedWidth(80)
        self._sort_combo.currentIndexChanged.connect(self._update_team_list)
        header_row.addWidget(self._sort_combo)
        left_layout.addLayout(header_row)

        self._team_list = _TeamListWidget()
        self._team_list.team_returned.connect(self._on_team_returned)
        self._team_list.currentItemChanged.connect(self._on_team_selection_changed)
        left_layout.addWidget(self._team_list)
        left.setMinimumWidth(190)
        left.setMaximumWidth(300)
        splitter.addWidget(left)

        # Right: day selector + zoom + grid
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        day_row = QHBoxLayout()
        day_row.addWidget(QLabel("Day:"))
        self._day_selector = DaySelectorWidget()
        self._day_selector.day_changed.connect(self._on_day_changed)
        day_row.addWidget(self._day_selector)
        day_row.addStretch()
        right_layout.addLayout(day_row)

        # Zoom controls
        zoom_bar = QHBoxLayout()
        zoom_bar.setSpacing(4)
        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedSize(28, 22)
        self._zoom_in_btn.setToolTip("Zoom in (Ctrl+scroll)")
        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedSize(28, 22)
        self._zoom_out_btn.setToolTip("Zoom out (Ctrl+scroll)")
        self._zoom_reset_btn = QPushButton("Fit")
        self._zoom_reset_btn.setFixedSize(36, 22)
        self._zoom_reset_btn.setToolTip("Reset zoom to fit")
        for btn in (self._zoom_in_btn, self._zoom_out_btn, self._zoom_reset_btn):
            btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 0 4px; border: 1px solid #bbb;"
                " border-radius: 3px; background: #f5f5f5; }"
                "QPushButton:hover { background: #e0e0e0; }"
            )
        zoom_bar.addWidget(self._zoom_in_btn)
        zoom_bar.addWidget(self._zoom_out_btn)
        zoom_bar.addWidget(self._zoom_reset_btn)
        zoom_bar.addStretch()
        right_layout.addLayout(zoom_bar)

        self._grid = _ManualGridView()
        self._grid.team_moved.connect(self._on_team_moved)
        self._grid.team_removed_from_day.connect(self._on_team_removed_from_day)
        self._zoom_in_btn.clicked.connect(self._grid.zoom_in)
        self._zoom_out_btn.clicked.connect(self._grid.zoom_out)
        self._zoom_reset_btn.clicked.connect(self._grid.zoom_reset)
        right_layout.addWidget(self._grid, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([220, 800])
        layout.addWidget(splitter, stretch=1)

        self._cover_combo.currentIndexChanged.connect(self._on_cover_changed)

    # ---------------------------------------------------------------------- state helpers

    def _reset_to_new(self):
        """Discard all assignments and start fresh."""
        self._team_days = {}
        self._team_block = {}
        self._solution = self._make_empty_solution()
        self._update_team_list()
        self._reload_grid()
        self._check_constraints()

    def _make_empty_solution(self) -> Solution:
        return Solution(
            solution_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            cover_pair=self._get_cover_pair(),
            day_assignments=[],
            block_assignments=[],
            score=0.0,
            score_breakdown={},
            metadata={"source": "manual"},
        )

    def _get_cover_pair(self) -> tuple:
        pair = self._cover_combo.currentData()
        return pair if pair else (1, 2)

    def _sync_day_assignments(self):
        """Rebuild solution.day_assignments from _team_days (only fully assigned teams)."""
        if self._solution is None:
            return
        self._solution.day_assignments = [
            TeamDayAssignment(team_id=tid, days=tuple(sorted(days)))
            for tid, days in self._team_days.items()
            if len(days) == 2
        ]
        self._solution.cover_pair = self._get_cover_pair()

    # ---------------------------------------------------------------------- UI refresh

    def _update_team_list(self):
        self._team_list.clear()
        teams = self._state.teams
        if not teams:
            item = QListWidgetItem("No teams loaded.\nUse File > Open Teams JSON.")
            item.setFlags(Qt.NoItemFlags)
            self._team_list.addItem(item)
            return

        sort_key = self._sort_combo.currentData()
        if sort_key == "size_desc":
            sorted_teams = sorted(teams, key=lambda t: (-t.size, t.name))
        elif sort_key == "size_asc":
            sorted_teams = sorted(teams, key=lambda t: (t.size, t.name))
        elif sort_key == "name":
            sorted_teams = sorted(teams, key=lambda t: t.name)
        else:  # "dept" (default)
            sorted_teams = sorted(teams, key=lambda t: (t.department, t.name))

        for team in sorted_teams:
            days = sorted(self._team_days.get(team.team_id, []))
            if days:
                parts = []
                for d in days:
                    blk = self._team_block.get((team.team_id, d), "?")
                    parts.append(f"Day {d} → {blk}")
                day_str = ",  ".join(parts)
            else:
                day_str = "unassigned"

            text = f"{team.name}  [{team.size}]  {team.department}\n  {day_str}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, team.team_id)

            if len(days) == 2:
                item.setBackground(QColor("#d4edda"))   # green — fully assigned
            elif len(days) == 1:
                item.setBackground(QColor("#fff3cd"))   # yellow — partial
            # else white (unassigned)

            self._team_list.addItem(item)

    def _reload_grid(self):
        if not self._state.blocks or self._solution is None:
            return
        self._grid.load(
            self._solution,
            self._current_day,
            self._state.blocks,
            self._state.teams_by_id,
            dept_color_fn=self._state.dept_color,
        )

    def _update_warning_banner(self, warnings: list[str]):
        if warnings:
            self._warning_banner.setText(
                "\n".join(f"\u26a0\ufe0f  {w}" for w in warnings)
            )
            self._warning_banner.show()
        else:
            self._warning_banner.hide()

    # ---------------------------------------------------------------------- constraints

    def _check_constraints(self) -> list[str]:
        warnings: list[str] = []
        teams_by_id = self._state.teams_by_id

        if not teams_by_id:
            self._update_warning_banner(warnings)
            return warnings

        all_ids = set(teams_by_id.keys())

        # 1. Unassigned teams
        unassigned = [tid for tid in all_ids if not self._team_days.get(tid)]
        if unassigned:
            sample = ", ".join(teams_by_id[tid].name for tid in unassigned[:3])
            tail = f" (+{len(unassigned) - 3})" if len(unassigned) > 3 else ""
            warnings.append(f"Not assigned to any days: {sample}{tail}")

        # 2. Partially assigned (only 1 day)
        partial = [tid for tid in all_ids if len(self._team_days.get(tid, [])) == 1]
        if partial:
            sample = ", ".join(teams_by_id[tid].name for tid in partial[:3])
            tail = f" (+{len(partial) - 3})" if len(partial) > 3 else ""
            warnings.append(f"Only 1 day assigned (need 2): {sample}{tail}")

        # 3. Cover constraint (only for fully assigned teams)
        a, b = self._get_cover_pair()
        cover_viols = [
            tid for tid, days in self._team_days.items()
            if len(days) == 2 and a not in days and b not in days
        ]
        if cover_viols:
            sample = ", ".join(teams_by_id[tid].name for tid in cover_viols[:3])
            tail = f" (+{len(cover_viols) - 3})" if len(cover_viols) > 3 else ""
            warnings.append(
                f"Cover constraint (Day {a} & Day {b}) violated: {sample}{tail}"
            )

        # 4. Block capacity
        for day in DAYS:
            loads: dict[str, int] = {}
            for (tid, d), block_id in self._team_block.items():
                if d == day:
                    team = teams_by_id.get(tid)
                    if team:
                        loads[block_id] = loads.get(block_id, 0) + team.size
            for block_id, used in loads.items():
                blk = self._state.blocks_by_id.get(block_id)
                if blk and used > blk.capacity:
                    warnings.append(
                        f"Block {block_id} over capacity on Day {day} "
                        f"({used}/{blk.capacity})"
                    )

        self._update_warning_banner(warnings)
        return warnings

    # ---------------------------------------------------------------------- event handlers

    def _on_day_changed(self, day: int):
        self._current_day = day
        self._reload_grid()
        # _reload_grid → _rebuild_scene → _apply_team_highlights automatically,
        # but we also sync the selected team in case list selection is active
        item = self._team_list.currentItem()
        if item:
            self._grid.set_team_highlight(item.data(Qt.UserRole))

    def _on_cover_changed(self, _index: int):
        if self._solution is not None:
            self._solution.cover_pair = self._get_cover_pair()
        self._check_constraints()

    def _on_team_selection_changed(self, current, _previous):
        """Highlight blocks whenever the user clicks a team in the list."""
        if current is None:
            self._grid.set_team_highlight(None)
        else:
            team_id = current.data(Qt.UserRole)
            self._grid.set_team_highlight(team_id)

    def _on_team_moved(
        self, team_id: str, from_block_id: str, to_block_id: str, day: int
    ):
        """Grid emits this after any successful drop or right-click assign."""
        # Sync _team_block from the solution (source of truth after grid mutation)
        self._team_block = {
            (ba.team_id, ba.day): ba.block_id
            for ba in self._solution.block_assignments
        }

        # Register the day for list-to-block drops and right-click assigns
        if from_block_id in ("__list__", "__right_click__"):
            days = self._team_days.setdefault(team_id, [])
            if day not in days:
                days.append(day)
                days.sort()

        self._sync_day_assignments()
        self._check_constraints()
        self._update_team_list()

    def _on_team_returned(self, team_id: str, from_block_id: str):
        """Team chip was dragged from a block and dropped on the team list → unassign."""
        self._remove_day_assignment(team_id, self._current_day)
        self._reload_grid()

    def _on_team_removed_from_day(self, team_id: str, day: int):
        """Right-click 'Remove from Day N' on a team chip → unassign from that day."""
        self._remove_day_assignment(team_id, day)
        # Grid already rebuilt by _ManualGridView._remove_from_day

    def _remove_day_assignment(self, team_id: str, day: int):
        """Shared removal: update local state and solution to drop (team_id, day)."""
        # Sync local dict from solution (grid may have already mutated block_assignments)
        self._team_block = {
            (ba.team_id, ba.day): ba.block_id
            for ba in self._solution.block_assignments
        }
        self._team_block.pop((team_id, day), None)

        days = self._team_days.get(team_id, [])
        if day in days:
            days.remove(day)

        self._sync_day_assignments()
        self._check_constraints()
        self._update_team_list()

    # ---------------------------------------------------------------------- buttons

    def _on_new(self):
        if not self._state.blocks or not self._state.teams:
            QMessageBox.warning(
                self, "No Data",
                "Please load an office map and teams first (File menu).",
            )
            return
        if self._team_block:
            result = QMessageBox.question(
                self, "New Manual Solution",
                "Start a new empty solution? Current work will be lost.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return
        self._reset_to_new()


    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Solution",
            str(self._state.solutions_dir),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            solution = persistence.load_solution(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Failed to load solution:\n{exc}")
            return

        self._solution = solution
        self._team_days = {}
        self._team_block = {}

        for da in solution.day_assignments:
            self._team_days[da.team_id] = list(da.days)

        for ba in solution.block_assignments:
            self._team_block[(ba.team_id, ba.day)] = ba.block_id

        # Sync cover pair combo (suppress _on_cover_changed side-effects by
        # iterating without triggering constraint check — cover check happens below)
        cp = solution.cover_pair
        for i in range(self._cover_combo.count()):
            if self._cover_combo.itemData(i) == cp:
                self._cover_combo.blockSignals(True)
                self._cover_combo.setCurrentIndex(i)
                self._cover_combo.blockSignals(False)
                break

        self._update_team_list()
        self._reload_grid()
        self._check_constraints()

    def _on_save(self):
        if not self._state.blocks or not self._state.teams:
            QMessageBox.warning(self, "No Data", "Please load data files first.")
            return

        self._sync_day_assignments()
        warnings = self._check_constraints()

        if warnings:
            result = QMessageBox.question(
                self, "Constraint Violations",
                "There are constraint violations:\n\n"
                + "\n".join(f"  \u2022 {w}" for w in warnings)
                + "\n\nSave anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return

        try:
            persistence.save_solution(self._solution, self._state.solutions_dir)
            # Add to app state if not already there
            if not any(
                s.solution_id == self._solution.solution_id
                for s in self._state.solutions
            ):
                self._state.solutions.insert(0, self._solution)
            self._state.solution_list_changed.emit()
            QMessageBox.information(
                self, "Saved",
                f"Solution {self._solution.solution_id} saved.",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Failed to save:\n{exc}")

    # ---------------------------------------------------------------------- Qt events

    def showEvent(self, event):
        super().showEvent(event)
        # Refresh team list in case data files changed since last visit
        self._update_team_list()
        if self._solution is not None and self._state.blocks:
            self._reload_grid()
        self._check_constraints()
        QTimer.singleShot(0, self._grid._fit_in_view)
