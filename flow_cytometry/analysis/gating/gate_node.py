"""GateNode class for hierarchical gating.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .base import Gate

logger = get_logger(__name__, "flow_cytometry")

@dataclass
class GateNode:
    """A node in the hierarchical gating tree.

    Each node wraps a :class:`Gate` and maintains parent-child
    relationships and population identity.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "All Events"
    negated: bool = False
    gate: Optional[Gate] = None
    children: list["GateNode"] = field(default_factory=list)
    parent: Optional["GateNode"] = field(default=None, repr=False)
    statistics: dict = field(default_factory=dict)

    @property
    def is_root(self) -> bool:
        return self.gate is None

    def add_child(self, gate: Gate, name: Optional[str] = None) -> "GateNode":
        """Create and attach a child gate node.
        
        Args:
            gate: The Gate instance to wrap in the child node.
            name: Optional human-readable name for the population. If None,
                  uses the first 8 characters of the gate_id.
                  
        Returns:
            GateNode: The newly created and attached child node.
        """
        node_name = name or (gate.gate_id[:8] if gate else "Unknown")
        child = GateNode(gate=gate, name=node_name, parent=self)
        self.children.append(child)
        return child

    def remove_child(self, node_id: str) -> bool:
        """Remove a child population by node ID.
        
        Args:
            node_id: The unique identifier of the child node to remove.
            
        Returns:
            bool: True if the child was found and removed, False otherwise.
        """
        for i, child in enumerate(self.children):
            if child.node_id == node_id:
                self.children.pop(i)
                return True
        return False

    def find_node_by_id(self, node_id: str) -> Optional["GateNode"]:
        """Recursively search for a population node by its node ID.
        
        Args:
            node_id: The unique identifier to search for in this node and its descendants.
            
        Returns:
            GateNode or None: The matching node if found, otherwise None.
        """
        if self.node_id == node_id:
            return self
        for child in self.children:
            found = child.find_node_by_id(node_id)
            if found:
                return found
        return None

    def find_nodes_by_gate(self, gate_id: str) -> list["GateNode"]:
        """Find all population nodes that use a specific gate instance.
        
        Args:
            gate_id: The unique identifier of the Gate instance to search for.
            
        Returns:
            list[GateNode]: A list of nodes that wrap the specified gate.
        """
        matches = []
        if self.gate and self.gate.gate_id == gate_id:
            matches.append(self)
        for child in self.children:
            matches.extend(child.find_nodes_by_gate(gate_id))
        return matches

    def apply_hierarchy(self, events: pd.DataFrame) -> pd.DataFrame:
        """Apply the chain of gates up to this node, respecting node-level negation.
        
        Args:
            events: The un-gated (root) DataFrame of events.
            
        Returns:
            pd.DataFrame: A subset of events that fall within this hierarchical path.
        """
        path: list[GateNode] = []
        node: Optional[GateNode] = self
        while node is not None:
            if node.gate is not None:
                path.append(node)
            node = node.parent
        path.reverse()

        if not path:
            return events

        full_mask = np.ones(len(events), dtype=bool)
        for step in path:
            step_mask = step.gate.contains(events)
            if step.negated:
                step_mask = ~step_mask
            full_mask &= step_mask
            
        return events.loc[full_mask].copy()

    def adapt_all(self, events: pd.DataFrame) -> None:
        """Recursively adapt all adaptive gates in the tree.
        
        Args:
            events: The un-gated (root) DataFrame of events to use for adaptation.
        """
        if self.gate and self.gate.adaptive:
            parent_events = events
            if self.parent:
                parent_events = self.parent.apply_hierarchy(events)
            self.gate.adapt(parent_events)
        
        subset = self.gate.apply(events) if self.gate else events
        for child in self.children:
            child.adapt_all(subset)

    @staticmethod
    def from_dict(data: dict, parent: Optional["GateNode"] = None) -> "GateNode":
        """Reconstruct a population tree from a serialized dictionary."""
        from .gate_factory import gate_from_dict
        
        gate_data = data.get("gate")
        gate = gate_from_dict(gate_data) if gate_data else None
        
        node = GateNode(
            gate=gate,
            name=data.get("name", "Unknown"),
            parent=parent,
            node_id=data.get("node_id"),
            negated=data.get("negated", False),
        )
        node.statistics = data.get("statistics", {})
        
        for child_data in data.get("children", []):
            node.children.append(GateNode.from_dict(child_data, parent=node))
            
        return node

    def to_dict(self) -> dict:
        """Serialize the full population tree."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "negated": self.negated,
            "gate": self.gate.to_dict() if self.gate else None,
            "children": [child.to_dict() for child in self.children],
        }
