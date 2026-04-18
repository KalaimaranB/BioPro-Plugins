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
from .transforms import apply_transform, invert_transform, TransformType
from .scaling import AxisScale
from ._utils import (
    ScaleFactory,
    TransformTypeResolver,
    BiexponentialParameters,
    ScaleSerializer,
)
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

    Bounds are stored in **raw data space**. The ``contains()`` method
    projects both events and bounds into display space using the axis
    scales before comparison, ensuring the gate remains correct on all
    axis types (linear, log, biexponential).

    Attributes:
        x_min, x_max: X-axis bounds in raw data space.
        y_min, y_max: Y-axis bounds in raw data space (ignored if ``y_param`` is None).
        x_scale:      Axis scale for X parameter (drives transform type).
        y_scale:      Axis scale for Y parameter.
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
        x_scale=None,
        y_scale=None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.x_scale = ScaleFactory.parse(x_scale)
        self.y_scale = ScaleFactory.parse(y_scale)

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this rectangle.

        Both raw event values and raw-space bounds are projected into
        display space using the same forward transform before comparison.
        This keeps the gate boundary correct regardless of axis scale type.
        """
        x_raw = events[self.x_param].values
        bounds_x_raw = np.array([self.x_min, self.x_max])
        
        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})

        # Project X to display space
        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        bounds_x_disp = apply_transform(bounds_x_raw, x_type, **x_kwargs)
        x_min_disp, x_max_disp = bounds_x_disp[0], bounds_x_disp[1]

        mask = (x_disp >= x_min_disp) & (x_disp <= x_max_disp)

        # Apply Y constraint if present
        if self.y_param and self.y_param in events.columns:
            y_raw = events[self.y_param].values
            bounds_y_raw = np.array([self.y_min, self.y_max])

            y_type = TransformTypeResolver.resolve(
                getattr(self.y_scale, "transform_type", "linear")
            )
            y_kwargs = (BiexponentialParameters(self.y_scale).to_dict()
                        if y_type == TransformType.BIEXPONENTIAL else {})

            y_disp = apply_transform(y_raw, y_type, **y_kwargs)
            bounds_y_disp = apply_transform(bounds_y_raw, y_type, **y_kwargs)
            y_min_disp, y_max_disp = bounds_y_disp[0], bounds_y_disp[1]

            mask &= (y_disp >= y_min_disp) & (y_disp <= y_max_disp)

        return mask

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(x_min=self.x_min, x_max=self.x_max,
                 y_min=self.y_min, y_max=self.y_max)
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d


class PolygonGate(Gate):
    """Polygonal gate defined by an ordered list of vertices.

    Vertices are stored in **raw data space** (same coordinate frame as
    RectangleGate bounds).  ``contains()`` projects both event values and
    vertices into display space using the axis scale before the
    point-in-polygon test, so the gate boundary remains correct on log
    and biexponential axes.

    Attributes:
        vertices: Ordered ``[(x, y), ...]`` pairs in raw data space.
        x_scale:  Axis scale for the X parameter (drives transform type).
        y_scale:  Axis scale for the Y parameter.
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        vertices: list[tuple[float, float]],
        x_scale=None,
        y_scale=None,
        name: str = "Polygon Gate",
        adaptive: bool = False,
        gate_id: str = None,
        **kwargs,
    ):
        super().__init__(x_param, y_param, adaptive=adaptive, gate_id=gate_id)
        self.name = name
        self.vertices = vertices
        self.x_scale = ScaleFactory.parse(x_scale)
        self.y_scale = ScaleFactory.parse(y_scale)

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this polygon gate.

        Both the raw event values and the raw-space vertices are projected
        into display space using the same forward transform before the
        point-in-polygon test.  This keeps the gate shape visually correct
        regardless of the axis scale type.
        """
        from matplotlib.path import Path
        
        x_raw = events[self.x_param].values
        y_raw = events[self.y_param].values
        vx_raw = np.array([v[0] for v in self.vertices])
        vy_raw = np.array([v[1] for v in self.vertices])

        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        y_type = TransformTypeResolver.resolve(
            getattr(self.y_scale, "transform_type", "linear")
        )

        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})
        y_kwargs = (BiexponentialParameters(self.y_scale).to_dict()
                    if y_type == TransformType.BIEXPONENTIAL else {})

        # Project events into display space
        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        y_disp = apply_transform(y_raw, y_type, **y_kwargs)

        # Project raw-space vertices into the same display space
        vx_disp = apply_transform(vx_raw, x_type, **x_kwargs)
        vy_disp = apply_transform(vy_raw, y_type, **y_kwargs)

        points = np.column_stack((x_disp, y_disp))
        poly_path = Path(np.column_stack((vx_disp, vy_disp)))
        return poly_path.contains_points(points)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["vertices"] = [list(v) for v in self.vertices]
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d

class EllipseGate(Gate):
    """Elliptical gate defined by center, semi-axes, and rotation.

    Attributes:
        center:   (cx, cy) center of the ellipse in raw data space.
        width:    Semi-axis length along X (before rotation) in raw data space.
        height:   Semi-axis length along Y (before rotation) in raw data space.
        angle:    Rotation angle in degrees (counter-clockwise).
        x_scale:  Axis scale for X parameter (drives transform type).
        y_scale:  Axis scale for Y parameter.
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
        x_scale=None,
        y_scale=None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.center = center
        self.width = width
        self.height = height
        self.angle = angle
        self.x_scale = ScaleFactory.parse(x_scale)
        self.y_scale = ScaleFactory.parse(y_scale)

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this ellipse.

        Both raw event values and raw-space center/axes are projected
        into display space using the same forward transform before
        the ellipse containment test. This keeps the gate boundary
        correct regardless of axis scale type.
        """
        x_raw = events[self.x_param].values
        y_raw = events[self.y_param].values
        cx_raw = self.center[0]
        cy_raw = self.center[1]

        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        y_type = TransformTypeResolver.resolve(
            getattr(self.y_scale, "transform_type", "linear")
        )

        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})
        y_kwargs = (BiexponentialParameters(self.y_scale).to_dict()
                    if y_type == TransformType.BIEXPONENTIAL else {})

        # Project events and center to display space
        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        y_disp = apply_transform(y_raw, y_type, **y_kwargs)
        cx_disp = apply_transform(np.array([cx_raw]), x_type, **x_kwargs)[0]
        cy_disp = apply_transform(np.array([cy_raw]), y_type, **y_kwargs)[0]

        # Project axis endpoints to get semi-axes lengths in display space
        x_plus_w_disp = apply_transform(np.array([cx_raw + self.width]), x_type, **x_kwargs)[0]
        y_plus_h_disp = apply_transform(np.array([cy_raw + self.height]), y_type, **y_kwargs)[0]
        width_disp = abs(x_plus_w_disp - cx_disp)
        height_disp = abs(y_plus_h_disp - cy_disp)

        # Translate to center
        x_centered = x_disp - cx_disp
        y_centered = y_disp - cy_disp

        # Rotate
        theta = np.radians(self.angle)
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        x_rot = cos_t * x_centered + sin_t * y_centered
        y_rot = -sin_t * x_centered + cos_t * y_centered

        # Ellipse containment test
        return (x_rot / width_disp) ** 2 + (y_rot / height_disp) ** 2 <= 1.0

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(center=list(self.center), width=self.width,
                 height=self.height, angle=self.angle)
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d


class QuadrantGate(Gate):
    """Quadrant gate — divides the plot into 4 regions at (x_mid, y_mid).

    Produces four sub-populations: Q1 (++), Q2 (-+), Q3 (--), Q4 (+-). Both
    the mid-point and the containment test apply axis transforms to ensure
    correct behavior on all axis types.

    Attributes:
        x_mid:    X-axis division point in raw data space.
        y_mid:    Y-axis division point in raw data space.
        x_scale:  Axis scale for X parameter (drives transform type).
        y_scale:  Axis scale for Y parameter.
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
        x_scale=None,
        y_scale=None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.x_mid = x_mid
        self.y_mid = y_mid
        self.x_scale = ScaleFactory.parse(x_scale)
        self.y_scale = ScaleFactory.parse(y_scale)

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Returns True for all events (the quadrant gate itself holds all).

        Use :meth:`get_quadrant` to obtain a specific quadrant mask.
        """
        return np.ones(len(events), dtype=bool)

    def get_quadrant(
        self, events: pd.DataFrame, quadrant: str
    ) -> np.ndarray:
        """Return a boolean mask for a specific quadrant.

        Both the division point and raw event values are projected into
        display space using the same forward transform before comparison.

        Args:
            events:   Event DataFrame.
            quadrant: One of ``'Q1'`` (++), ``'Q2'`` (-+),
                      ``'Q3'`` (--), ``'Q4'`` (+-) or ``'Q1 ++'``, etc.

        Returns:
            Boolean mask array.
        """
        q = quadrant.split()[0].upper() if quadrant else quadrant

        x_raw = events[self.x_param].values
        y_raw = events[self.y_param].values
        mid_x_raw = np.array([self.x_mid])
        mid_y_raw = np.array([self.y_mid])

        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        y_type = TransformTypeResolver.resolve(
            getattr(self.y_scale, "transform_type", "linear")
        )

        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})
        y_kwargs = (BiexponentialParameters(self.y_scale).to_dict()
                    if y_type == TransformType.BIEXPONENTIAL else {})

        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        y_disp = apply_transform(y_raw, y_type, **y_kwargs)
        mid_x_disp = apply_transform(mid_x_raw, x_type, **x_kwargs)[0]
        mid_y_disp = apply_transform(mid_y_raw, y_type, **y_kwargs)[0]

        if q == "Q1":
            return (x_disp >= mid_x_disp) & (y_disp >= mid_y_disp)
        elif q == "Q2":
            return (x_disp < mid_x_disp) & (y_disp >= mid_y_disp)
        elif q == "Q3":
            return (x_disp < mid_x_disp) & (y_disp < mid_y_disp)
        elif q == "Q4":
            return (x_disp >= mid_x_disp) & (y_disp < mid_y_disp)
        else:
            raise ValueError(f"Invalid quadrant: {quadrant!r}")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(x_mid=self.x_mid, y_mid=self.y_mid)
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d


class RangeGate(Gate):
    """1-D range gate (threshold or bisector) for histograms.

    Defines a single boundary on one parameter. Bounds are stored in
    **raw data space** and transformed to display space for containment
    testing, ensuring correct results on all axis types.

    Attributes:
        low:      Lower bound in raw data space.
        high:     Upper bound in raw data space.
        x_scale:  Axis scale for the parameter (drives transform type).
    """

    def __init__(
        self,
        x_param: str,
        *,
        low: float = -np.inf,
        high: float = np.inf,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
        x_scale=None,
    ) -> None:
        super().__init__(
            x_param, None,
            adaptive=adaptive, gate_id=gate_id
        )
        self.low = low
        self.high = high
        self.x_scale = ScaleFactory.parse(x_scale)

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this range.

        Both raw event values and raw-space bounds are projected into
        display space using the same forward transform before comparison.
        This keeps the gate boundary correct regardless of axis scale type.
        """
        x_raw = events[self.x_param].values
        bounds_raw = np.array([self.low, self.high])

        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})

        # Project to display space
        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        bounds_disp = apply_transform(bounds_raw, x_type, **x_kwargs)
        low_disp, high_disp = bounds_disp[0], bounds_disp[1]

        return (x_disp >= low_disp) & (x_disp <= high_disp)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(low=self.low, high=self.high)
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
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
                      y_max=data.get("y_max", np.inf),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "PolygonGate":
        kwargs.update(vertices=[tuple(v) for v in data.get("vertices", [])],
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "EllipseGate":
        kwargs.update(center=tuple(data.get("center", (0, 0))),
                      width=data.get("width", 1),
                      height=data.get("height", 1),
                      angle=data.get("angle", 0),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "QuadrantGate":
        kwargs.update(x_mid=data.get("x_mid", 0),
                      y_mid=data.get("y_mid", 0),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "RangeGate":
        kwargs.update(low=data.get("low", -np.inf),
                      high=data.get("high", np.inf),
                      x_scale=data.get("x_scale"))

    return cls(**kwargs)