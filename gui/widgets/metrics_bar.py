from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame


def _metric_label(title: str, value: str, color: str = "#333") -> tuple[QWidget, QLabel]:
    container = QFrame()
    container.setFrameShape(QFrame.StyledPanel)
    container.setStyleSheet(
        "QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 4px 10px; }"
    )
    inner = QHBoxLayout(container)
    inner.setContentsMargins(6, 4, 6, 4)
    inner.setSpacing(6)

    title_lbl = QLabel(title + ":")
    title_lbl.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")
    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(f"font-size: 13px; color: {color}; font-weight: bold;")

    inner.addWidget(title_lbl)
    inner.addWidget(value_lbl)
    return container, value_lbl


class MetricsBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._score_container, self._score_lbl = _metric_label("Score", "—")
        self._comp_container, self._comp_lbl = _metric_label("Compactness", "—")
        self._cons_container, self._cons_lbl = _metric_label("Consistency", "—")
        self._cover_container, self._cover_lbl = _metric_label("Cover Days", "—")
        self._id_container, self._id_lbl = _metric_label("Solution ID", "—")

        for w in [
            self._score_container,
            self._comp_container,
            self._cons_container,
            self._cover_container,
            self._id_container,
        ]:
            layout.addWidget(w)

        layout.addStretch()

    def update_metrics(self, solution):
        if solution is None:
            for lbl in [
                self._score_lbl,
                self._comp_lbl,
                self._cons_lbl,
                self._cover_lbl,
                self._id_lbl,
            ]:
                lbl.setText("—")
            return

        score = solution.score
        breakdown = solution.score_breakdown
        compactness = breakdown.get("compactness", 0.0)
        consistency = breakdown.get("consistency", 0.0)
        cover = solution.cover_pair

        if score >= 0.8:
            score_color = "#27AE60"
        elif score >= 0.6:
            score_color = "#F5A623"
        else:
            score_color = "#D0021B"

        self._score_lbl.setText(f"{score:.3f}")
        self._score_lbl.setStyleSheet(f"font-size: 13px; color: {score_color}; font-weight: bold;")
        self._comp_lbl.setText(f"{compactness * 100:.1f}%")
        self._cons_lbl.setText(f"{consistency * 100:.1f}%")
        self._cover_lbl.setText(f"Day {cover[0]} & Day {cover[1]}")
        self._id_lbl.setText(solution.solution_id)
