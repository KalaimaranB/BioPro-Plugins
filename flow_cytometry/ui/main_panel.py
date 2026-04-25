"""Flow cytometry workspace — the root panel injected by BioPro.

This is the main entry point UI class.  It sets up the workspace
layout (toolbar ribbon, left sidebar, center canvas, right properties)
and exposes the BioPro-required interface: signals, export_state,
load_state, export_workflow, load_workflow.

It also instantiates and wires the ``GateController`` and
``GatePropagator`` which coordinate gate lifecycle, statistics
computation, and cross-sample gate propagation.

This file is intentionally thin — all complex widgets live in their
own modules under ``ui/widgets/``, ``ui/graph/``, and ``ui/ribbons/``.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biopro.sdk.core import PluginBase
from biopro.ui.theme import Colors, Fonts

# Relative imports — all within this plugin
from .ribbons.workspace_ribbon import WorkspaceRibbon
from .ribbons.compensation_ribbon import CompensationRibbon
from .ribbons.gating_ribbon import GatingRibbon
from .ribbons.statistics_ribbon import StatisticsRibbon
from .ribbons.reports_ribbon import ReportsRibbon
from .widgets.groups_panel import GroupsPanel
from .widgets.sample_list import SampleList
from .widgets.gate_hierarchy import GateHierarchy
from .widgets.properties_panel import PropertiesPanel
from .graph.graph_manager import GraphManager

from ..analysis.state import FlowState
from ..analysis.gate_controller import GateController
from ..analysis.gate_propagator import GatePropagator
from ..analysis.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class FlowCytometryPanel(PluginBase):
    """Root widget for the Flow Cytometry workspace.

    Injected by BioPro's ``ModuleManager`` as the central workspace
    widget.  Provides the full BioPro plugin interface.

    Layout::

        ┌────────────────────────────────────────────────────┐
        │  Tab Bar: Workspace | Compensation | Gating | ...  │
        │  ┌──────────────────────────────────────────────┐  │
        │  │            Toolbar Ribbon (stacked)          │  │
        │  └──────────────────────────────────────────────┘  │
        ├───────────┬────────────────────────┬───────────────┤
        │ Groups    │                        │ Properties &  │
        │ Panel     │   Graph Canvas Area    │ Statistics    │
        │───────────│   (tabbed graphs)      │               │
        │ Sample    │                        │               │
        │ Tree      │                        │               │
        └───────────┴────────────────────────┴───────────────┘

    Signals:
        state_changed:  Emitted on any structural edit (BioPro hooks
                        this to ``HistoryManager`` for undo/redo).
        status_message: Piped to the core status bar.
        results_ready:  Emitted when analysis results are available.
    """

    # ── BioPro-required signals ───────────────────────────────────────
    # state_changed and status_message are now provided by PluginBase
    results_ready = pyqtSignal(object)

    def _setup_logging(self) -> None:
        """Initialize plugin-specific logging to a temporary file."""
        import tempfile
        import os
        from logging.handlers import RotatingFileHandler

        log_file = os.path.join(tempfile.gettempdir(), "biopro_flow.log")
        handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=3)
        formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Get the root logger for this plugin's package
        plugin_logger = logging.getLogger("biopro.plugins.flow_cytometry")
        plugin_logger.setLevel(logging.DEBUG)
        plugin_logger.addHandler(handler)
        
        # Ensure the handler is removed on shutdown to avoid leaks
        self._log_handler = handler
        
        logger.info(f"Plugin logging initialized. Writing to: {log_file}")

    def __init__(self, plugin_id: str = "flow_cytometry", parent=None) -> None:
        super().__init__(plugin_id, parent)
        self._setup_logging()

        # ── State ─────────────────────────────────────────────────────
        self.state = FlowState()

        # ── Analysis engines ──────────────────────────────────────────
        from ..analysis.axis_manager import AxisManager
        from ..analysis.population_service import PopulationService
        self.state.axis_manager = AxisManager(self.state, parent=self)
        self.state.population_service = PopulationService(self.state)

        self._gate_controller = GateController(self.state, parent=self)
        self._gate_propagator = GatePropagator(self.state, parent=self)

        # ── Size policy ───────────────────────────────────────────────
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # ── Build UI ──────────────────────────────────────────────────
        self.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        self._setup_ui()
        
        # ── Event System Bridge ───────────────────────────────────────
        # Forward internal events to SDK CentralEventBus and trigger undo snapshots
        self.state.event_bus.subscribe(None, self._bridge_event)
        
        self.status_message.emit("Flow Cytometry workspace ready.")

    def _bridge_event(self, event: Event) -> None:
        """Forward internal events to the SDK's CentralEventBus."""
        # 1. Publish to SDK (string-topic, payload)
        topic = f"{self.plugin_id}.{event.type.value}"
        self.publish_event(topic, event.data)
        
        # 2. Trigger undo snapshots for structural changes
        structural_events = {
            EventType.GATE_CREATED,
            EventType.GATE_DELETED,
            EventType.GATE_MODIFIED,
            EventType.COMPENSATION_APPLIED,
            EventType.TRANSFORM_CHANGED,
        }
        if event.type in structural_events:
            self.push_state()
            self.state_changed.emit()

    # ── UI Construction ───────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Build the workspace layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar Tab Bar ───────────────────────────────────────────
        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setStyleSheet(
            f"QTabBar {{"
            f"  background: {Colors.BG_DARKEST};"
            f"  border: none;"
            f"}}"
            f"QTabBar::tab {{"
            f"  background: {Colors.BG_DARK};"
            f"  color: {Colors.FG_SECONDARY};"
            f"  padding: 10px 20px;"
            f"  border: none;"
            f"  border-bottom: 2px solid transparent;"
            f"  font-size: {Fonts.SIZE_SMALL}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  color: {Colors.ACCENT_PRIMARY};"
            f"  border-bottom: 2px solid {Colors.ACCENT_PRIMARY};"
            f"  background: {Colors.BG_DARKEST};"
            f"}}"
            f"QTabBar::tab:hover {{"
            f"  color: {Colors.FG_PRIMARY};"
            f"  background: {Colors.BG_MEDIUM};"
            f"}}"
        )

        tab_names = ["Workspace", "Compensation", "Gating", "Statistics", "Reports"]
        for name in tab_names:
            self._tab_bar.addTab(name)

        root.addWidget(self._tab_bar)

        # ── Ribbon Stack ──────────────────────────────────────────────
        self._ribbon_stack = QStackedWidget()
        self._ribbon_stack.setFixedHeight(64)
        self._ribbon_stack.setStyleSheet(
            f"background: {Colors.BG_DARK};"
            f" border-bottom: 1px solid {Colors.BORDER};"
        )

        self._workspace_ribbon = WorkspaceRibbon(self.state)
        self._compensation_ribbon = CompensationRibbon(self.state)
        self._gating_ribbon = GatingRibbon(self.state)
        self._statistics_ribbon = StatisticsRibbon(self.state)
        self._reports_ribbon = ReportsRibbon(self.state)

        self._ribbon_stack.addWidget(self._workspace_ribbon)
        self._ribbon_stack.addWidget(self._compensation_ribbon)
        self._ribbon_stack.addWidget(self._gating_ribbon)
        self._ribbon_stack.addWidget(self._statistics_ribbon)
        self._ribbon_stack.addWidget(self._reports_ribbon)

        self._tab_bar.currentChanged.connect(self._ribbon_stack.setCurrentIndex)
        root.addWidget(self._ribbon_stack)

        # ── Main Content Splitter ─────────────────────────────────────
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Left sidebar: groups + sample tree
        left_sidebar = QWidget()
        left_sidebar.setStyleSheet(
            f"background: {Colors.BG_DARKEST};"
        )
        left_layout = QVBoxLayout(left_sidebar)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._groups_panel = GroupsPanel(self.state)
        
        # Vertical Splitter for Samples & Gates
        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.BORDER};
                height: 2px;
            }}
        """)
        
        self._sample_list = SampleList(self.state)
        self._gate_hierarchy = GateHierarchy(self.state)
        
        self._left_splitter.addWidget(self._sample_list)
        self._left_splitter.addWidget(self._gate_hierarchy)
        self._left_splitter.setSizes([300, 300]) # Equal initial vertical split

        left_layout.addWidget(self._groups_panel)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        left_layout.addWidget(sep)

        left_layout.addWidget(self._left_splitter, stretch=1)

        # Center: graph canvas area
        self._graph_manager = GraphManager(self.state)

        # Right: properties panel
        self._properties_panel = PropertiesPanel(self.state, self._gate_controller)

        self._main_splitter.addWidget(left_sidebar)
        self._main_splitter.addWidget(self._graph_manager)
        self._main_splitter.addWidget(self._properties_panel)

        self._main_splitter.setSizes([260, 700, 280])
        self._main_splitter.setCollapsible(0, False)
        self._main_splitter.setCollapsible(1, False)
        self._main_splitter.setCollapsible(2, True)

        root.addWidget(self._main_splitter, stretch=1)

        # ── Wire internal signals ─────────────────────────────────────
        self._wire_signals()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        logger.info(f"FlowCytometryPanel resized: {self.width()}x{self.height()}")

    def _wire_signals(self) -> None:
        """Connect internal widget signals to each other and to the
        BioPro interface signals."""

        # ── Sample list → graph + properties ──────────────────────────
        self._sample_list.sample_double_clicked.connect(self._graph_manager.open_graph_with_context)
        self._sample_list.selection_changed.connect(
            lambda sid: self._properties_panel.show_sample_properties(sid, None)
        )
        self._sample_list.selection_changed.connect(self._on_sample_selection_changed)

        # ── Gate Hierarchy → graph + properties ───────────────────────
        self._gate_hierarchy.gate_double_clicked.connect(self._on_gate_double_clicked)
        self._gate_hierarchy.selection_changed.connect(self._on_gate_selection_changed)
        self._gate_hierarchy.gate_rename_requested.connect(self._gate_controller.rename_population)
        self._gate_hierarchy.gate_delete_requested.connect(self._gate_controller.remove_population)
        self._gate_hierarchy.split_requested.connect(self._gate_controller.split_population)
        self._gate_hierarchy.copy_gates_requested.connect(self._on_copy_gates)

        # ── Groups panel selection → filter sample list ───────────────
        self._groups_panel.group_selected.connect(self._sample_list.filter_by_group)

        # ── Any structural change → BioPro state_changed ──────────────
        self._gate_controller.gate_added.connect(self.state_changed)
        self._gate_controller.gate_removed.connect(self.state_changed)

        # ── Workspace ribbon: samples loaded → refresh tree + groups ──
        self._workspace_ribbon.samples_loaded.connect(self._on_samples_loaded)

        # ── Workspace ribbon: template loaded → refresh everything ────
        self._workspace_ribbon.template_load_requested.connect(
            self._refresh_all
        )

        # ── Compensation ribbon: matrix changed → refresh ─────────────
        self._compensation_ribbon.compensation_changed.connect(
            self._on_compensation_changed
        )

        # ── Gating ribbon → drawing tool selection ────────────────────
        self._gating_ribbon.tool_selected.connect(
            self._graph_manager.set_drawing_mode
        )
        self._gating_ribbon.delete_gate_requested.connect(
            self._on_delete_selected_gate
        )
        self._gating_ribbon.copy_gates_requested.connect(
            self._on_copy_gates_from_active
        )

        # ── Graph manager → gate controller ───────────────────────────
        self._graph_manager.gate_drawn.connect(self._on_gate_drawn)
        self._graph_manager.gate_selection_changed.connect(
            self._on_gate_selected_on_canvas
        )

        # ── Gate controller → UI updates ──────────────────────────────
        self._gate_controller.gate_added.connect(self._on_gate_added)
        self._gate_controller.gate_removed.connect(self._on_gate_removed)
        self._gate_controller.gate_stats_updated.connect(
            self._on_gate_stats_updated
        )
        self._gate_controller.all_stats_updated.connect(
            self._on_all_stats_updated
        )

        # ── Gate controller → propagator ──────────────────────────────
        self._gate_controller.propagation_requested.connect(
            self._gate_propagator.request_propagation
        )

        # ── Propagator → live UI updates ──────────────────────────────
        self._gate_propagator.sample_updated.connect(
            self._on_propagated_sample_updated
        )
        self._gate_propagator.propagation_complete.connect(
            self._on_propagation_complete
        )

    # ── Gate lifecycle callbacks ──────────────────────────────────────

    def _on_gate_drawn(self, gate, sample_id: str, parent_node_id) -> None:
        """Handle a gate drawn on the canvas → add to model."""
        # Note: gate.name is not used anymore as Identity is in the Node.
        # But we pass it as a suggestion 'name' to the controller.
        prefix = gate.__class__.__name__.replace("Gate", "")
        
        node_id = self._gate_controller.add_gate(
            gate, sample_id, name=None, parent_node_id=parent_node_id
        )
        if node_id:
            # Switch back to select mode after drawing
            self._gating_ribbon.reset_to_select()
            
            # AUTO-SELECT the new node so properties are shown immediately
            self._on_gate_selected(node_id)
            
            # Navigate into the new gate automatically so the user can keep gating
            # We defer this via QTimer (150ms) to ensure the double-click event loop finishes
            # processing first. Otherwise, macOS Native Window handler might misinterpret
            # the orphaned double-click event and force the app out of full screen.
            QTimer.singleShot(150, lambda: self._graph_manager.open_graph_for_sample(sample_id, node_id))
            
            self.status_message.emit(
                f"⟳ Propagating gate to other samples…"
            )

    def _on_gate_added(self, sample_id: str, node_id: str) -> None:
        """Gate added to model → refresh tree and canvas overlays."""
        self._refresh_gate_overlays(sample_id)
        self.state_changed.emit()
        
        # Ensure the new node is selected
        self._on_gate_selected(node_id)

    def _on_gate_removed(self, sample_id: str, node_id: str) -> None:
        """Gate removed → refresh tree and canvas."""
        self._refresh_gate_overlays(sample_id)
        self.state_changed.emit()

    def _on_gate_stats_updated(
        self, sample_id: str, node_id: str
    ) -> None:
        """Gate stats changed → update tree badges and properties."""
        self._gate_hierarchy.update_gate_stats(sample_id, node_id)
        # Update properties if this node is selected
        if node_id == self.state.current_gate_id:
            self._properties_panel.refresh()
        self._refresh_gate_overlays(sample_id)

    def _on_all_stats_updated(self, sample_id: str) -> None:
        """All stats for a sample updated → bulk refresh."""
        self._sample_list.update_all_sample_stats(sample_id)
        self._gate_hierarchy.update_all_sample_stats(sample_id)

    def _on_propagated_sample_updated(
        self, sample_id: str, stats: dict, new_tree: object
    ) -> None:
        """A single sample finished propagation → update its tree."""
        self._sample_list.update_all_sample_stats(sample_id)
        self._gate_hierarchy.update_all_sample_stats(sample_id)
        self._refresh_gate_overlays(sample_id)

    def _on_propagation_complete(self) -> None:
        """All samples finished propagation."""
        n = len(self.state.experiment.samples)
        self.status_message.emit(f"✓ Gate propagation complete ({n} samples updated).")
        # Refresh the properties panel and preview to show the new propagated gates/stats
        self._properties_panel.refresh()

    def _on_delete_selected_gate(self) -> None:
        """Delete the gate currently selected on the canvas."""
        graph = self._graph_manager.get_active_graph()
        if graph is None:
            return

        canvas = graph.canvas
        gate_id = canvas._selected_gate_id
        if gate_id is None:
            self.status_message.emit("No gate selected to delete.")
            return

        sample = self.state.experiment.samples.get(graph.sample_id)
        if sample:
            # Delete ALL populations sharing this physical gate
            nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
            for node in nodes:
                self._gate_controller.remove_population(graph.sample_id, node.node_id)
            self.status_message.emit("Gate and associated populations deleted.")

    def _on_copy_gates(self, sample_id: str) -> None:
        """Copy gates from a sample to all others in its group."""
        count = self._gate_controller.copy_gates_to_group(sample_id)
        self._gate_hierarchy.refresh()
        self.state_changed.emit()
        self.status_message.emit(
            f"Gates copied to {count} sample{'s' if count != 1 else ''}."
        )

    def _on_copy_gates_from_active(self) -> None:
        """Copy gates from the active graph's sample."""
        graph = self._graph_manager.get_active_graph()
        if graph:
            self._on_copy_gates(graph.sample_id)

    def _on_gate_selected_on_canvas(self, gate_id: str | None) -> None:
        """Gate clicked on canvas → update selection state."""
        graph = self._graph_manager.get_active_graph()
        if graph is None:
            return

        if gate_id:
            sample = self.state.experiment.samples.get(graph.sample_id)
            if sample:
                # Map gate_id back to a primary node_id
                nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
                if nodes:
                    self._on_gate_selected(nodes[0].node_id)
        else:
            self._on_gate_selected(None)

    def _on_sample_selection_changed(self, sample_id: str) -> None:
        """Sample selection changed in list."""
        self._gate_hierarchy.set_active_sample(sample_id)

    def _on_gate_selection_changed(self, node_id: str) -> None:
        """Gate selection changed in tree → update canvas and properties."""
        self._on_gate_selected(node_id)

    def _on_gate_double_clicked(self, node_id: str) -> None:
        """Gate double clicked → open new graph viewing this population."""
        sample_id = self._gate_hierarchy._active_sample_id
        if sample_id:
            self._graph_manager.open_graph_for_sample(sample_id, node_id)

    def _on_gate_selected(self, node_id: str | None) -> None:
        """Central selection handler for populations across all UI components."""
        self.state.current_gate_id = node_id
        
        # Sync tree selection
        if node_id:
            item = self._gate_hierarchy._gate_item_map.get(node_id)
            if item:
                # Block signals to avoid feedback loops
                self._gate_hierarchy._tree.blockSignals(True)
                self._gate_hierarchy._tree.setCurrentItem(item)
                self._gate_hierarchy._tree.blockSignals(False)
        else:
            self._gate_hierarchy._tree.clearSelection()

        # Update properties panel
        self._properties_panel.set_active_gate(node_id)
        
        # Highlight on canvas (canvas uses physical gate_id for artist storage)
        sample_id = self.state.current_sample_id
        if sample_id and node_id:
            sample = self.state.experiment.samples.get(sample_id)
            if sample:
                node = sample.gate_tree.find_node_by_id(node_id)
                if node and node.gate:
                    self._graph_manager.set_selected_gate(node.gate.gate_id)
        else:
            self._graph_manager.set_selected_gate(None)

    # ── Helper: refresh gate overlays on canvas ───────────────────────

    def _refresh_gate_overlays(self, sample_id: str) -> None:
        """Refresh gate overlays on all open graphs for a sample."""
        # Determine which parent gate each open graph is viewing
        for graph in self._graph_manager._graphs.values():
            if graph.sample_id != sample_id:
                continue

            gates, nodes = self._gate_controller.get_gates_for_display(
                sample_id, graph.node_id
            )
            graph.refresh_gates(gates, nodes)

    # ── Existing callbacks ────────────────────────────────────────────

    def _on_samples_loaded(self) -> None:
        """Callback when new FCS files are loaded via the ribbon."""
        self._groups_panel.refresh()
        self.state_changed.emit()
        self.status_message.emit(
            f"{len(self.state.experiment.samples)} samples loaded."
        )

    def _on_compensation_changed(self) -> None:
        """Callback when the compensation matrix changes."""
        self._sample_list.refresh()  # Refresh event counts after comp
        self._gate_hierarchy.refresh()
        self._properties_panel.refresh()
        self.state_changed.emit()
        src = self.state.compensation.source if self.state.compensation else "none"
        self.status_message.emit(f"Compensation updated (source: {src}).")

    def cleanup(self) -> None:
        """Called when the Flow Cytometry tab is closed."""
        logger.info("Cleaning up Flow Cytometry panel...")

        # 1. Base cleanup (nulls state)
        super().cleanup()

        # 2. Cleanup background tasks
        if self._gate_propagator:
            self._gate_propagator.cleanup()

        # 3. Cleanup UI components
        if self._graph_manager:
            self._graph_manager.cleanup()

        if self._sample_list:
            self._sample_list.cleanup()

    def shutdown(self) -> None:
        """Called when the application exists or plugin is uninstalled."""
        logger.info("Shutting down Flow Cytometry plugin...")
        # Clear any global caches if they existed
        pass

    # ── BioPro API: State Management ──────────────────────────────────

    def get_state(self) -> FlowState:
        """Package the workspace state for the SDK."""
        return self.state

    def set_state(self, state: FlowState) -> None:
        """Restore the workspace from an SDK state object."""
        if not state:
            return
        self.state = state
        self._refresh_all()

    def cleanup(self) -> None:
        """Resource cleanup on plugin close."""
        logger.info("Cleaning up Flow Cytometry workspace...")
        # Stop background timers/workers
        if hasattr(self, "_gate_propagator"):
            self._gate_propagator._timer.stop()
        
        # Unsubscribe from internal bus to avoid leaks if panel is recreated
        # (Though usually the whole state is recreated too)
        
        super().cleanup()

    def export_state(self) -> dict:
        """Package the workspace state for backward compatibility."""
        return {
            "flow_state": self.state.to_workflow_dict(),
            "active_tab": self._tab_bar.currentIndex(),
        }

    def load_state(self, state_dict: dict) -> None:
        """Restore the workspace for backward compatibility."""
        if not state_dict:
            return

        flow_data = state_dict.get("flow_state", {})
        self.state.from_workflow_dict(flow_data)

        tab_idx = state_dict.get("active_tab", 0)
        self._tab_bar.setCurrentIndex(tab_idx)

        # Refresh all UI widgets from the new state
        self._refresh_all()

    def export_workflow(self) -> dict:
        """Serialize the workspace for saving to disk."""
        return self.state.to_workflow_dict()

    def load_workflow(self, payload: dict) -> None:
        """Restore the workspace from a saved file."""
        if not payload:
            logger.warning("Empty payload received in load_workflow.")
            return

        logger.info("MainPanel: Loading workflow...")
        try:
            # Unwrap if the full BioPro envelope (metadata + payload) is passed
            actual_data = payload.get("payload", payload)
            
            self.state.from_workflow_dict(actual_data)
            
            # Defer refresh to ensure all state updates are processed
            QTimer.singleShot(50, self._refresh_all)
            
            self.status_message.emit("Workflow loaded successfully.")
            logger.info("MainPanel: Workflow load triggered.")
        except Exception as exc:
            logger.exception("Failed to load workflow")
            QMessageBox.critical(self, "Load Error", f"Failed to restore workflow:\n{exc}")

    # ── Internal helpers ──────────────────────────────────────────────

    def _refresh_all(self) -> None:
        """Rebuild all UI widgets from the current state."""
        logger.info("MainPanel: Performing full UI refresh...")
        
        # 1. Refresh data-driven widgets first
        self._groups_panel.refresh()
        self._sample_list.refresh()
        
        # 2. Sync the active sample context
        sid = self.state.current_sample_id
        
        # Fallback: if no sample is active, pick the first one from the loaded data
        if not sid and self.state.experiment.samples:
            sid = list(self.state.experiment.samples.keys())[0]
            self.state.current_sample_id = sid
            logger.info(f"MainPanel: No active sample in workflow, auto-selecting: {sid}")

        if sid:
            logger.info(f"MainPanel: Restoring active sample: {sid}")
            # Block signals to prevent redundant refresh calls during setup
            self._sample_list._tree.blockSignals(True)
            self._sample_list.select_sample(sid)
            self._sample_list._tree.blockSignals(False)
            
            self._gate_hierarchy.set_active_sample(sid)
        else:
            self._gate_hierarchy.refresh()
        
        # 3. Restore gate selection
        if self.state.current_gate_id:
            logger.info(f"MainPanel: Restoring gate selection: {self.state.current_gate_id}")
            self._on_gate_selected(self.state.current_gate_id)
            
        # 4. Final refresh for properties and graph
        self._properties_panel.refresh()
        self._graph_manager.refresh()
        
        logger.info("MainPanel: Full UI refresh complete.")

    def _sample_name(self, sample_id: str) -> str:
        """Get a sample's display name by ID."""
        sample = self.state.experiment.samples.get(sample_id)
        return sample.display_name if sample else sample_id