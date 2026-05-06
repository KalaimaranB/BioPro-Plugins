"""Service for high-level gating operations (cloning, propagation).
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from typing import TYPE_CHECKING, Optional

from ..gating import GateNode, gate_from_dict

if TYPE_CHECKING:
    from ..experiment import Sample, Experiment
    from ..gating import Gate

logger = get_logger(__name__, "flow_cytometry")

class GatingService:
    """Handles cross-sample gate tree operations.
    """

    @staticmethod
    def get_gates_for_display(
        sample: Sample, parent_node_id: Optional[str] = None
    ) -> tuple[list[Gate], list[GateNode]]:
        """Return the gates (and nodes) that should be drawn on the canvas."""
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

    @staticmethod
    def clone_gate_tree(source_root: GateNode, target: Sample) -> None:
        """Deep-clone a gate tree onto a target sample."""
        target.gate_tree = GateNode()
        GatingService._clone_children(source_root, target.gate_tree)

    @staticmethod
    def _clone_children(source: GateNode, target_parent: GateNode) -> None:
        """Recursively clone gate children."""
        for child in source.children:
            if child.gate is None:
                continue

            # Deep-copy the gate with a new ID to keep it independent
            cloned_gate_dict = child.gate.to_dict()
            cloned_gate_dict["gate_id"] = None  # force new ID
            cloned_gate = gate_from_dict(cloned_gate_dict)

            cloned_node = target_parent.add_child(cloned_gate, name=child.name)
            cloned_node.negated = child.negated
            GatingService._clone_children(child, cloned_node)

    @staticmethod
    def copy_gates_to_group(experiment: Experiment, source_sample_id: str) -> int:
        """Copy the gate tree from one sample to all others in its groups."""
        source = experiment.samples.get(source_sample_id)
        if source is None:
            return 0

        # Find all samples in the same groups
        targets: list[Sample] = []
        for group in experiment.groups.values():
            if source_sample_id in group.sample_ids:
                for sid in group.sample_ids:
                    if sid != source_sample_id:
                        s = experiment.samples.get(sid)
                        if s and s.fcs_data:
                            targets.append(s)

        # If not in any group, copy to all other samples
        if not targets:
            targets = [
                s for s in experiment.samples.values()
                if s.sample_id != source_sample_id and s.fcs_data
            ]

        count = 0
        for target in targets:
            GatingService.clone_gate_tree(source.gate_tree, target)
            count += 1

        return count
