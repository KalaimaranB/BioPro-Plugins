"""Properties panel — context-sensitive detail view for selected items.

Shows different content depending on what's selected:
- **Sample**: file metadata, keywords, channel list, marker assignments
- **Gate**: gate type, parameters, event count, %parent, %total,
  plus computed statistics (Mean, MFI, CV)
- **No selection**: general workspace info

This is the right-side panel of the workspace.  It refreshes in
real-time when gate statistics are updated by the ``GateController``
or ``GatePropagator``.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QLineEdit,
    QPushButton,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.experiment import Sample, SampleRole
from ...analysis.gate_controller import GateController

logger = logging.getLogger(__name__)


class PropertiesPanel(QWidget):
    """Right-sidebar panel showing properties of the selected item.

    Dynamically updates when the user clicks on a sample or gate
    in the sample tree, and refreshes live when gate statistics
    are recomputed.
    """

    def __init__(self, state: FlowState, controller: GateController, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._controller = controller
        self._current_sample_id: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        self._header = QLabel("Properties")
        self._header.setFixedHeight(32)
        self._header.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" font-weight: 700; text-transform: uppercase;"
            f" letter-spacing: 1px; background: {Colors.BG_DARK};"
            f" padding: 6px 12px;"
            f" border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(self._header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {Colors.BG_DARKEST};")

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        self._content_layout.setSpacing(8)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._content)
        layout.addWidget(scroll, stretch=1)

        # Initial state
        self._show_empty()

    def show_sample_properties(
        self, sample_id: str, gate_id: Optional[str]
    ) -> None:
        """Update the panel to show properties of the selected item.

        Args:
            sample_id: The selected sample's ID.
            gate_id:   The selected gate's ID (None if sample root).
        """
        self._current_sample_id = sample_id
        self._current_node_id = gate_id

        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            self._show_empty()
            return

        if gate_id:
            self._show_gate_properties(sample, gate_id)
        else:
            self._show_sample_details(sample)

    def refresh(self) -> None:
        """Refresh the panel (e.g., after state restore)."""
        if self._current_sample_id and self._current_node_id:
            self.show_sample_properties(
                self._current_sample_id, self._current_node_id
            )
        elif self._current_sample_id:
            self.show_sample_properties(self._current_sample_id, None)
        else:
            self._show_empty()

    def refresh_gate_stats(self, sample_id: str, node_id: str) -> None:
        """Live-refresh if the currently displayed gate was updated.

        Called by the ``GateController`` when stats change.

        Args:
            sample_id: The sample whose gate was updated.
            node_id:   The gate that was updated.
        """
        if (self._current_sample_id == sample_id
                and self._current_node_id == node_id):
            self.show_sample_properties(sample_id, node_id)

    # ── Private display methods ───────────────────────────────────────

    def _clear_content(self) -> None:
        """Remove all widgets from the content area."""
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_empty(self) -> None:
        """Show empty/default state."""
        self._clear_content()
        self._header.setText("Properties")
        self._current_sample_id = None
        self._current_node_id = None

        lbl = QLabel(
            "Select a sample or gate\nfrom the tree to view\nits properties."
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; padding: 24px;"
        )
        self._content_layout.addWidget(lbl)

    def _show_sample_details(self, sample: Sample) -> None:
        """Display sample metadata and channel info."""
        self._clear_content()
        self._header.setText(f"📄 {sample.display_name}")

        form = QFormLayout()
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        label_style = (
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent;"
        )
        value_style = (
            f"color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent;"
        )

        def _add_row(label_text: str, value_text: str) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            val = QLabel(value_text)
            val.setStyleSheet(value_style)
            val.setWordWrap(True)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            form.addRow(lbl, val)

        # Basic info
        _add_row("Role:", sample.role.value.replace("_", " ").title())
        _add_row("Events:", f"{sample.event_count:,}" if sample.has_data else "Not loaded")

        if sample.fcs_data:
            _add_row("File:", sample.fcs_data.file_path.name)

        if sample.markers:
            _add_row("Markers:", ", ".join(sample.markers))
        if sample.fmo_minus:
            _add_row("FMO Minus:", sample.fmo_minus)
        if sample.is_compensated:
            _add_row("Compensated:", "✅ Yes")

        # Gate count
        gate_count = self._count_gates(sample.gate_tree)
        if gate_count > 0:
            _add_row("Gates:", f"{gate_count} population{'s' if gate_count > 1 else ''}")

        # Channel list — show all, word wrap handles overflow
        if sample.fcs_data and sample.fcs_data.channels:
            _add_row("Channels:", ", ".join(sample.fcs_data.channels))

        form_widget = QWidget()
        form_widget.setLayout(form)
        self._content_layout.addWidget(form_widget)
        self._content_layout.addStretch()

    def _show_gate_properties(self, sample: Sample, node_id: str) -> None:
        """Display gate-specific properties with detailed statistics."""
        self._clear_content()

        node = sample.gate_tree.find_node_by_id(node_id)
        if node is None or node.gate is None:
            self._show_empty()
            return

        gate = node.gate
        self._header.setText(f"⊳ {node.name}")

        form = QFormLayout()
        form.setSpacing(6)
        form.setContentsMargins(0, 0, 0, 0)

        label_style = (
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent;"
        )
        value_style = (
            f"color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent;"
        )
        stat_value_style = (
            f"color: {Colors.ACCENT_PRIMARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; font-weight: 600;"
        )

        def _add_row(
            label_text: str, value_text: str, highlight: bool = False
        ) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            val = QLabel(value_text)
            val.setStyleSheet(stat_value_style if highlight else value_style)
            val.setWordWrap(True)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            form.addRow(lbl, val)

        # Population Name
        name_edit = QLineEdit(node.name)
        name_edit.setStyleSheet(f"background: {Colors.BG_DARK}; border: 1px solid {Colors.BORDER}; padding: 4px;")
        name_edit.editingFinished.connect(lambda: self._on_name_changed(name_edit.text()))
        form.addRow("Name:", name_edit)

        # Gate identity
        _add_row("Type:", type(gate).__name__)
        _add_row("X Param:", gate.x_param)
        if gate.y_param:
            _add_row("Y Param:", gate.y_param)
        _add_row("Adaptive:", "🧠 Yes" if gate.adaptive else "No")

        # Invert toggle (Node level)
        negate_cb = QCheckBox("Invert (Select Outside)")
        negate_cb.setChecked(node.negated)
        negate_cb.setStyleSheet(f"color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_SMALL}px;")
        negate_cb.toggled.connect(self._on_negate_toggled)
        form.addRow("", negate_cb)

        # Separator
        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER}; margin: 4px 0;")
        form.addRow(sep)

        # Population statistics — highlighted
        if node.statistics:
            count = node.statistics.get("count", 0)
            pct_parent = node.statistics.get("pct_parent", 0.0)
            pct_total = node.statistics.get("pct_total", 0.0)

            _add_row("Event Count:", f"{int(count):,}", highlight=True)
            _add_row("% Parent:", f"{pct_parent:.2f}%", highlight=True)
            _add_row("% Total:", f"{pct_total:.2f}%", highlight=True)

        # Child gate count
        child_count = len(node.children)
        if child_count > 0:
            _add_row("Sub-gates:", f"{child_count}")

        # Final Assemblage
        form_widget = QWidget()
        form_widget.setLayout(form)
        self._content_layout.addWidget(form_widget)
        
        # Action Section (Split Button) - outside the form for better visibility
        actions_layout = QVBoxLayout()
        actions_layout.setContentsMargins(0, 8, 0, 0)
        
        split_btn = QPushButton("⇶ Split Inside/Outside")
        split_btn.setFixedHeight(32)
        split_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_MEDIUM};
                color: {Colors.ACCENT_PRIMARY};
                border: 1px solid {Colors.ACCENT_PRIMARY};
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_PRIMARY};
                color: {Colors.BG_DARKEST};
            }}
        """)
        split_btn.clicked.connect(self._on_split_clicked)
        actions_layout.addWidget(split_btn)
        
        actions_widget = QWidget()
        actions_widget.setLayout(actions_layout)
        self._content_layout.addWidget(actions_widget)
        
        self._content_layout.addStretch()

    def set_active_gate(self, node_id: Optional[str]) -> None:
        """Update the panel to show properties for a specific population."""
        self.show_sample_properties(self._current_sample_id, node_id)

    def _on_name_changed(self, new_name: str) -> None:
        if self._current_sample_id and self._current_node_id:
            self._controller.rename_population(
                self._current_sample_id, self._current_node_id, new_name
            )

    def _on_negate_toggled(self, negated: bool) -> None:
        """Handle negation toggle at the node level."""
        if self._current_sample_id and self._current_node_id:
            sample = self._state.experiment.samples.get(self._current_sample_id)
            if sample:
                node = sample.gate_tree.find_node_by_id(self._current_node_id)
                if node and node.gate:
                    self._controller.modify_gate(
                        node.gate.gate_id, self._current_sample_id, negated=negated
                    )

    def _on_split_clicked(self) -> None:
        if self._current_sample_id and self._current_node_id:
            self._controller.split_population(
                self._current_sample_id, self._current_node_id
            )

    def _count_gates(self, node) -> int:
        """Count total gates in a tree (excluding root)."""
        count = 0
        for child in node.children:
            if child.gate is not None:
                count += 1
            count += self._count_gates(child)
        return count