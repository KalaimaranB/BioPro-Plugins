"""Central gate controller — coordinates gate lifecycle and statistics.

Sits between the UI (canvas drawing, tree clicks) and the data model
(``GateNode`` tree, ``Sample``).  All gate mutations flow through here
so that statistics are recomputed consistently and cross-sample
propagation is triggered exactly once per user action.

Responsibilities:
    - Add / modify / delete gates in a sample's ``GateNode`` tree.
    - Compute population statistics (count, %parent, %total).
    - Emit signals so the UI can update incrementally.
    - Trigger the ``GatePropagator`` for cross-sample updates.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

import numpy as np
import pandas as pd

from .experiment import Sample
from .gating import (
    Gate,
    GateNode,
    QuadrantGate,
    RectangleGate,
    PolygonGate,
    EllipseGate,
    RangeGate,
    gate_from_dict,
)
from .statistics import compute_statistic, StatType
from .statistics_analysis import StatisticsAnalysis
from .state import FlowState
from biopro.sdk.core.events import CentralEventBus
from . import events
from biopro.core.task_scheduler import task_scheduler

from .services.naming import NamingService
from .services.splitter import PopulationSplitter
from .services.modifier import GateModifier
from .services.gating_service import GatingService
from .services.stats_service import StatsService

logger = get_logger(__name__, "flow_cytometry")


class GateController(QObject):
    """Central coordinator for gating operations across the workspace.

    Signals:
        gate_added(sample_id, gate_id):
            Emitted after a gate is successfully added to a sample.
        gate_removed(sample_id, gate_id):
            Emitted after a gate is removed from a sample.
        gate_stats_updated(sample_id, gate_id):
            Emitted after statistics are recomputed for a gate.
        all_stats_updated(sample_id):
            Emitted after all gates on a sample are recomputed.
        propagation_requested(gate_id, source_sample_id):
            Emitted to ask ``GatePropagator`` to re-apply the gate
            tree to other samples in the group.
    """

    gate_added = pyqtSignal(str, str)        # sample_id, node_id
    gate_removed = pyqtSignal(str, str)      # sample_id, node_id
    gate_renamed = pyqtSignal(str, str)      # sample_id, node_id
    gate_selected = pyqtSignal(str, str)     # sample_id, node_id (can be empty)
    gate_geometry_changed = pyqtSignal(str, str)  # sample_id, gate_id
    gate_stats_updated = pyqtSignal(str, str)  # sample_id, node_id
    all_stats_updated = pyqtSignal(str)      # sample_id
    propagation_requested = pyqtSignal(str, str)  # gate_id, source_sample_id

    def __init__(self, state: FlowState, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._state = state
        self.sync_stats = False

    # ── Gate lifecycle ────────────────────────────────────────────────

    def generate_unique_name(self, sample_id: str, prefix: str = "Gate") -> str:
        """Generate a name that doesn't collide with existing gates in this sample."""
        return NamingService.generate_unique_name(self._state.experiment, sample_id, prefix)

    def add_gate(
        self,
        gate: Gate,
        sample_id: str,
        name: Optional[str] = None,
        parent_node_id: Optional[str] = None,
    ) -> Optional[str]:
        """Add a gate to a sample's gating tree.

        Args:
            gate:            The gate to add.
            sample_id:       Target sample.
            name:            Population name (defaults to 'Gate N').
            parent_node_id:  ID of the parent node (None → attach to root).

        Returns:
            The node_id of the new population, or None.
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            logger.warning("Cannot add gate — sample %s not found.", sample_id)
            return None

        # Generate a name if not provided
        if not name:
            name = self.generate_unique_name(sample_id)

        # Use PopulationService to add the population
        child_node = self._state.population_service.add_population(
            sample_id, gate, parent_node_id, name
        )
        if child_node is None:
            return None

        # Compute initial statistics (recursively for Quadrants)
        # Recompute stats in the background
        self.recompute_all_stats(sample_id)

        self.gate_added.emit(sample_id, child_node.node_id)

        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_CREATED, {
            "sample_id": sample_id,
            "node_id": child_node.node_id,
            "gate_id": gate.gate_id,
            "name": child_node.name
        })

        # Request propagation to other samples
        self.propagation_requested.emit(gate.gate_id, sample_id)

        logger.info(
            "Population '%s' added to sample '%s' using %s.",
            child_node.name,
            sample.display_name,
            type(gate).__name__,
        )
        
        # Auto-select the new gate
        self.select_gate(sample_id, child_node.node_id)
        
        return child_node.node_id


    def modify_gate(
        self, gate_id: str, sample_id: str, **kwargs: Any
    ) -> bool:
        """Modify a gate's physical parameters and recompute ALL sharing populations."""
        success = GateModifier.modify_gate(self._state.experiment, gate_id, sample_id, **kwargs)
        if not success:
            return False

        # Recompute stats in the background for all affected nodes
        self.recompute_all_stats(sample_id)
        
        # Find all nodes that share this gate geometry to emit signals
        sample = self._state.experiment.samples.get(sample_id)
        if sample:
            nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
            for node in nodes:
                self.gate_stats_updated.emit(sample_id, node.node_id)

        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_MODIFIED, {
            "sample_id": sample_id,
            "gate_id": gate_id,
        })

        self.gate_geometry_changed.emit(sample_id, gate_id)
        self.propagation_requested.emit(gate_id, sample_id)
        return True

    def split_population(self, sample_id: str, node_id: str) -> Optional[str]:
        """Create a sibling population that is the inverse of the target node."""
        result = PopulationSplitter.split_population(self._state.experiment, sample_id, node_id)
        if result is None:
            return None

        new_node_id, new_name, gate_id = result

        # Compute stats in the background
        self.recompute_all_stats(sample_id)

        self.gate_added.emit(sample_id, new_node_id)
        self.gate_stats_updated.emit(sample_id, new_node_id)
        
        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_CREATED, {
            "sample_id": sample_id,
            "node_id": new_node_id,
            "gate_id": gate_id,
            "name": new_name,
            "is_split": True
        })
        
        logger.info("Split population created: '%s'", new_name)
        return new_node_id

    def remove_population(self, sample_id: str, node_id: str) -> bool:
        """Remove a population from a sample's tree."""
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return False
            
        node = self._state.population_service.find_node(sample_id, node_id)
        if node is None:
            return False
            
        old_gate_id = node.gate.gate_id if node.gate else None
        
        # Use PopulationService to remove it
        success = self._state.population_service.remove_population(sample_id, node_id)
        if not success:
            return False

        self.gate_removed.emit(sample_id, node_id)
        
        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_DELETED, {
            "sample_id": sample_id,
            "node_id": node_id,
            "gate_id": old_gate_id
        })
        logger.info("Population %s removed from sample %s.", node_id, sample_id)
        return True

    def rename_population(
        self, sample_id: str, node_id: str, new_name: str
    ) -> bool:
        """Rename a population.
        
        When a population is renamed, trigger propagation so the name
        change is reflected across all samples in the same group(s).
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return False

        node = sample.gate_tree.find_node_by_id(node_id)
        if node is None:
            return False

        node.name = new_name
        self.gate_renamed.emit(sample_id, node_id)
        self.gate_stats_updated.emit(sample_id, node_id)
        
        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_RENAMED, {
            "sample_id": sample_id,
            "node_id": node_id,
            "new_name": new_name
        })
        
        # Always trigger propagation on rename to ensure names persist across samples.
        # Find the root gate in this node's ancestry chain.
        gate_id = self._find_root_gate_id(node)
        if gate_id:
            self.propagation_requested.emit(gate_id, sample_id)
        return True

    def _find_root_gate_id(self, node: GateNode) -> Optional[str]:
        """Find the nearest gate in the node's ancestry chain."""
        current = node
        while current is not None:
            if current.gate is not None:
                return current.gate.gate_id
            current = current.parent
        return None

    # ── Selection management ──────────────────────────────────────────

    def select_gate(self, sample_id: str, node_id: Optional[str]) -> None:
        """Update the selected gate and notify listeners.
        
        Args:
            sample_id: The sample context.
            node_id:   The population node to select (None to deselect).
        """
        old_id = self._state.view.current_gate_id
        if old_id == node_id:
            return

        self._state.view.current_gate_id = node_id
        self.gate_selected.emit(sample_id, node_id or "")
        
        # Publish to SDK CentralEventBus
        CentralEventBus.publish(events.GATE_SELECTED, {
            "sample_id": sample_id,
            "node_id": node_id
        })
        
        logger.debug(f"Selection changed: {old_id} -> {node_id}")

    # ── Copy / propagate helpers ──────────────────────────────────────

    def copy_gates_to_group(self, source_sample_id: str) -> int:
        """Copy the gate tree from one sample to all others in its groups."""
        count = GatingService.copy_gates_to_group(self._state.experiment, source_sample_id)
        
        # We still need to trigger stats recomputation on the controller for all targets
        source = self._state.experiment.samples.get(source_sample_id)
        if source:
            for target_id in self._get_target_sample_ids(source_sample_id):
                self.recompute_all_stats(target_id)

        logger.info("Copied gate tree from source to %d samples.", count)
        return count

    def _get_target_sample_ids(self, source_sample_id: str) -> list[str]:
        """Helper to find target sample IDs for propagation."""
        experiment = self._state.experiment
        targets = set()
        for group in experiment.groups.values():
            if source_sample_id in group.sample_ids:
                for sid in group.sample_ids:
                    if sid != source_sample_id:
                        targets.add(sid)
        if not targets:
            for sid in experiment.samples:
                if sid != source_sample_id:
                    targets.add(sid)
        return list(targets)


    def recompute_all_stats(self, sample_id: str, sync: bool = False) -> None:
        """Submit a background task to recompute all gate statistics for a sample."""
        sync = sync or self.sync_stats
        
        if sync:
            analyzer = StatisticsAnalysis()
            analyzer.target_sample_id = sample_id
            results = analyzer.run(self._state)
            self._on_stats_finished(results)
            return

        task_id = StatsService.recompute_all_stats(
            self._state, sample_id, self._on_stats_finished
        )
        if task_id:
            logger.info(f"Submitted StatisticsAnalysis for sample {sample_id} (task_id: {task_id})")

    def _on_stats_finished(self, results: dict) -> None:
        """Apply background statistics results to the live state on the UI thread."""
        sample_id = results.get("sample_id")
        stats_map = results.get("stats", {})
        
        if not sample_id:
            return

        sample = self._state.experiment.samples.get(sample_id)
        if not sample:
            return

        # Apply results to nodes
        for node_id, stats in stats_map.items():
            node = sample.gate_tree.find_node_by_id(node_id)
            if node:
                node.statistics = stats
                # Notify individual gate subscribers
                self.gate_stats_updated.emit(sample_id, node_id)
                # Publish to global bus
                CentralEventBus.publish(events.STATS_COMPUTED, {
                    "sample_id": sample_id,
                    "node_id": node_id,
                    "stats": stats
                })

        # Notify that all stats for this sample are done
        self.all_stats_updated.emit(sample_id)
        logger.info(f"Applied background stats for sample {sample_id}")

    # Legacy synchronous stats methods removed in favor of background StatisticsAnalysis

    # ── Gate query helpers ────────────────────────────────────────────

    def get_gates_for_display(
        self, sample_id: str, parent_node_id: Optional[str] = None
    ) -> tuple[list[Gate], list[GateNode]]:
        """Return the gates (and nodes) that should be drawn on the canvas."""
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return ([], [])
        return GatingService.get_gates_for_display(sample, parent_node_id)