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

import logging
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
from .state import FlowState
from .event_bus import Event, EventType

logger = logging.getLogger(__name__)


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
    gate_stats_updated = pyqtSignal(str, str)  # sample_id, node_id
    all_stats_updated = pyqtSignal(str)      # sample_id
    propagation_requested = pyqtSignal(str, str)  # gate_id, source_sample_id

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state

    # ── Gate lifecycle ────────────────────────────────────────────────

    def generate_unique_name(self, sample_id: str, prefix: str = "Gate") -> str:
        """Generate a name that doesn't collide with existing gates in this sample."""
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return f"{prefix} 1"

        existing_names = set()

        def _collect(node: GateNode):
            if not node.is_root:
                existing_names.add(node.name)
            for child in node.children:
                _collect(child)

        _collect(sample.gate_tree)

        counter = 1
        while True:
            candidate = f"{prefix} {counter}"
            if candidate not in existing_names:
                return candidate
            counter += 1

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
        def _stats_recursive(n: GateNode):
            self._compute_node_stats(n, sample)
            self.gate_stats_updated.emit(sample_id, n.node_id)
            for child in n.children:
                _stats_recursive(child)
        
        _stats_recursive(child_node)

        self.gate_added.emit(sample_id, child_node.node_id)

        # Publish to EventBus
        self._state.event_bus.publish(Event(
            type=EventType.GATE_CREATED,
            data={
                "sample_id": sample_id,
                "node_id": child_node.node_id,
                "gate_id": gate.gate_id,
                "name": child_node.name
            },
            source="GateController"
        ))

        # Request propagation to other samples
        self.propagation_requested.emit(gate.gate_id, sample_id)

        logger.info(
            "Population '%s' added to sample '%s' using %s.",
            child_node.name,
            sample.display_name,
            type(gate).__name__,
        )
        return child_node.node_id


    def modify_gate(
        self, gate_id: str, sample_id: str, **kwargs
    ) -> bool:
        """Modify a gate's physical parameters and recompute ALL sharing populations.

        Args:
            gate_id:   The physical gate geometry to modify.
            sample_id: The sample owning the gate.
            **kwargs:  Gate attributes to update (e.g., x_min=100, negated=True).
                       Note: 'negated' now targets the primary node if passed here,
                       for backward compatibility or direct access.
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return False

        # Find all nodes that share this gate geometry
        nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
        if not nodes:
            return False

        gate = nodes[0].gate
        
        # Identity-level changes (negated) only apply if we want them to,
        # but usually modify_gate is for geometry.
        # We'll support 'negated' here by applying it to ALL nodes sharing the gate
        # for now, but in future 'modify_population' will be preferred.
        node_kwargs = {}
        if "negated" in kwargs:
            node_kwargs["negated"] = kwargs.pop("negated")

        # Update geometry
        for key, value in kwargs.items():
            if hasattr(gate, key):
                setattr(gate, key, value)
        
        # Update identity for all linked nodes
        for node in nodes:
            for key, value in node_kwargs.items():
                setattr(node, key, value)
            
            # Recompute this gate and all descendants
            self._recompute_subtree(node, sample)
            self.gate_stats_updated.emit(sample_id, node.node_id)

        # Publish to EventBus
        self._state.event_bus.publish(Event(
            type=EventType.GATE_MODIFIED,
            data={
                "sample_id": sample_id,
                "gate_id": gate_id,
            },
            source="GateController"
        ))

        self.propagation_requested.emit(gate_id, sample_id)
        return True

    def split_population(self, sample_id: str, node_id: str) -> Optional[str]:
        """Create a sibling population that is the inverse of the target node.

        Allows a single gate to drive two populations (Inside/Outside).
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return None

        node = sample.gate_tree.find_node_by_id(node_id)
        if node is None or node.gate is None or node.parent is None:
            return None

        # Create sibling using the same gate instance
        new_name = f"{node.name} (Outside)" if not node.negated else f"{node.name} (Inside)"
        sibling = node.parent.add_child(node.gate, name=new_name)
        sibling.negated = not node.negated

        # Compute stats
        self._recompute_subtree(sibling, sample)

        self.gate_added.emit(sample_id, sibling.node_id)
        self.gate_stats_updated.emit(sample_id, sibling.node_id)
        
        # Publish to EventBus
        self._state.event_bus.publish(Event(
            type=EventType.GATE_CREATED,
            data={
                "sample_id": sample_id,
                "node_id": sibling.node_id,
                "gate_id": node.gate.gate_id,
                "name": sibling.name,
                "is_split": True
            },
            source="GateController"
        ))
        
        logger.info("Split population created: '%s' from '%s'", sibling.name, node.name)
        return sibling.node_id

    def remove_population(self, sample_id: str, node_id: str) -> bool:
        """Remove a population node from a sample's tree."""
        # Find the node first to get its gate_id for the event
        node = self._state.population_service.find_node(sample_id, node_id)
        if node is None:
            return False
            
        old_gate_id = node.gate.gate_id if node.gate else None
        
        # Use PopulationService to remove it
        success = self._state.population_service.remove_population(sample_id, node_id)
        if not success:
            return False

        self.gate_removed.emit(sample_id, node_id)
        
        # Publish to EventBus
        self._state.event_bus.publish(Event(
            type=EventType.GATE_DELETED,
            data={
                "sample_id": sample_id,
                "node_id": node_id,
                "gate_id": old_gate_id
            },
            source="GateController"
        ))
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
        
        # Publish to EventBus
        self._state.event_bus.publish(Event(
            type=EventType.GATE_RENAMED,
            data={
                "sample_id": sample_id,
                "node_id": node_id,
                "new_name": new_name
            },
            source="GateController"
        ))
        
        # Always trigger propagation on rename to ensure names persist across samples.
        # Find the root gate in this node's ancestry chain.
        gate_id = self._find_root_gate_id(node)
        if gate_id:
            self.propagation_requested.emit(gate_id, sample_id)
        return True

    def _find_root_gate_id(self, node: GateNode) -> Optional[str]:
        """Find the nearest gate in the node's ancestry chain.
        
        Traverses up from the given node to find the first ancestor
        that has a gate. This ensures we propagate the minimal affected
        subtree when a population name changes.
        
        Args:
            node: The GateNode to start from.
            
        Returns:
            The gate_id of the nearest ancestor gate, or None if no
            gate is found in the chain (only for root node).
        """
        current = node
        while current is not None:
            if current.gate is not None:
                return current.gate.gate_id
            current = current.parent
        return None

    # ── Copy / propagate helpers ──────────────────────────────────────

    def copy_gates_to_group(self, source_sample_id: str) -> int:
        """Copy the gate tree from one sample to all others in its groups.

        Args:
            source_sample_id: The sample whose gates to copy.

        Returns:
            Number of target samples that received the gate tree.
        """
        source = self._state.experiment.samples.get(source_sample_id)
        if source is None:
            return 0

        # Find all samples in the same groups
        targets: list[Sample] = []
        for group in self._state.experiment.groups.values():
            if source_sample_id in group.sample_ids:
                for sid in group.sample_ids:
                    if sid != source_sample_id:
                        s = self._state.experiment.samples.get(sid)
                        if s and s.fcs_data:
                            targets.append(s)

        # If not in any group, copy to all other samples
        if not targets:
            targets = [
                s for s in self._state.experiment.samples.values()
                if s.sample_id != source_sample_id and s.fcs_data
            ]

        count = 0
        for target in targets:
            self._clone_gate_tree(source.gate_tree, target)
            self.recompute_all_stats(target.sample_id)
            count += 1

        logger.info(
            "Copied gate tree from '%s' to %d samples.",
            source.display_name, count,
        )
        return count

    def _clone_gate_tree(
        self, source_root: GateNode, target: Sample
    ) -> None:
        """Deep-clone a gate tree onto a target sample."""
        # Clear existing gates on target
        target.gate_tree = GateNode()

        # Recursively clone
        self._clone_children(source_root, target.gate_tree)

    def _clone_children(
        self, source: GateNode, target_parent: GateNode
    ) -> None:
        """Recursively clone gate children."""
        import copy

        for child in source.children:
            if child.gate is None:
                continue

            # Deep-copy the gate with a new ID to keep it independent
            cloned_gate_dict = child.gate.to_dict()
            cloned_gate_dict["gate_id"] = None  # force new ID
            cloned_gate = gate_from_dict(cloned_gate_dict)

            cloned_node = target_parent.add_child(cloned_gate, name=child.name)
            cloned_node.negated = child.negated
            self._clone_children(child, cloned_node)

    # ── Statistics computation ────────────────────────────────────────

    def recompute_all_stats(self, sample_id: str) -> None:
        """Recompute all gate statistics for a sample.

        Args:
            sample_id: The sample to recompute.
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None or sample.fcs_data is None:
            return

        events = sample.fcs_data.events
        if events is None:
            return

        total_count = len(events)

        # Walk the tree depth-first
        self._walk_and_compute(
            sample.gate_tree, events, total_count, total_count
        )

        self.all_stats_updated.emit(sample_id)

    def _walk_and_compute(
        self,
        node: GateNode,
        parent_events: pd.DataFrame,
        parent_count: int,
        total_count: int,
    ) -> None:
        """Recursively compute stats for all nodes under ``node``."""
        for child in node.children:
            if child.gate is None:
                continue

            try:
                # Use hierarchy logic which respects node-level negation
                mask = child.gate.contains(parent_events)
                if child.negated:
                    mask = ~mask
                gated_events = parent_events.loc[mask].copy()
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "Gate '%s' failed: %s. Skipping.", child.name, exc
                )
                child.statistics = {"count": 0, "pct_parent": 0.0, "pct_total": 0.0}
                continue

            count = len(gated_events)
            pct_parent = (count / parent_count * 100.0) if parent_count > 0 else 0.0
            pct_total = (count / total_count * 100.0) if total_count > 0 else 0.0

            child.statistics = {
                "count": count,
                "pct_parent": round(pct_parent, 2),
                "pct_total": round(pct_total, 2),
            }

            # Recurse into child gates
            self._walk_and_compute(
                child, gated_events, count, total_count
            )

    def _compute_node_stats(
        self, node: GateNode, sample: Sample
    ) -> None:
        """Compute statistics for a single gate node.

        Uses the full hierarchy to get the parent subset first.
        """
        if sample.fcs_data is None or sample.fcs_data.events is None:
            return

        events = sample.fcs_data.events
        total_count = len(events)

        # Get the parent's subset
        if node.parent and node.parent.gate is not None:
            parent_events = node.parent.apply_hierarchy(events)
        else:
            parent_events = events

        parent_count = len(parent_events)

        try:
            mask = node.gate.contains(parent_events)
            if node.negated:
                mask = ~mask
            gated_events = parent_events.loc[mask].copy()
        except (KeyError, ValueError) as exc:
            logger.warning("Gate stats failed: %s", exc)
            node.statistics = {"count": 0, "pct_parent": 0.0, "pct_total": 0.0}
            return

        count = len(gated_events)
        pct_parent = (count / parent_count * 100.0) if parent_count > 0 else 0.0
        pct_total = (count / total_count * 100.0) if total_count > 0 else 0.0

        node.statistics = {
            "count": count,
            "pct_parent": round(pct_parent, 2),
            "pct_total": round(pct_total, 2),
        }

    def _recompute_subtree(
        self, node: GateNode, sample: Sample
    ) -> None:
        """Recompute stats for a node and all its descendants."""
        self._compute_node_stats(node, sample)

        if sample.fcs_data is None or sample.fcs_data.events is None:
            return

        events = sample.fcs_data.events
        total_count = len(events)
        gated = node.apply_hierarchy(events)

        self._walk_and_compute(node, gated, len(gated), total_count)

    # ── Gate query helpers ────────────────────────────────────────────

    def get_gates_for_display(
        self, sample_id: str, parent_node_id: Optional[str] = None
    ) -> tuple[list[Gate], list[GateNode]]:
        """Return the gates (and nodes) that should be drawn on the canvas.

        When viewing a population (parent_node_id), returns the direct
        child gates of that population.

        Args:
            sample_id:      The active sample.
            parent_node_id: The parent gate (None for root).

        Returns:
            Tuple of (gates, gate_nodes).
        """
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return ([], [])

        if parent_node_id:
            parent = sample.gate_tree.find_node_by_id(parent_node_id)
            if parent is None:
                return ([], [])
        else:
            parent = sample.gate_tree

        gates = []
        nodes = []
        for child in parent.children:
            if child.gate is not None:
                gates.append(child.gate)
                nodes.append(child)

        return (gates, nodes)