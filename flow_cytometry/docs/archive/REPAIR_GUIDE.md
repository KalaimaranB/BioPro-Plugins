# Flow Cytometry Module - Detailed Repair Guide

**Date**: April 28, 2026  
**Purpose**: Step-by-step instructions for fixing identified issues

---

## Table of Contents

1. [Quick Fixes (Do First)](#quick-fixes-do-first)
2. [Code Decomposition](#code-decomposition)
3. [Service Extraction](#service-extraction)
4. [Testing Improvements](#testing-improvements)
5. [Documentation Standards](#documentation-standards)

---

## Quick Fixes (Do First)

### Fix 1: Remove Dead Code in transforms.py

**File**: `analysis/transforms.py`  
**Line**: ~89  
**Issue**: Commented-out dithering code

```python
# BEFORE (line 89):
#data_jitter += np.random.uniform(-0.5, 0.5, size=data_jitter.shape)
```

**Fix**: Remove the commented line entirely, or make it a feature:

```python
# AFTER:
# Dithering disabled by default. To enable for barcode removal:
# data_jitter += np.random.uniform(-0.5, 0.5, size=data_jitter.shape)
# Or use the enable_dithering parameter:
def biexponential_transform(
    data: np.ndarray,
    *,
    enable_dithering: bool = False,  # NEW PARAMETER
    top: float = 262144.0,
    width: float = 1.0,
    positive: float = 4.5,
    negative: float = 0.0,
) -> np.ndarray:
    # ... existing code ...
    if enable_dithering:
        data_jitter += np.random.uniform(-0.5, 0.5, size=data_jitter.shape)
```

---

### Fix 2: Add AxisScale Validation

**File**: `analysis/scaling.py`  
**Issue**: No validation on AxisScale parameters

```python
# AFTER (add to AxisScale class):
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AxisScale:
    # ... existing fields ...
    
    def __post_init__(self):
        """Validate scale parameters after initialization."""
        # Validate transform type
        valid_transforms = {'linear', 'log', 'biexponential'}
        if self.transform_type.value not in valid_transforms:
            raise ValueError(
                f"Invalid transform_type: {self.transform_type}. "
                f"Must be one of: {valid_transforms}"
            )
        
        # Validate range
        if self.min_val is not None and self.max_val is not None:
            if self.min_val >= self.max_val:
                raise ValueError(
                    f"min_val ({self.min_val}) must be less than max_val ({self.max_val})"
                )
        
        # Validate Logicle parameters
        if self.transform_type.value == 'biexponential':
            if self.logicle_t <= 0:
                raise ValueError(f"logicle_t must be positive, got {self.logicle_t}")
            if self.logicle_w < 0:
                raise ValueError(f"logicle_w must be non-negative, got {self.logicle_w}")
            if self.logicle_m <= 0:
                raise ValueError(f"logicle_m must be positive, got {self.logicle_m}")
            if self.logicle_a < 0:
                raise ValueError(f"logicle_a must be non-negative, got {self.logicle_a}")
        
        # Validate outlier percentile
        if not 0 <= self.outlier_percentile <= 50:
            raise ValueError(
                f"outlier_percentile must be between 0 and 50, got {self.outlier_percentile}"
            )
```

---

### Fix 3: Make Colormap Configurable in render_task.py

**File**: `analysis/render_task.py`  
**Line**: ~115  
**Issue**: Hardcoded colormap

```python
# BEFORE:
ax.scatter(
    x_plot, y_plot,
    c=c_plot,
    cmap=colormaps['jet'],
    vmin=0.0, vmax=1.0,
    s=0.8, alpha=0.8, edgecolors='none'
)
```

```python
# AFTER:
# Add to configure() method:
def configure(
    self,
    # ... existing parameters ...
    colormap: str = "jet",  # NEW PARAMETER
) -> None:
    # ... existing code ...
    self.config["colormap"] = colormap

# In run() method:
colormap_name = c.get("colormap", "jet")
ax.scatter(
    x_plot, y_plot,
    c=c_plot,
    cmap=colormaps[colormap_name],
    vmin=0.0, vmax=1.0,
    s=0.8, alpha=0.8, edgecolors='none'
)
```

---

### Fix 4: Extract Magic Numbers in rendering.py

**File**: `analysis/rendering.py`  
**Issue**: Magic numbers throughout

```python
# BEFORE (line 70):
nbins = int(min(1024, max(512, np.sqrt(n_points) * 2.0)) * quality_multiplier)

# AFTER:
# Add constants at top of file:
DEFAULT_NBINS_MIN = 512
DEFAULT_NBINS_MAX = 1024
NBINS_SCALING_FACTOR = 2.0

# In function:
nbins = int(
    min(DEFAULT_NBINS_MAX, max(DEFAULT_NBINS_MIN, np.sqrt(n_points) * NBINS_SCALING_FACTOR)) 
    * quality_multiplier
)
```

---

## Code Decomposition

### Decomposition 1: Split flow_canvas.py

**Current**: 1000+ lines in single file  
**Target**: ~300 lines per module

#### Step 1: Create canvas_data_layer.py

```python
# filepath: flow_cytometry/ui/graph/canvas_data_layer.py
"""Data layer rendering for FlowCanvas.

This module handles all data rendering (scatter, pseudocolor, histogram, etc.)
separately from gate overlays and UI interactions.
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Optional, Tuple

from matplotlib import colormaps
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from ...analysis.transforms import TransformType, apply_transform
from ...analysis.scaling import AxisScale, calculate_auto_range
from .renderers.factory import RenderStrategyFactory

logger = logging.getLogger(__name__)


class DataLayerRenderer:
    """Handles all data rendering for flow cytometry plots.
    
    This class is responsible for:
    - Rendering scatter plots, pseudocolor, histograms, etc.
    - Applying axis transforms
    - Calculating auto-ranges
    - Applying axis formatting
    
    It does NOT handle:
    - Gate overlays
    - Mouse/keyboard events
    - Selection state
    """
    
    def __init__(
        self,
        ax: Axes,
        x_param: str,
        y_param: str,
        x_scale: AxisScale,
        y_scale: AxisScale,
        display_mode: str,
    ):
        self._ax = ax
        self._x_param = x_param
        self._y_param = y_param
        self._x_scale = x_scale
        self._y_scale = y_scale
        self._display_mode = display_mode
        
    def render(
        self,
        data: pd.DataFrame,
        max_events: int = 100000,
        quality_multiplier: float = 1.0,
    ) -> None:
        """Render the data layer.
        
        Args:
            data: DataFrame with events
            max_events: Maximum events to render
            quality_multiplier: Resolution multiplier
        """
        # Implementation here
        pass
        
    def _calculate_axis_limits(
        self, 
        x_data: np.ndarray, 
        y_data: np.ndarray
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """Calculate axis limits from data.
        
        Returns:
            (x_limits, y_limits) tuples
        """
        # Implementation here
        pass
        
    def _apply_axis_formatting(self) -> None:
        """Apply FlowJo-style axis formatting."""
        # Implementation here
        pass
```

#### Step 2: Create canvas_gate_layer.py

```python
# filepath: flow_cytometry/ui/graph/canvas_gate_layer.py
"""Gate overlay rendering for FlowCanvas.

This module handles all gate overlay rendering separately from data rendering.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

from matplotlib.axes import Axes
from matplotlib.patches import Patch
from matplotlib.text import Text

from ...analysis.gating import Gate, GateNode

logger = logging.getLogger(__name__)


class GateLayerRenderer:
    """Handles gate overlay rendering.
    
    Responsibilities:
    - Drawing gate boundaries
    - Drawing gate labels
    - Drawing selection highlights
    - Hit testing for selection
    """
    
    def __init__(self, ax: Axes, coordinate_mapper: Any):
        self._ax = ax
        self._coordinate_mapper = coordinate_mapper
        self._gate_artists: List[Any] = []
        self._gate_patches: Dict[str, Patch] = {}
        
    def render_gates(
        self,
        gates: List[Gate],
        gate_nodes: List[GateNode],
        selected_gate_id: Optional[str] = None,
    ) -> None:
        """Render all gate overlays.
        
        Args:
            gates: List of gates to render
            gate_nodes: Corresponding gate nodes for labels/stats
            selected_gate_id: Currently selected gate
        """
        # Clear previous artists
        self._clear_artists()
        
        # Render each gate
        for i, gate in enumerate(gates):
            self._render_gate(gate, is_selected=(gate.gate_id == selected_gate_id))
            
    def _render_gate(self, gate: Gate, is_selected: bool) -> None:
        """Render a single gate overlay."""
        # Implementation here
        pass
        
    def _clear_artists(self) -> None:
        """Remove all gate artists from axes."""
        for artist in self._gate_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError):
                pass
        self._gate_artists.clear()
        self._gate_patches.clear()
        
    def hit_test(self, x: float, y: float) -> Optional[str]:
        """Test if point hits any gate.
        
        Args:
            x: X coordinate in data space
            y: Y coordinate in data space
            
        Returns:
            Gate ID if hit, None otherwise
        """
        # Implementation here
        pass
```

#### Step 3: Create canvas_event_handler.py

```python
# filepath: flow_cytometry/ui/graph/canvas_event_handler.py
"""Event handling for FlowCanvas.

This module handles all mouse and keyboard events separately from rendering.
"""

from __future__ import annotations

import logging
from typing import Optional, Callable, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CanvasEventHandler:
    """Handles mouse and keyboard events for FlowCanvas.
    
    Responsibilities:
    - Mouse press handling (start drawing, select gate)
    - Mouse motion handling (rubber-band preview)
    - Mouse release handling (finalize drawing)
    - Keyboard handling (cancel, shortcuts)
    - Double-click handling (close polygon)
    """
    
    def __init__(
        self,
        on_press: Callable[[float, float], None],
        on_motion: Callable[[float, float], None],
        on_release: Callable[[float, float], None],
        on_dblclick: Callable[[float, float], None],
    ):
        """Initialize event handler with callbacks.
        
        Args:
            on_press: Callback for mouse press (x, y)
            on_motion: Callback for mouse motion (x, y)
            on_release: Callback for mouse release (x, y)
            on_dblclick: Callback for double-click (x, y)
        """
        self._on_press = on_press
        self._on_motion = on_motion
        self._on_release = on_release
        self._on_dblclick = on_dblclick
        
    def handle_press(self, event) -> None:
        """Handle matplotlib press event."""
        if event.inaxes is not None and event.xdata is not None:
            self._on_press(event.xdata, event.ydata)
            
    def handle_motion(self, event) -> None:
        """Handle matplotlib motion event."""
        if event.inaxes is not None and event.xdata is not None:
            self._on_motion(event.xdata, event.ydata)
            
    def handle_release(self, event) -> None:
        """Handle matplotlib release event."""
        if event.inaxes is not None and event.xdata is not None:
            self._on_release(event.xdata, event.ydata)
            
    def handle_dblclick(self, event) -> None:
        """Handle matplotlib double-click event."""
        if event.inaxes is not None and event.xdata is not None:
            self._on_dblclick(event.xdata, event.ydata)
```

---

### Decomposition 2: Split gating.py

**Current**: 800+ lines in single file  
**Target**: ~150 lines per gate type

#### Step 1: Create analysis/gating/ directory structure

```
analysis/gating/
├── __init__.py
├── base.py
├── rectangle.py
├── polygon.py
├── ellipse.py
├── quadrant.py
├── range.py
├── gate_node.py
└── gate_factory.py
```

#### Step 2: Create base.py

```python
# filepath: flow_cytometry/analysis/gating/base.py
"""Abstract base class for all gate types.

This module defines the Gate interface that all gate implementations
must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any
import uuid

import numpy as np
import pandas as pd


@dataclass
class Gate(ABC):
    """Abstract base for all gate types.
    
    Every gate operates on two parameters (x_param, y_param) for 2-D gates
    or one parameter for 1-D gates (y_param is None).
    
    Attributes:
        gate_id: Unique identifier for serialization and cloning.
        name: Human-readable gate name.
        x_param: Channel/parameter name for X axis.
        y_param: Channel/parameter name for Y axis (None for 1-D).
        adaptive: If True, supports automatic repositioning.
    """
    
    x_param: str
    y_param: Optional[str] = None
    adaptive: bool = False
    gate_id: str = dataclass(default_factory=lambda: str(uuid.uuid4()))
    
    @abstractmethod
    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this gate.
        
        Args:
            events: DataFrame with columns matching x_param (and y_param if 2-D).
            
        Returns:
            Boolean array of shape (n_events,).
        """
        pass
    
    @abstractmethod
    def copy(self) -> Gate:
        """Create a deep copy of this gate."""
        pass
    
    def apply(self, events: pd.DataFrame) -> pd.DataFrame:
        """Return the subset of events inside this gate."""
        mask = self.contains(events)
        return events.loc[mask].copy()
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "type": type(self).__name__,
            "gate_id": self.gate_id,
            "x_param": self.x_param,
            "y_param": self.y_param,
            "adaptive": self.adaptive,
        }
```

#### Step 3: Create rectangle.py

```python
# filepath: flow_cytometry/analysis/gating/rectangle.py
"""Rectangle gate implementation.

A rectangular gate defined by min/max bounds on X and Y axes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .base import Gate
from ..scaling import AxisScale
from ..transforms import apply_transform, TransformType
from .._utils import ScaleFactory, TransformTypeResolver, BiexponentialParameters


@dataclass
class RectangleGate(Gate):
    """Rectangular (2-D) or range (1-D) gate defined by min/max bounds.
    
    Bounds are stored in raw data space. The contains() method projects
    both events and bounds into display space using axis scales before
    comparison.
    
    Attributes:
        x_min: X-axis lower bound in raw data space.
        x_max: X-axis upper bound in raw data space.
        y_min: Y-axis lower bound (ignored if y_param is None).
        y_max: Y-axis upper bound (ignored if y_param is None).
        x_scale: Axis scale for X parameter.
        y_scale: Axis scale for Y parameter.
    """
    
    x_min: float = -np.inf
    x_max: float = np.inf
    y_min: float = -np.inf
    y_max: float = np.inf
    x_scale: Optional[AxisScale] = None
    y_scale: Optional[AxisScale] = None
    
    def __post_init__(self):
        self.x_scale = ScaleFactory.parse(self.x_scale)
        self.y_scale = ScaleFactory.parse(self.y_scale)
    
    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this rectangle."""
        if self.x_param not in events.columns:
            return np.zeros(len(events), dtype=bool)
        
        x_raw = events[self.x_param].values
        bounds_x_raw = np.array([self.x_min, self.x_max])
        
        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        x_kwargs = (
            BiexponentialParameters(self.x_scale).to_dict()
            if x_type == TransformType.BIEXPONENTIAL else {}
        )
        
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
            y_kwargs = (
                BiexponentialParameters(self.y_scale).to_dict()
                if y_type == TransformType.BIEXPONENTIAL else {}
            )
            
            y_disp = apply_transform(y_raw, y_type, **y_kwargs)
            bounds_y_disp = apply_transform(bounds_y_raw, y_type, **y_kwargs)
            y_min_disp, y_max_disp = bounds_y_disp[0], bounds_y_disp[1]
            
            mask &= (y_disp >= y_min_disp) & (y_disp <= y_max_disp)
        
        return mask
    
    def copy(self) -> RectangleGate:
        return RectangleGate(
            self.x_param,
            self.y_param,
            x_min=self.x_min,
            x_max=self.x_max,
            y_min=self.y_min,
            y_max=self.y_max,
            adaptive=self.adaptive,
            gate_id=self.gate_id,
            x_scale=self.x_scale.copy() if self.x_scale else None,
            y_scale=self.y_scale.copy() if self.y_scale else None,
        )
```

#### Step 4: Update __init__.py

```python
# filepath: flow_cytometry/analysis/gating/__init__.py
"""Flow cytometry gating module.

Provides gate definitions, hierarchy management, and factory functions.

Gate Types:
    - RectangleGate: Rectangular region
    - PolygonGate: Arbitrary polygon
    - EllipseGate: Elliptical region
    - QuadrantGate: Four-way division
    - RangeGate: 1-D range/threshold

Example:
    >>> from flow_cytometry.analysis.gating import RectangleGate
    >>> gate = RectangleGate("FSC-A", "SSC-A", x_min=1000, x_max=50000)
    >>> mask = gate.contains(events_df)
    >>> gated_events = events_df[mask]
"""

from .base import Gate
from .rectangle import RectangleGate
from .polygon import PolygonGate
from .ellipse import EllipseGate
from .quadrant import QuadrantGate
from .range import RangeGate
from .gate_node import GateNode
from .gate_factory import gate_from_dict

__all__ = [
    "Gate",
    "RectangleGate",
    "PolygonGate",
    "EllipseGate",
    "QuadrantGate",
    "RangeGate",
    "GateNode",
    "gate_from_dict",
]
```

---

## Service Extraction

### Extract GateController Services

**Current**: GateController handles gate lifecycle, statistics, selection, naming  
**Target**: Separate services for each responsibility

#### Step 1: Create GateService

```python
# filepath: flow_cytometry/analysis/services/gate_service.py
"""Gate lifecycle service.

Handles CRUD operations for gates in the gating tree.
"""

from __future__ import annotations

import logging
from typing import Optional, List

from ..experiment import Experiment
from ..gating import Gate, GateNode

logger = logging.getLogger(__name__)


class GateService:
    """Service for gate CRUD operations.
    
    Responsibilities:
    - Adding gates to samples
    - Removing gates from samples
    - Modifying gate parameters
    - Finding gates by ID
    """
    
    def __init__(self, experiment: Experiment):
        self._experiment = experiment
    
    def add_gate(
        self,
        sample_id: str,
        gate: Gate,
        parent_node_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[GateNode]:
        """Add a gate to a sample's gating tree.
        
        Args:
            sample_id: Target sample ID
            gate: Gate to add
            parent_node_id: Parent node (None for root)
            name: Population name
            
        Returns:
            Created GateNode or None if failed
        """
        sample = self._experiment.samples.get(sample_id)
        if sample is None:
            logger.warning("Sample %s not found", sample_id)
            return None
            
        # Find parent node
        if parent_node_id is None:
            parent_node = sample.gate_tree
        else:
            parent_node = sample.gate_tree.find_node_by_id(parent_node_id)
            if parent_node is None:
                logger.warning("Parent node %s not found", parent_node_id)
                return None
        
        # Add child
        child = parent_node.add_child(gate, name)
        logger.info("Added gate %s to sample %s", gate.gate_id, sample_id)
        return child
    
    def remove_gate(self, sample_id: str, node_id: str) -> bool:
        """Remove a gate node from a sample."""
        # Implementation here
        pass
    
    def modify_gate(
        self,
        sample_id: str,
        gate_id: str,
        **kwargs,
    ) -> bool:
        """Modify gate parameters."""
        # Implementation here
        pass
    
    def find_gate(self, sample_id: str, gate_id: str) -> Optional[Gate]:
        """Find a gate by ID in a sample."""
        sample = self._experiment.samples.get(sample_id)
        if sample is None:
            return None
            
        nodes = sample.gate_tree.find_nodes_by_gate(gate_id)
        return nodes[0].gate if nodes else None
```

#### Step 2: Create StatsService

```python
# filepath: flow_cytometry/analysis/services/stats_service.py
"""Statistics computation service.

Handles population statistics calculation.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from ..experiment import Experiment, Sample
from ..gating import GateNode
from ..statistics import compute_population_stats, StatType

logger = logging.getLogger(__name__)


class StatsService:
    """Service for computing population statistics.
    
    Responsibilities:
    - Computing count, %parent, %total for populations
    - Caching statistics
    - Recomputing on gate changes
    """
    
    def __init__(self, experiment: Experiment):
        self._experiment = experiment
    
    def compute_stats(
        self,
        sample: Sample,
        node: GateNode,
    ) -> Dict[str, Any]:
        """Compute statistics for a population node.
        
        Args:
            sample: Sample containing the data
            node: GateNode to compute stats for
            
        Returns:
            Dictionary with count, pct_parent, pct_total
        """
        # Get parent events
        if node.parent is None:
            parent_events = sample.fcs_data.events
        else:
            parent_events = node.parent.apply_hierarchy(sample.fcs_data.events)
        
        # Get gated events
        gated_events = node.apply_hierarchy(sample.fcs_data.events)
        
        # Compute statistics
        stats = compute_population_stats(
            gated_events,
            parent_events,
            sample.fcs_data.events,
        )
        
        # Cache
        node.statistics = stats
        
        return stats
    
    def recompute_all_stats(self, sample_id: str) -> None:
        """Recompute statistics for all nodes in a sample."""
        sample = self._experiment.samples.get(sample_id)
        if sample is None:
            return
            
        self._recurse_stats(sample.gate_tree, sample)
    
    def _recurse_stats(self, node: GateNode, sample: Sample) -> None:
        """Recursively compute stats for all nodes."""
        if node.gate is not None:
            self.compute_stats(sample, node)
        for child in node.children:
            self._recurse_stats(child, sample)
```

#### Step 3: Refactor GateController

```python
# filepath: flow_cytometry/analysis/gate_controller.py (refactored)
"""Gate controller - coordinates gate operations.

This is now a thin facade that coordinates between services.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .state import FlowState
from .services.gate_service import GateService
from .services.stats_service import StatsService
from .services.naming import NamingService
from .gating import Gate

# ... existing signals ...


class GateController(QObject):
    """Facade coordinating gate operations.
    
    This class delegates to specialized services while maintaining
    the existing signal-based API for UI integration.
    """
    
    # ... existing signals ...
    
    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        
        # Initialize services
        self._gate_service = GateService(state.experiment)
        self._stats_service = StatsService(state.experiment)
        self._naming_service = NamingService()
    
    def add_gate(
        self,
        gate: Gate,
        sample_id: str,
        name: Optional[str] = None,
        parent_node_id: Optional[str] = None,
    ) -> Optional[str]:
        """Add a gate (delegates to GateService)."""
        # Generate name if not provided
        if not name:
            name = self._naming_service.generate_unique_name(
                self._state.experiment, sample_id
            )
        
        # Add gate
        node = self._gate_service.add_gate(
            sample_id, gate, parent_node_id, name
        )
        
        if node is None:
            return None
        
        # Compute stats
        self._stats_service.recompute_all_stats(sample_id)
        
        # Emit signals
        self.gate_added.emit(sample_id, node.node_id)
        
        return node.node_id
    
    # ... delegate other methods to services ...
```

---

## Testing Improvements

### Add Transform Tests

```python
# filepath: tests/unit/analysis/transforms/test_inverse.py
"""Tests for inverse transform functions.

These tests verify that applying a transform and then its inverse
returns approximately the original values.
"""

import pytest
import numpy as np
from flow_cytometry.analysis.transforms import (
    apply_transform,
    invert_transform,
    TransformType,
    linear_transform,
    log_transform,
    biexponential_transform,
    invert_linear_transform,
    invert_log_transform,
    invert_biexponential_transform,
)


class TestLinearInverse:
    """Tests for linear transform inverse."""
    
    def test_identity(self):
        """Linear transform is its own inverse."""
        data = np.array([0.0, 100.0, 1000.0, 10000.0])
        transformed = linear_transform(data)
        recovered = invert_linear_transform(transformed)
        np.testing.assert_allclose(data, recovered, rtol=1e-6)
    
    def test_negative_values(self):
        """Handles negative values correctly."""
        data = np.array([-1000.0, -100.0, 0.0, 100.0])
        transformed = linear_transform(data)
        recovered = invert_linear_transform(transformed)
        np.testing.assert_allclose(data, recovered, rtol=1e-6)
    
    def test_empty_array(self):
        """Handles empty array."""
        data = np.array([])
        transformed = linear_transform(data)
        recovered = invert_linear_transform(transformed)
        assert len(recovered) == 0


class TestLogInverse:
    """Tests for logarithmic transform inverse."""
    
    @pytest.fixture
    def sample_data(self):
        return np.array([1.0, 10.0, 100.0, 1000.0, 10000.0])
    
    def test_round_trip(self, sample_data):
        """Log transform should be invertible."""
        transformed = log_transform(sample_data)
        recovered = invert_log_transform(transformed)
        np.testing.assert_allclose(sample_data, recovered, rtol=0.01)
    
    def test_with_custom_decades(self):
        """Test with custom decades parameter."""
        data = np.array([1.0, 100.0, 10000.0])
        transformed = log_transform(data, decades=3.0)
        recovered = invert_log_transform(transformed, decades=3.0)
        np.testing.assert_allclose(data, recovered, rtol=0.01)
    
    def test_min_value_floor(self):
        """Test that min_value floor is handled."""
        data = np.array([0.5, 1.0, 10.0])  # Below default min_value=1.0
        transformed = log_transform(data, min_value=0.1)
        recovered = invert_log_transform(transformed, min_value=0.1)
        # Values below min_value are clamped, so check non-clamped values
        np.testing.assert_allclose(data[1:], recovered[1:], rtol=0.01)


class TestBiexponentialInverse:
    """Tests for biexponential (logicle) transform inverse."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate data spanning negative and positive ranges."""
        return np.array([-100, 0, 100, 1000, 10000, 100000])
    
    @pytest.fixture
    def default_params(self):
        return {"top": 262144.0, "width": 1.0, "positive": 4.5, "negative": 0.0}
    
    def test_round_trip(self, sample_data, default_params):
        """Biexponential should be invertible."""
        transformed = biexponential_transform(sample_data, **default_params)
        recovered = invert_biexponential_transform(transformed, **default_params)
        np.testing.assert_allclose(sample_data, recovered, rtol=0.02)
    
    def test_zero_is_identity(self, default_params):
        """Zero should map to zero."""
        result = biexponential_transform(np.array([0.0]), **default_params)
        recovered = invert_biexponential_transform(result, **default_params)
        assert recovered[0] == pytest.approx(0.0, abs=1e-6)
    
    @pytest.mark.parametrize("params", [
        {"top": 262144, "width": 1.0, "positive": 4.5, "negative": 0.0},
        {"top": 262144, "width": 0.5, "positive": 4.5, "negative": 1.0},
        {"top": 262144, "width": 1.0, "positive": 4.5, "negative": 0.5},
    ])
    def test_parameter_variations(self, sample_data, params):
        """Test different logicle parameter combinations."""
        transformed = biexponential_transform(sample_data, **params)
        recovered = invert_biexponential_transform(transformed, **params)
        np.testing.assert_allclose(sample_data, recovered, rtol=0.03)
    
    def test_with_negative_data(self):
        """Test with significant negative data (compensated)."""
        data = np.array([-5000, -1000, -100, 0, 100, 1000, 10000])
        params = {"top": 262144, "width": 1.0, "positive": 4.5, "negative": 1.0}
        transformed = biexponential_transform(data, **params)
        recovered = invert_biexponential_transform(transformed, **params)
        np.testing.assert_allclose(data, recovered, rtol=0.05)


class TestApplyTransformInverse:
    """Tests for the generic apply_transform/invert_transform functions."""
    
    def test_linear_round_trip(self):
        """Test generic apply_transform with linear."""
        data = np.array([0.0, 500.0, 1000.0])
        transformed = apply_transform(data, TransformType.LINEAR)
        recovered = invert_transform(transformed, TransformType.LINEAR)
        np.testing.assert_allclose(data, recovered, rtol=1e-6)
    
    def test_log_round_trip(self):
        """Test generic apply_transform with log."""
        data = np.array([1.0, 100.0, 10000.0])
        transformed = apply_transform(data, TransformType.LOG)
        recovered = invert_transform(transformed, TransformType.LOG)
        np.testing.assert_allclose(data, recovered, rtol=0.01)
    
    def test_biexponential_round_trip(self):
        """Test generic apply_transform with biexponential."""
        data = np.array([-100, 0, 100, 1000, 10000])
        transformed = apply_transform(
            data, 
            TransformType.BIEXPONENTIAL,
            top=262144, width=1.0, positive=4.5, negative=0.0
        )
        recovered = invert_transform(
            transformed,
            TransformType.BIEXPONENTIAL,
            top=262144, width=1.0, positive=4.5, negative=0.0
        )
        np.testing.assert_allclose(data, recovered, rtol=0.02)
    
    def test_invalid_transform_type(self):
        """Test that invalid transform type raises error."""
        data = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="Unknown transform"):
            apply_transform(data, "invalid_type")  # type: ignore
```

---

### Add Rendering Tests

```python
# filepath: tests/unit/analysis/rendering/test_pseudocolor.py
"""Tests for pseudocolor rendering."""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.rendering import compute_pseudocolor_points


class TestComputePseudocolorPoints:
    """Tests for the compute_pseudocolor_points function."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample 2D data with clusters."""
        np.random.seed(42)
        # Cluster 1: dense at (1000, 1000)
        c1_x = np.random.normal(1000, 100, 5000)
        c1_y = np.random.normal(1000, 100, 5000)
        # Cluster 2: sparse at (10000, 5000)
        c2_x = np.random.normal(10000, 500, 500)
        c2_y = np.random.normal(5000, 500, 500)
        # Combine
        x = np.concatenate([c1_x, c2_x])
        y = np.concatenate([c1_y, c2_y])
        return x, y
    
    def test_output_shapes(self, sample_data):
        """Test that output arrays have correct shapes."""
        x, y = sample_data
        x_out, y_out, c_out = compute_pseudocolor_points(
            x, y, 
            x_range=(0, 20000),
            y_range=(0, 15000),
        )
        assert len(x_out) == len(y_out) == len(c_out)
        assert len(x_out) == len(x)  # All points returned
    
    def test_color_range(self, sample_data):
        """Test that color values are in [0, 1]."""
        x, y = sample_data
        _, _, c = compute_pseudocolor_points(
            x, y,
            x_range=(0, 20000),
            y_range=(0, 15000),
        )
        assert np.all(c >= 0.0)
        assert np.all(c <= 1.0)
    
    def test_empty_data(self):
        """Test handling of empty data."""
        x = np.array([])
        y = np.array([])
        x_out, y_out, c_out = compute_pseudocolor_points(
            x, y,
            x_range=(0, 1000),
            y_range=(0, 1000),
        )
        assert len(x_out) == len(y_out) == len(c_out) == 0
    
    def test_nan_handling(self):
        """Test that NaN values are handled."""
        x = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        y = np.array([1.0, 2.0, 3.0, np.nan, 5.0])
        x_out, y_out, c_out = compute_pseudocolor_points(
            x, y,
            x_range=(0, 10),
            y_range=(0, 10),
        )
        # NaN values should be filtered out
        assert len(x_out) < len(x)
    
    def test_inverted_limits(self):
        """Test handling of inverted axis limits."""
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        # Inverted limits (max, min)
        x_out, y_out, c_out = compute_pseudocolor_points(
            x, y,
            x_range=(5.0, 1.0),  # Inverted!
            y_range=(5.0, 1.0),  # Inverted!
        )
        # Should still work (handled internally)
        assert len(x_out) == len(x)
    
    def test_quality_multiplier(self):
        """Test that quality_multiplier affects resolution."""
        x = np.random.uniform(0, 1000, 10000)
        y = np.random.uniform(0, 1000, 10000)
        
        # Low quality
        _, _, c_low = compute_pseudocolor_points(
            x, y,
            x_range=(0, 1000),
            y_range=(0, 1000),
            quality_multiplier=0.5,
        )
        
        # High quality
        _, _, c_high = compute_pseudocolor_points(
            x, y,
            x_range=(0, 1000),
            y_range=(0, 1000),
            quality_multiplier=2.0,
        )
        
        # Both should produce valid output
        assert len(c_low) == len(x)
        assert len(c_high) == len(x)
```

---

## Documentation Standards

### Docstring Template

```python
def function_name(
    param1: Type1,
    param2: Type2,
    *,
    option1: Type3 = default,
) -> ReturnType:
    """Short summary of what the function does.

    Longer description if needed. Can span multiple paragraphs.
    Explain the algorithm used, edge cases handled, and any
    important assumptions.

    Args:
        param1: Description of first parameter. Include constraints
            or valid ranges if applicable.
        param2: Description of second parameter.
        option1: Description of keyword-only option. (default: {default})

    Returns:
        Description of return value. Include type and any important
        characteristics.

    Raises:
        ValueError: When this condition occurs.
        TypeError: When that condition occurs.
        KeyError: When the key is not found.

    Example:
        Basic usage:
        >>> result = function_name(1, 2)
        >>> print(result)
        3

        With options:
        >>> result = function_name(1, 2, option1='custom')
        >>> print(result)
        'custom_result'

    Note:
        Any important notes about behavior, performance, or
        compatibility.
    """
```

### Class Docstring Template

```python
class ClassName:
    """Short summary of what the class does.

    Longer description if needed. Explain the purpose of the class,
    its main responsibilities, and how it fits into the larger
    architecture.

    Attributes:
        attr1: Description of first attribute.
        attr2: Description of second attribute.

    Example:
        Basic usage:
        >>> obj = ClassName(param1='value')
        >>> obj.do_something()
        'result'

        With custom configuration:
        >>> obj = ClassName(param1='value', option=True)
        >>> obj.do_something()
        'custom_result'
    """
```

---

## Migration Checklist

When making these changes, use this checklist:

### Before Starting
- [ ] All existing tests pass
- [ ] Code is under version control
- [ ] Backup created

### During Decomposition
- [ ] Import statements updated in all dependent files
- [ ] No circular dependencies introduced
- [ ] All existing tests still pass
- [ ] Type hints updated

### After Completion
- [ ] All tests pass
- [ ] No import errors
- [ ] Documentation updated
- [ ] No regression in functionality

---

*Document Version: 1.0*  
*Last Updated: April 28, 2026*