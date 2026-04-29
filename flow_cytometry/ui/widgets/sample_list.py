"""Sample list widget — lists loaded samples without gating hierarchy."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.experiment import Sample
from ...analysis.state import FlowState
from biopro.sdk.core.events import CentralEventBus
from ...analysis import events


# Icons and Colors from the original SampleTree
_ROLE_BADGES = {
    "tube": "○",
    "fmo": "◉",
    "compensation": "◧",
    "blank": "◌",
}

_ROLE_COLORS = {
    "tube": Colors.FG_PRIMARY,
    "fmo": Colors.ACCENT_PRIMARY,
    "compensation": "#FFB74D",
    "blank": Colors.FG_DISABLED,
}


class SampleList(QWidget):
    """List of loaded samples with basic stats.

    Signals:
        sample_double_clicked(sample_id): Emitted on double click.
        selection_changed(sample_id): Emitted on selection change.
    """

    sample_double_clicked = pyqtSignal(str)
    selection_changed = pyqtSignal(str)

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._active_group_filter: str = "__all__"
        self._setup_ui()
        self._setup_events()

    def _setup_events(self) -> None:
        """Subscribe to relevant state events."""
        CentralEventBus.subscribe(events.SAMPLE_LOADED, self._on_sample_loaded)

    def _on_sample_loaded(self, data: dict) -> None:
        """Handle incoming sample loaded events."""
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tree widget using QTreeWidget for multi-column support
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Sample", "Events"])
        self._tree.setColumnCount(2)
        self._tree.setIndentation(0)
        self._tree.setRootIsDecorated(False)

        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header_view.resizeSection(1, 75)

        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {Colors.BG_DARKEST};"
            f" border: none; outline: none;"
            f" color: {Colors.FG_PRIMARY};"
            f" font-size: {Fonts.SIZE_SMALL}px; }}"
            f"QTreeWidget::item {{ padding: 6px 4px;"
            f" border-bottom: 1px solid {Colors.BG_DARK}; }}"
            f"QTreeWidget::item:selected {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.ACCENT_PRIMARY}; border-left: 3px solid {Colors.ACCENT_PRIMARY}; }}"
            f"QTreeWidget::item:hover {{ background: {Colors.BG_DARK}; }}"
            f"QHeaderView::section {{ background: {Colors.BG_DARK};"
            f" color: {Colors.FG_SECONDARY}; border: none;"
            f" border-bottom: 1px solid {Colors.BORDER};"
            f" padding: 4px 6px; font-size: 10px; font-weight: 600; }}"
        )

        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree, stretch=1)

        # Empty state placeholder
        self._empty_label = QLabel(
            "No samples loaded.\n\n"
            "Use the Workspace toolbar to:\n"
            "• Add Samples (FCS files)\n"
            "• Load a Workflow Template"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; padding: 24px;"
        )
        layout.addWidget(self._empty_label)

        self._update_empty_state()

    def filter_by_group(self, group_id: str) -> None:
        """Filter the list by group."""
        self._active_group_filter = group_id
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the list from the current state."""
        self._tree.clear()
        samples = self._get_filtered_samples()

        for sample in samples:
            item = self._create_sample_item(sample)
            self._tree.addTopLevelItem(item)

        self._update_empty_state()

    def update_all_sample_stats(self, *args, **kwargs) -> None:
        """Compatibility signature to absorb signal events harmlessly or update event counts."""
        self.refresh()

    def update_gate_stats(self, sample_id: str, gate_id: str = "") -> None:
        pass  # We don't track gates here

    def _get_filtered_samples(self) -> list[Sample]:
        experiment = self._state.experiment
        if self._active_group_filter == "__all__":
            return list(experiment.samples.values())

        group = experiment.groups.get(self._active_group_filter)
        if not group:
            return list(experiment.samples.values())

        return [
            experiment.samples[sid]
            for sid in group.sample_ids
            if sid in experiment.samples
        ]

    def _create_sample_item(self, sample: Sample) -> QTreeWidgetItem:
        badge = _ROLE_BADGES.get(sample.role, "○")
        name = f"{badge} {sample.display_name}"

        if sample.markers:
            name += f"  [{', '.join(sample.markers)}]"

        item = QTreeWidgetItem([
            name,
            f"{sample.event_count:,}" if sample.has_data else "—",
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, sample.sample_id)
        item.setToolTip(0, name)

        color = _ROLE_COLORS.get(sample.role, "#B0BEC5")
        item.setForeground(0, QColor(color))
        
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)

        return item
    
    def select_sample(self, sample_id: str | None) -> None:
        """Select a sample in the list by ID."""
        if not sample_id:
            self._tree.clearSelection()
            return
            
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == sample_id:
                self._tree.setCurrentItem(item)
                break

    def _update_empty_state(self) -> None:
        is_empty = self._tree.topLevelItemCount() == 0
        self._tree.setVisible(not is_empty)
        self._empty_label.setVisible(is_empty)

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        if item is None:
            return
        sample_id = item.data(0, Qt.ItemDataRole.UserRole)
        if sample_id:
            self.sample_double_clicked.emit(sample_id)

    def _on_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        if current is None:
            return
        sample_id = current.data(0, Qt.ItemDataRole.UserRole)
        if sample_id:
            self.selection_changed.emit(sample_id)

    def cleanup(self) -> None:
        """Clear tree state."""
        self._tree.clear()
