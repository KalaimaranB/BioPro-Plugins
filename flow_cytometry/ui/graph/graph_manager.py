"""Graph manager — tabbed container for multiple GraphWindow instances.

Handles opening, closing, and switching between graph windows in the
center canvas area of the workspace.  Equivalent to FlowJo's ability
to have multiple graph windows open simultaneously.

Also exposes the active graph's signals for gating integration:
when a tool is selected in the gating ribbon, the GraphManager
forwards the drawing mode to the currently active graph's canvas.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

from .graph_window import GraphWindow
from ...analysis.state import FlowState
from ...analysis.gating import Gate, GateNode

logger = logging.getLogger(__name__)


class GraphManager(QWidget):
    """Tabbed container managing multiple :class:`GraphWindow` instances.

    The center canvas area of the workspace.  Shows a welcome screen
    when no graphs are open, and a tabbed interface when one or more
    graphs are active.

    Signals:
        gate_drawn(Gate, sample_id, parent_node_id):
            Forwarded from the active GraphWindow when a gate is created.
        gate_selection_changed(gate_id):
            Forwarded when a gate overlay is clicked on the canvas.
    """

    gate_drawn = pyqtSignal(object, str, object)  # Gate, sample_id, parent_node_id
    gate_selection_changed = pyqtSignal(object)    # gate_id or None

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._graphs: dict[str, GraphWindow] = {}   # key: "sample_id:gate_id"
        self._current_tool = "select"
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget for multiple graphs
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {Colors.BG_DARKEST}; }}"
            f"QTabBar::tab {{"
            f"  background: {Colors.BG_DARK};"
            f"  color: {Colors.FG_SECONDARY};"
            f"  padding: 6px 14px;"
            f"  border: none;"
            f"  border-bottom: 2px solid transparent;"
            f"  font-size: {Fonts.SIZE_SMALL}px;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  color: {Colors.FG_PRIMARY};"
            f"  border-bottom: 2px solid {Colors.ACCENT_PRIMARY};"
            f"  background: {Colors.BG_DARKEST};"
            f"}}"
            f"QTabBar::tab:hover {{"
            f"  color: {Colors.FG_PRIMARY};"
            f"  background: {Colors.BG_MEDIUM};"
            f"}}"
            f"QTabBar::close-button {{"
            f"  image: none;"
            f"  subcontrol-position: right;"
            f"}}"
        )

        # Welcome/empty screen
        self._welcome = QWidget()
        self._welcome.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        welcome_layout = QVBoxLayout(self._welcome)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("🧪 Flow Cytometry Workspace")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {Colors.FG_PRIMARY}; font-size: 20px;"
            f" font-weight: 700; background: transparent;"
        )
        welcome_layout.addWidget(title)

        subtitle = QLabel(
            "Double-click a sample in the tree to open a graph,\n"
            "or load a workflow template to get started."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_NORMAL}px;"
            f" background: transparent; margin-top: 8px;"
        )
        welcome_layout.addWidget(subtitle)

        # Keyboard shortcut hints
        hints = QLabel(
            "Quick actions:\n"
            "  Workspace tab → Add Samples\n"
            "  Workspace tab → Load Template\n"
        )
        hints.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hints.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; margin-top: 16px;"
        )
        welcome_layout.addWidget(hints)

        layout.addWidget(self._welcome)
        layout.addWidget(self._tabs)

        self._update_visibility()

    # ── Public API ────────────────────────────────────────────────────

    def open_graph_for_sample(
        self, sample_id: str, node_id: Optional[str] = None
    ) -> None:
        """Open (or focus) a graph window for a sample/gate.

        If a graph for this sample+gate already exists, it is brought
        to focus.  Otherwise, a new tab is created.

        Args:
            sample_id: The sample to graph.
            node_id:   The population/node within the sample (None for ungated).
        """
        key = f"{sample_id}:{node_id or 'root'}"

        if key in self._graphs:
            # Focus existing tab
            graph = self._graphs[key]
            idx = self._tabs.indexOf(graph)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            return

        # Create new graph window
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            logger.warning("Cannot open graph — sample %s not found", sample_id)
            return

        graph = GraphWindow(self._state, sample_id, node_id)
        self._graphs[key] = graph

        # Apply current tool
        graph.set_drawing_mode(self._current_tool)

        # Wire signals
        graph.gate_drawn.connect(self._on_gate_drawn)
        graph.gate_selection_changed.connect(self._on_gate_selection)
        graph.axis_scale_sync_requested.connect(self._on_axis_scale_sync)

        tab_label = sample.display_name
        if node_id:
            node = sample.gate_tree.find_node_by_id(node_id)
            if node:
                tab_label = f"{sample.display_name} › {node.name}"

        idx = self._tabs.addTab(graph, tab_label)
        self._tabs.setCurrentIndex(idx)

        self._update_visibility()
        logger.info("Opened graph for %s (population=%s)", sample.display_name, node_id)

    def set_drawing_mode(self, tool_name: str) -> None:
        """Set the drawing mode on all open graph windows.

        Args:
            tool_name: The tool name from GatingRibbon.
        """
        self._current_tool = tool_name
        for graph in self._graphs.values():
            graph.set_drawing_mode(tool_name)

    def set_selected_gate(self, gate_id: Optional[str]) -> None:
        """Highlight a specific gate on the active graph.
        
        Args:
            gate_id: The gate ID to select, or None to deselect.
        """
        graph = self.get_active_graph()
        if graph:
            graph.canvas.select_gate(gate_id)

    def refresh_gates_on_sample(
        self,
        sample_id: str,
        gates: list[Gate],
        gate_nodes: list[GateNode],
    ) -> None:
        """Refresh gate overlays on all open graphs for a sample.

        Args:
            sample_id:  The sample whose gates changed.
            gates:      Updated gate list.
            gate_nodes: Updated gate node list.
        """
        for key, graph in self._graphs.items():
            if graph.sample_id == sample_id:
                graph.refresh_gates(gates, gate_nodes)

    def get_active_graph(self) -> Optional[GraphWindow]:
        """Return the currently active GraphWindow, or None."""
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, GraphWindow) else None

    def _close_tab(self, index: int) -> None:
        """Close a graph tab and clean up."""
        widget = self._tabs.widget(index)
        if isinstance(widget, GraphWindow):
            key = f"{widget.sample_id}:{widget.node_id or 'root'}"
            self._graphs.pop(key, None)

        self._tabs.removeTab(index)
        if widget:
            widget.deleteLater()

        self._update_visibility()

    def _on_tab_changed(self, index: int) -> None:
        """Apply the current drawing mode when switching tabs."""
        graph = self.get_active_graph()
        if graph:
            graph.set_drawing_mode(self._current_tool)

    def _on_gate_drawn(
        self, gate: Gate, sample_id: str, parent_node_id
    ) -> None:
        """Forward gate_drawn from the active graph."""
        self.gate_drawn.emit(gate, sample_id, parent_node_id)

    def _on_gate_selection(self, gate_id) -> None:
        """Forward gate selection from the active graph."""
        self.gate_selection_changed.emit(gate_id)

    def _on_axis_scale_sync(self, channel_name: str, scale) -> None:
        """Propagate AxisScale to all other graphs mapping this channel
        and save to global state for new graphs.
        """
        self._state.channel_scales[channel_name] = scale.copy()
        
        sender = self.sender()
        for graph in self._graphs.values():
            if graph is sender:
                continue
            graph.apply_axis_scale(channel_name, scale)

    def refresh(self) -> None:
        """Refresh all open graph windows."""
        for graph in self._graphs.values():
            graph._update_breadcrumb()

    def _update_visibility(self) -> None:
        """Toggle between welcome screen and tabs."""
        has_graphs = self._tabs.count() > 0
        self._tabs.setVisible(has_graphs)
        self._welcome.setVisible(not has_graphs)
