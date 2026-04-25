"""Population service for managing gate hierarchies and gated data.

Provides a clean interface for querying and manipulating the population tree
without direct coupling to Sample or Experiment objects where possible.
"""

from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING, List

if TYPE_CHECKING:
    from .state import FlowState
    from .gating import GateNode, Gate
    from .experiment import Sample
    import pandas as pd

logger = logging.getLogger(__name__)

class PopulationService:
    """Service for managing populations (GateNodes) across the experiment."""
    
    def __init__(self, state: FlowState):
        self._state = state

    def get_sample(self, sample_id: str) -> Optional[Sample]:
        """Look up a sample by ID."""
        return self._state.experiment.samples.get(sample_id)

    def get_root_node(self, sample_id: str) -> Optional[GateNode]:
        """Get the root of the gate tree for a sample."""
        sample = self.get_sample(sample_id)
        return sample.gate_tree if sample else None

    def find_node(self, sample_id: str, node_id: str) -> Optional[GateNode]:
        """Find a specific population node in a sample's tree."""
        root = self.get_root_node(sample_id)
        if not root:
            return None
        return root.find_node_by_id(node_id)

    def find_nodes_by_gate(self, sample_id: str, gate_id: str) -> List[GateNode]:
        """Find all nodes in a sample sharing a physical gate."""
        root = self.get_root_node(sample_id)
        if not root:
            return []
        return root.find_nodes_by_gate(gate_id)

    def get_gated_events(self, sample_id: str, node_id: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Get the events for a population, applying all parent gates."""
        sample = self.get_sample(sample_id)
        if not sample or not sample.has_data:
            return None
            
        events = sample.fcs_data.events
        if not node_id:
            return events
            
        node = self.find_node(sample_id, node_id)
        if not node:
            return events
            
        return node.apply_hierarchy(events)

    def add_population(self, sample_id: str, gate: Gate, parent_id: Optional[str] = None, name: Optional[str] = None) -> Optional[GateNode]:
        """Add a new population to a sample's gating hierarchy."""
        from .gating import QuadrantGate, RectangleGate
        sample = self.get_sample(sample_id)
        if not sample:
            return None
            
        parent = self.find_node(sample_id, parent_id) if parent_id else sample.gate_tree
        if not parent:
            logger.warning(f"Parent node {parent_id} not found in sample {sample_id}")
            return None
            
        # Standard gate
        if not isinstance(gate, QuadrantGate):
            return parent.add_child(gate, name=name)
            
        # Quadrant gate - special multi-population creation
        quad_node = parent.add_child(gate, name=name or "Quadrants")
        
        # Create 4 child rectangle gates for each quadrant
        xlim_hi = 1e9   # effectively unbounded
        xlim_lo = -1e9

        q_defs = [
            ("Q1 ++", gate.x_mid, xlim_hi,  gate.y_mid, xlim_hi),
            ("Q2 −+", xlim_lo,   gate.x_mid, gate.y_mid, xlim_hi),
            ("Q3 −−", xlim_lo,   gate.x_mid, xlim_lo,   gate.y_mid),
            ("Q4 +−", gate.x_mid, xlim_hi,  xlim_lo,   gate.y_mid),
        ]

        for q_name, xmin, xmax, ymin, ymax in q_defs:
            child_gate = RectangleGate(
                x_param=gate.x_param,
                y_param=gate.y_param,
                x_min=xmin,
                x_max=xmax,
                y_min=ymin,
                y_max=ymax,
                x_scale=gate.x_scale,
                y_scale=gate.y_scale,
            )
            quad_node.add_child(child_gate, name=q_name)
            
        return quad_node

    def remove_population(self, sample_id: str, node_id: str) -> bool:
        """Remove a population and all its children from a sample."""
        sample = self.get_sample(sample_id)
        if not sample:
            return False
            
        node = self.find_node(sample_id, node_id)
        if not node or node.parent is None: # Cannot remove root
            return False
            
        node.parent.children.remove(node)
        return True
