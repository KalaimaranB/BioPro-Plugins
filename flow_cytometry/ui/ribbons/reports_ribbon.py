"""Reports ribbon — tabular and graphical report generation.

Actions: Table Editor, Layout Editor, Export (CSV, PDF, PNG),
Batch Report.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from biopro.shared.ui.ui_components import PrimaryButton, SecondaryButton

from ...analysis.state import FlowState


class ReportsRibbon(QWidget):
    """Toolbar ribbon for report generation actions."""

    table_editor_requested = pyqtSignal()
    layout_editor_requested = pyqtSignal()
    export_csv_requested = pyqtSignal()
    export_pdf_requested = pyqtSignal()
    batch_report_requested = pyqtSignal()

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        btn_table = PrimaryButton("📊 Table Editor")
        btn_table.setToolTip("Open the tabular report editor")
        btn_table.clicked.connect(self.table_editor_requested)
        layout.addWidget(btn_table)

        btn_layout = SecondaryButton("🖼 Layout Editor")
        btn_layout.setToolTip("Design publication-ready graphical layouts")
        btn_layout.clicked.connect(self.layout_editor_requested)
        layout.addWidget(btn_layout)

        btn_csv = SecondaryButton("📤 Export CSV")
        btn_csv.clicked.connect(self.export_csv_requested)
        layout.addWidget(btn_csv)

        btn_pdf = SecondaryButton("📄 Export PDF")
        btn_pdf.clicked.connect(self.export_pdf_requested)
        layout.addWidget(btn_pdf)

        btn_batch = SecondaryButton("⚡ Batch Report")
        btn_batch.setToolTip("Generate reports for all samples in a group")
        btn_batch.clicked.connect(self.batch_report_requested)
        layout.addWidget(btn_batch)

        layout.addStretch()
