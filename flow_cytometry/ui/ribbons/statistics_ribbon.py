"""Statistics ribbon — add and configure population statistics.

Actions: Add Statistic (type dropdown), Custom Formula, Export Stats.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from biopro.ui.theme import Colors, Fonts
from biopro.shared.ui.ui_components import PrimaryButton, SecondaryButton

from ...analysis.state import FlowState
from ..widgets.styled_combo import FlowComboBox
from ...analysis.statistics import StatType


class StatisticsRibbon(QWidget):
    """Toolbar ribbon for statistics actions."""

    add_stat_requested = pyqtSignal(str)   # stat type name
    export_requested = pyqtSignal()

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        label = QLabel("Add Statistic:")
        label.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" font-weight: 600; background: transparent;"
        )
        layout.addWidget(label)

        self._stat_combo = FlowComboBox()
        for st in StatType:
            display = st.value.replace("_", " ").title()
            self._stat_combo.addItem(display, st.value)
        layout.addWidget(self._stat_combo)

        btn_add = PrimaryButton("➕ Add")
        btn_add.setToolTip("Add the selected statistic to the current population")
        btn_add.clicked.connect(
            lambda: self.add_stat_requested.emit(
                self._stat_combo.currentData()
            )
        )
        layout.addWidget(btn_add)

        btn_export = SecondaryButton("📤 Export Stats")
        btn_export.setToolTip("Export all statistics to CSV")
        btn_export.clicked.connect(self.export_requested)
        layout.addWidget(btn_export)

        layout.addStretch()
