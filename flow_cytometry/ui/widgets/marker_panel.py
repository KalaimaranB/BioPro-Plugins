"""Marker panel — marker-to-fluorophore-to-channel mapping editor.

Allows the scientist to explicitly declare which biological markers
are detected by which fluorophores on which channels.  This is a key
scientist-centric feature: once set, the system auto-labels graphs,
auto-pairs FMO controls, and can suggest marker-aware gating strategies.

Can be embedded in the Properties panel or opened as a standalone tab.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.experiment import MarkerMapping

logger = get_logger(__name__, "flow_cytometry")


class MarkerPanel(QWidget):
    """Editable table for marker → fluorophore → channel mappings.

    Signals:
        mappings_changed: Emitted when the user edits any mapping.
    """

    mappings_changed = pyqtSignal()

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Marker Panel")
        header.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" font-weight: 700; text-transform: uppercase;"
            f" letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Marker", "Fluorophore", "Channel", "Color"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)

        self._table.setStyleSheet(
            f"QTableWidget {{ background: {Colors.BG_DARKEST};"
            f" gridline-color: {Colors.BORDER}; border: none;"
            f" color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_SMALL}px; }}"
            f"QTableWidget::item {{ padding: 4px 6px; }}"
            f"QTableWidget::item:selected {{ background: {Colors.BG_MEDIUM}; }}"
            f"QHeaderView::section {{ background: {Colors.BG_DARK};"
            f" color: {Colors.FG_SECONDARY}; border: none;"
            f" border-bottom: 1px solid {Colors.BORDER};"
            f" padding: 4px 6px; font-size: 10px; font-weight: 600; }}"
        )

        self._table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table, stretch=1)

    def refresh(self) -> None:
        """Rebuild the table from the current state."""
        self._table.blockSignals(True)
        self._table.setRowCount(0)

        for mapping in self._state.experiment.marker_mappings:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(mapping.marker_name))
            self._table.setItem(row, 1, QTableWidgetItem(mapping.fluorophore))
            self._table.setItem(row, 2, QTableWidgetItem(mapping.channel))

            color_item = QTableWidgetItem(mapping.color)
            from PyQt6.QtGui import QColor
            color_item.setBackground(QColor(mapping.color))
            self._table.setItem(row, 3, color_item)

        self._table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Sync table edits back to the state."""
        mappings = self._state.experiment.marker_mappings
        if row >= len(mappings):
            return

        item = self._table.item(row, col)
        if item is None:
            return

        value = item.text()
        mapping = mappings[row]

        if col == 0:
            mapping.marker_name = value
        elif col == 1:
            mapping.fluorophore = value
        elif col == 2:
            mapping.channel = value
        elif col == 3:
            mapping.color = value

        self.mappings_changed.emit()
