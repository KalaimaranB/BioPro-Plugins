"""Gate model — definitions, hierarchy, and adaptive repositioning.

Gates define regions in parameter space that classify events as inside
or outside a population.  Gates form a tree (``GateNode``) where child
gates operate on the subset of events that passed the parent gate.

Adaptive gate support:
    When ``adaptive=True`` on a ``Gate``, the gate positions can be
    auto-adjusted to a new dataset using kernel-density estimation
    while preserving the gate topology (shape, relative position).
    This is the key feature for reusable workflow templates — a
    scientist's gating strategy adapts to new samples automatically.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Gate base class ──────────────────────────────────────────────────────────


class Gate(ABC):
    """Abstract base for all gate types.

    Every gate operates on two parameters (x_param, y_param) for 2-D gates
    or one parameter for 1-D gates (y_param is None).

    Attributes:
        gate_id:   Unique identifier for serialization and cloning.
        name:      Human-readable gate name (e.g., ``"Lymphocytes"``).
        x_param:   Channel/parameter name for the X axis.
        y_param:   Channel/parameter name for the Y axis (None for 1-D).
        adaptive:  If True, the gate supports automatic repositioning
                   on new data via :meth:`adapt`.
    """

    def __init__(
        self,
        x_param: str,
        y_param: Optional[str] = None,
        *,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        self.gate_id = gate_id or str(uuid.uuid4())
        self.x_param = x_param
        self.y_param = y_param
        self.adaptive = adaptive

    @abstractmethod
    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this gate.

        Args:
            events: DataFrame with columns matching ``x_param``
                    (and ``y_param`` if 2-D).

        Returns:
            Boolean array of shape ``(n_events,)``.
        """

    def apply(self, events: pd.DataFrame) -> pd.DataFrame:
        """Return the subset of events inside this gate.

        Args:
            events: Full event DataFrame.

        Returns:
            Filtered DataFrame containing only gated events.
        """
        mask = self.contains(events)
        return events.loc[mask].copy()

    def adapt(self, events: pd.DataFrame) -> None:
        """Re-position the gate to fit a new dataset.

        Default implementation is a no-op.  Subclasses that support
        adaptive repositioning override this method with density-based
        optimization.

        Args:
            events: The new dataset to adapt to.
        """
        if self.adaptive:
            logger.debug(
                "Adaptive gate — adapt() not yet implemented for %s",
                type(self).__name__,
            )

    def to_dict(self) -> dict:
        """Serialize the gate to a JSON-compatible dictionary."""
        return {
            "type": type(self).__name__,
            "gate_id": self.gate_id,
            "x_param": self.x_param,
            "y_param": self.y_param,
            "adaptive": self.adaptive,
        }

    def __repr__(self) -> str:
        return f"<{type(self).__name__} on {self.x_param}/{self.y_param}>"


# ── Concrete gate types ──────────────────────────────────────────────────────


class RectangleGate(Gate):
    """Rectangular (2-D) or range (1-D) gate defined by min/max bounds.

    Attributes:
        x_min, x_max: X-axis bounds.
        y_min, y_max: Y-axis bounds (ignored if ``y_param`` is None).
    """

    def __init__(
        self,
        x_param: str,
        y_param: Optional[str] = None,
        *,
        x_min: float = -np.inf,
        x_max: float = np.inf,
        y_min: float = -np.inf,
        y_max: float = np.inf,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        x = events[self.x_param].values
        mask = (x >= self.x_min) & (x <= self.x_max)
        if self.y_param and self.y_param in events.columns:
            y = events[self.y_param].values
            mask &= (y >= self.y_min) & (y <= self.y_max)
        return mask

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(x_min=self.x_min, x_max=self.x_max,
                 y_min=self.y_min, y_max=self.y_max)
        return d


class PolygonGate(Gate):
    """Polygon gate defined by a list of (x, y) vertices.

    Uses matplotlib's ``Path.contains_points`` for hit-testing.

    Attributes:
        vertices: List of (x, y) tuples defining the polygon boundary.
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        *,
        vertices: Optional[list[tuple[float, float]]] = None,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.vertices = vertices or []

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        if len(self.vertices) < 3:
            return np.zeros(len(events), dtype=bool)

        from matplotlib.path import Path as MplPath

        x = events[self.x_param].values
        y = events[self.y_param].values
        points = np.column_stack([x, y])
        path = MplPath(self.vertices)
        return path.contains_points(points)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["vertices"] = [list(v) for v in self.vertices]
        return d


class EllipseGate(Gate):
    """Elliptical gate defined by center, semi-axes, and rotation.

    Attributes:
        center:   (cx, cy) center of the ellipse.
        width:    Semi-axis length along X (before rotation).
        height:   Semi-axis length along Y (before rotation).
        angle:    Rotation angle in degrees (counter-clockwise).
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        width: float = 1.0,
        height: float = 1.0,
        angle: float = 0.0,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.center = center
        self.width = width
        self.height = height
        self.angle = angle

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        x = events[self.x_param].values - self.center[0]
        y = events[self.y_param].values - self.center[1]

        theta = np.radians(self.angle)
        cos_t, sin_t = np.cos(theta), np.sin(theta)

        x_rot = cos_t * x + sin_t * y
        y_rot = -sin_t * x + cos_t * y

        return (x_rot / self.width) ** 2 + (y_rot / self.height) ** 2 <= 1.0

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(center=list(self.center), width=self.width,
                 height=self.height, angle=self.angle)
        return d


class QuadrantGate(Gate):
    """Quadrant gate — divides the plot into 4 regions at (x_mid, y_mid).

    Produces four sub-populations: Q1 (++), Q2 (-+), Q3 (--), Q4 (+-).

    Attributes:
        x_mid: X-axis division point.
        y_mid: Y-axis division point.
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        *,
        x_mid: float = 0.0,
        y_mid: float = 0.0,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.x_mid = x_mid
        self.y_mid = y_mid

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Returns True for all events (the quadrant gate itself holds all).

        Use :meth:`get_quadrant` to obtain a specific quadrant mask.
        """
        return np.ones(len(events), dtype=bool)

    def get_quadrant(
        self, events: pd.DataFrame, quadrant: str
    ) -> np.ndarray:
        """Return a boolean mask for a specific quadrant.

        Args:
            events:   Event DataFrame.
            quadrant: One of ``'Q1'`` (++), ``'Q2'`` (-+),
                      ``'Q3'`` (--), ``'Q4'`` (+-).

        Returns:
            Boolean mask array.
        """
        x = events[self.x_param].values
        y = events[self.y_param].values
        if quadrant == "Q1":
            return (x >= self.x_mid) & (y >= self.y_mid)
        elif quadrant == "Q2":
            return (x < self.x_mid) & (y >= self.y_mid)
        elif quadrant == "Q3":
            return (x < self.x_mid) & (y < self.y_mid)
        elif quadrant == "Q4":
            return (x >= self.x_mid) & (y < self.y_mid)
        else:
            raise ValueError(f"Invalid quadrant: {quadrant!r}")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(x_mid=self.x_mid, y_mid=self.y_mid)
        return d


class RangeGate(Gate):
    """1-D range gate (threshold or bisector) for histograms.

    Defines a single boundary on one parameter.

    Attributes:
        low:  Lower bound.
        high: Upper bound.
    """

    def __init__(
        self,
        x_param: str,
        *,
        low: float = -np.inf,
        high: float = np.inf,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            x_param, None,
            adaptive=adaptive, gate_id=gate_id
        )
        self.low = low
        self.high = high

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        x = events[self.x_param].values
        return (x >= self.low) & (x <= self.high)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(low=self.low, high=self.high)
        return d


# ── Gate tree ────────────────────────────────────────────────────────────────


@dataclass
class GateNode:
    """A node in the hierarchical gating tree.

    Each node wraps a :class:`Gate` and maintains parent-child
    relationships and population identity (naming, negation).
    The root node typically has ``gate=None`` and reflects all events.

    Attributes:
        node_id:    Unique identifier for this population node.
        name:       Display name for the population.
        negated:    If True, this node selects the events OUTSIDE its gate.
        gate:       The geometry definition (None for the root).
        children:   Child :class:`GateNode` instances.
        parent:     Back-reference to the parent node.
        statistics: Cached statistics for this population.
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
            gate: The gate to add as a child.
            name: Population name (defaults to gate ID if None).

        Returns:
            The newly created child :class:`GateNode`.
        """
        node_name = name or (gate.gate_id[:8] if gate else "Unknown")
        child = GateNode(gate=gate, name=node_name, parent=self)
        self.children.append(child)
        return child

    def remove_child(self, node_id: str) -> bool:
        """Remove a child population by node ID."""
        for i, child in enumerate(self.children):
            if child.node_id == node_id:
                self.children.pop(i)
                return True
        return False

    def find_node_by_id(self, node_id: str) -> Optional["GateNode"]:
        """Recursively search for a population node by its node ID."""
        if self.node_id == node_id:
            return self
        for child in self.children:
            found = child.find_node_by_id(node_id)
            if found:
                return found
        return None

    def find_nodes_by_gate(self, gate_id: str) -> list["GateNode"]:
        """Find all population nodes that use a specific gate instance."""
        matches = []
        if self.gate and self.gate.gate_id == gate_id:
            matches.append(self)
        for child in self.children:
            matches.extend(child.find_nodes_by_gate(gate_id))
        return matches

    def apply_hierarchy(self, events: pd.DataFrame) -> pd.DataFrame:
        """Apply the chain of gates up to this node, respecting node-level negation."""
        # Collect nodes from root → this node
        path: list[GateNode] = []
        node: Optional[GateNode] = self
        while node is not None:
            if node.gate is not None:
                path.append(node)
            node = node.parent
        path.reverse()

        subset = events
        for step in path:
            mask = step.gate.contains(subset)
            if step.negated:
                mask = ~mask
            subset = subset.loc[mask].copy()
        return subset

    def adapt_all(self, events: pd.DataFrame) -> None:
        """Recursively adapt all adaptive gates in the tree.

        Walks the tree depth-first, applying parent gates first so
        child gates see the correctly filtered population.

        Args:
            events: The full ungated event DataFrame.
        """
        if self.gate and self.gate.adaptive:
            # Get the parent's subset first
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
        
        # Reconstruct children
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
            "statistics": self.statistics,
            "children": [child.to_dict() for child in self.children],
        }


# ── Gate factory ─────────────────────────────────────────────────────────────


_GATE_REGISTRY: dict[str, type[Gate]] = {
    "RectangleGate": RectangleGate,
    "PolygonGate": PolygonGate,
    "EllipseGate": EllipseGate,
    "QuadrantGate": QuadrantGate,
    "RangeGate": RangeGate,
}


def gate_from_dict(data: dict) -> Gate:
    """Reconstruct a Gate instance from a serialized dictionary.

    Args:
        data: Dictionary produced by :meth:`Gate.to_dict`.

    Returns:
        A Gate subclass instance.

    Raises:
        ValueError: If the gate type is unknown.
    """
    gate_type = data.get("type", "")
    cls = _GATE_REGISTRY.get(gate_type)
    if cls is None:
        raise ValueError(f"Unknown gate type: {gate_type!r}")

    # Common kwargs
    kwargs = {
        "x_param": data["x_param"],
        "adaptive": data.get("adaptive", False),
        "gate_id": data.get("gate_id"),
    }
    if data.get("y_param"):
        kwargs["y_param"] = data["y_param"]

    # Type-specific kwargs
    if gate_type == "RectangleGate":
        kwargs.update(x_min=data.get("x_min", -np.inf),
                      x_max=data.get("x_max", np.inf),
                      y_min=data.get("y_min", -np.inf),
                      y_max=data.get("y_max", np.inf))
    elif gate_type == "PolygonGate":
        kwargs["vertices"] = [tuple(v) for v in data.get("vertices", [])]
    elif gate_type == "EllipseGate":
        kwargs.update(center=tuple(data.get("center", (0, 0))),
                      width=data.get("width", 1),
                      height=data.get("height", 1),
                      angle=data.get("angle", 0))
    elif gate_type == "QuadrantGate":
        kwargs.update(x_mid=data.get("x_mid", 0),
                      y_mid=data.get("y_mid", 0))
    elif gate_type == "RangeGate":
        kwargs.update(low=data.get("low", -np.inf),
                      high=data.get("high", np.inf))

    return cls(**kwargs)
