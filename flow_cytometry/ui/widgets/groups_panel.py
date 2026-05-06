"""Groups panel — displays sample groups with roles and colors.

Shows all defined groups in the workspace.  Clicking a group filters
the sample tree below to show only that group's samples.

Displays group list: Name, Size (count), Role (compensation,
control, test), and a color indicator.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.experiment import Group

logger = get_logger(__name__, "flow_cytometry")


class GroupsPanel(QWidget):
    """Left-sidebar panel showing sample groups.

    Signals:
        group_selected(group_id): Emitted when a group is clicked.
    """

    group_selected = pyqtSignal(str)

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self.setFixedHeight(160)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)

        header = QLabel("Groups")
        header.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" font-weight: 700; text-transform: uppercase;"
            f" letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {Colors.BG_DARKEST};"
            f" border: none; outline: none; }}"
            f"QListWidget::item {{ padding: 6px 8px;"
            f" border-bottom: 1px solid {Colors.BORDER};"
            f" color: {Colors.FG_PRIMARY}; }}"
            f"QListWidget::item:selected {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.ACCENT_PRIMARY}; }}"
            f"QListWidget::item:hover {{ background: {Colors.BG_DARK}; }}"
        )
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, stretch=1)

        # Add "All Samples" as default
        self._populate_default()

    def _populate_default(self) -> None:
        """Add the default 'All Samples' entry."""
        self._list.clear()
        item = QListWidgetItem("📂  All Samples")
        item.setData(Qt.ItemDataRole.UserRole, "__all__")
        self._list.addItem(item)
        self._list.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        if item:
            group_id = item.data(Qt.ItemDataRole.UserRole)
            self.group_selected.emit(group_id or "__all__")

    def refresh(self) -> None:
        """Rebuild the group list from the current state."""
        self._list.clear()

        # Always include "All Samples"
        all_item = QListWidgetItem("📂  All Samples")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        self._list.addItem(all_item)

        for group in self._state.experiment.groups.values():
            role_icon = {
                "compensation": "🔬",
                "control": "🎛",
                "test": "🧪",
                "all_samples": "📂",
                "custom": "📁",
            }.get(group.role.value, "📁")

            text = f"{role_icon}  {group.name}  ({group.size})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, group.group_id)
            self._list.addItem(item)

        self._list.setCurrentRow(0)
