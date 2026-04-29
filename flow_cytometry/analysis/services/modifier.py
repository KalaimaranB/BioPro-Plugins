"""Service for modifying gate parameters with validation."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..experiment import Experiment
    from ..gating import Gate


class GateModifier:
    """Service for modifying gate parameters with validation."""

    @staticmethod
    def modify_gate(experiment: Experiment, gate_id: str, sample_id: str, **kwargs: Any) -> bool:
        """Modify a gate's physical parameters.
        
        Args:
            experiment: The active experiment model.
            gate_id:    ID of the gate geometry to modify.
            sample_id:  ID of the sample owning the gate.
            **kwargs:   Parameters to update.
            
        Returns:
            True if modification was successful.
        """
        sample = experiment.samples.get(sample_id)
        if sample is None:
            return False

        # Find all nodes that share this gate geometry
        nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
        if not nodes:
            return False

        gate = nodes[0].gate
        
        # Identity-level changes (negated) only apply if we want them to,
        # but usually modify_gate is for geometry.
        node_kwargs: dict[str, Any] = {}
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
                
        return True
