"""Global styled combo box for the flow module.

This addresses the pervasive text cutoff issue by automatically sizing
to contents, preventing automatic text ellipsis in the dropdown view,
and wrapping long text lines correctly.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QListView

from biopro.ui.theme import Colors, Fonts


class FlowComboBox(QComboBox):
    """A combo box that prevents text truncation.

    Automatically expands its dropdown menu to fit wide contents
    and disables Ellipsis truncation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Completely prevents the combobox from shrinking and hiding text in the collapsed state
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        
        view = QListView()
        view.setTextElideMode(Qt.TextElideMode.ElideNone)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setView(view)
        
        self.setStyleSheet(
            f"QComboBox {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.FG_PRIMARY}; border: 1px solid {Colors.BORDER};"
            f" border-radius: 4px; padding: 4px 8px;"
            f" font-size: {Fonts.SIZE_SMALL}px; }}"
            f"QComboBox QAbstractItemView {{ min-width: 200px; padding: 4px; }}"
        )

    def showPopup(self):
        """Dynamically ensure the popup list fits all text before showing."""
        width = self.width()
        font_metrics = self.fontMetrics()
        for i in range(self.count()):
            text_width = font_metrics.horizontalAdvance(self.itemText(i)) + 30
            if text_width > width:
                width = text_width
        self.view().setMinimumWidth(width)
        super().showPopup()
