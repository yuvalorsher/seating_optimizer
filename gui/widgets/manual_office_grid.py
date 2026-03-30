from __future__ import annotations

from PySide6.QtCore import Signal

from gui.widgets.office_grid import OfficeGridView


class ManualOfficeGrid(OfficeGridView):
    """Subclass of OfficeGridView for manual seating mode.

    Instead of mutating a Solution on drop, emits drop_requested so that
    ManualTab can show a count dialog and update ManualState.
    Also forwards team_right_clicked from BlockItems as chip_right_clicked.
    Preserves user zoom across scene rebuilds.
    """

    drop_requested = Signal(str, object, str)  # group_id, from_block_id_or_None, to_block_id
    chip_right_clicked = Signal(str, str)       # group_id, block_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._allow_oversize = True  # capacity violations are shown as warnings, not blocked

    def _rebuild_scene(self):
        saved_zoomed = self._user_zoomed
        saved_scale = self._current_scale
        super()._rebuild_scene()
        # Connect right-click signals for all block items (parent does not do this)
        for item in self._block_items.values():
            item.team_right_clicked.connect(self.chip_right_clicked)
        # Restore user zoom (parent resets it to 1.0 in _rebuild_scene)
        if saved_zoomed and saved_scale != 1.0:
            self._user_zoomed = True
            self._current_scale = saved_scale
            self.scale(saved_scale, saved_scale)

    def _on_group_dropped(self, group_id: str, from_block_id, to_block_id: str):
        """Override: do NOT mutate solution. Let ManualTab handle it."""
        self.drop_requested.emit(group_id, from_block_id, to_block_id)
