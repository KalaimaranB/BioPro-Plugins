# Flow Cytometry: Responsibility Breakdown (Reference)

## FlowCanvas Method Organization

### Group 1: Rendering Pipeline (550 lines)
```python
def _render_data_layer(self) -> None:
    """Main data render - scatter/histogram selection"""
    # - Validates columns exist
    # - Applies transforms
    # - Calculates axis limits
    # - Dispatches to plot type renderer
    # - Caches bitmap
    
def _draw_dot(self, x, y) -> None:          # Scatter plot with subsampling
def _draw_pseudocolor(self, x, y) -> None:  # 2D histogram (hexbin)
def _draw_contour(self, x, y) -> None:      # Contour plot with KDE
def _draw_density(self, x, y) -> None:      # KDE density plot
def _draw_histogram(self, x) -> None:       # 1D histogram
def _draw_cdf(self, x) -> None:             # Cumulative distribution

def _apply_axis_formatting(self) -> None:
    """Apply biological decade ticks if transformed"""
    
def _build_bio_ticks(self, scale, is_biex) -> tuple[np.ndarray, list[str]]:
    """Build -10³, -10², 0, 10², 10³, ... labels"""
```

**Extraction Target**: `PlotRenderer` service

---

### Group 2: Gate Visualization (300 lines)
```python
def _render_gate_layer(self) -> None:
    """Orchestrate gate overlay redraw"""
    
def _redraw_gate_overlays(self) -> None:
    """Draw patches for each gate (Rectangle, Polygon, Ellipse, etc.)
    - Transforms gate coordinates to display space
    - Creates matplotlib patches
    - Stores patch→gate_id mapping for hit testing
    - Applies colors based on gate depth
    """
    
def _draw_node_labels(
    self,
    node: GateNode,
    patch_bounds: tuple,
    ax: Axes
) -> list[Artist]:
    """Position statistics labels inside/near gate patches"""
    
def _format_gate_label(self, gate, node) -> str:
    """Format: 'Population Name\n1,234 (5.6%)'"""
```

**Extraction Target**: `GateOverlayRenderer` service

---

### Group 3: Mouse Event Handling (300 lines) ⚠️
```python
def _on_press(self, event) -> None:
    """Mouse pressed:
    - If NONE mode: try_select_gate()
    - If POLYGON mode: add vertex, draw progress
    - If QUADRANT mode: finalize immediately
    - If RECTANGLE/ELLIPSE/RANGE: start drag
    """
    
def _on_motion(self, event) -> None:
    """Mouse moved during drag:
    - Remove old rubber band
    - Draw new preview based on mode
    - Call draw_idle()
    """
    
def _on_release(self, event) -> None:
    """Mouse released:
    - Check if drag distance > threshold (not accidental click)
    - Dispatch to _finalize_rectangle/polygon/ellipse/range
    """
    
def _on_dblclick(self, event) -> None:
    """Double-click: Close polygon if ≥3 vertices"""

def keyPressEvent(self, event) -> None:
    """Escape: Cancel drawing"""
```

**Extraction Target**: `DrawingStateMachine` service

---

### Group 4: Gate Drawing Finalization (200 lines) ⚠️ **BUSINESS LOGIC IN UI**
```python
def _finalize_rectangle(self, x0, y0, x1, y1) -> None:
    """Create RectangleGate from coordinates
    - Inverse transform to raw data space
    - Instantiate RectangleGate (BUSINESS LOGIC!)
    - Emit gate_created signal
    """
    
def _finalize_polygon(self) -> None:
    """Create PolygonGate from vertices"""
    
def _finalize_ellipse(self, x0, y0, x1, y1) -> None:
    """Create EllipseGate from bounding box"""
    
def _finalize_quadrant(self, x, y) -> None:
    """Create QuadrantGate at click position"""
    
def _finalize_range(self, x0, x1) -> None:
    """Create RangeGate from range"""

def _try_select_gate(self, x, y) -> None:
    """Hit test all patches, select if hit, emit gate_selected"""
```

**Extraction Targets**: 
- Gate creation → `GateFactory` (remove from UI)
- Selection logic → Keep in canvas but call from `DrawingStateMachine`

---

### Group 5: Coordinate Transformation (100 lines)
```python
def _transform_x(self, x: np.ndarray) -> np.ndarray:
    """Raw → Display: Apply AxisScale transform"""
    
def _transform_y(self, y: np.ndarray) -> np.ndarray:
    """Raw → Display: Apply AxisScale transform"""
    
def _inverse_transform_x(self, x: np.ndarray) -> np.ndarray:
    """Display → Raw: Invert AxisScale transform"""
    
def _inverse_transform_y(self, y: np.ndarray) -> np.ndarray:
    """Display → Raw: Invert AxisScale transform"""
```

**Extraction Target**: `CoordinateMapper` service

---

### Group 6: Drawing Progress UI (250 lines)
```python
def _draw_polygon_progress(self) -> None:
    """Show vertex markers, connecting lines, closing preview"""
    
def _clear_polygon_progress(self) -> None:
    """Remove all polygon progress artists"""
    
def _clear_rubber_band(self) -> None:
    """Remove rubber-band preview patch"""
    
def _show_instruction(self, mode: GateDrawingMode) -> None:
    """Show 'Click to add points' etc. overlay"""
    
def _update_instruction(self, text: str) -> None:
    """Update instruction text (e.g., 'Need 3 points')"""
    
def _hide_instruction(self) -> None:
    """Remove instruction overlay"""
    
def _cancel_drawing(self) -> None:
    """Abort any in-progress drawing, cleanup state"""
    
def _show_empty(self) -> None:
    """Display 'Load FCS data' placeholder"""
    
def _show_error(self, msg: str) -> None:
    """Display error message"""
    
def _show_loading(self) -> None:
    """Show spinning 'Rendering...' overlay"""
    
def _hide_loading(self) -> None:
    """Hide loading overlay"""
```

**Extraction Target**: Partial (instruction/progress helpers stay with canvas, but could be a `DrawingProgressManager`)

---

### Group 7: State & Configuration (150 lines)
```python
# Public API
def set_data(self, events: pd.DataFrame) -> None:
def set_axes(self, x_param, y_param, x_label, y_label) -> None:
def set_scales(self, x_scale, y_scale) -> None:
def set_display_mode(self, mode: DisplayMode) -> None:
def set_drawing_mode(self, mode: GateDrawingMode) -> None:
def set_gates(self, gates, gate_nodes) -> None:
def select_gate(self, gate_id) -> None:

# Batch operations
def begin_update(self) -> None:
    """Suppress redraws until end_update"""
    
def end_update(self) -> None:
    """Perform deferred redraw"""
    
def redraw(self) -> None:
    """Full render: data + gates"""
```

**Extraction Target**: Keep in canvas (remains the entry point)

---

### Group 8: Qt Lifecycle (100 lines)
```python
def __init__(self, parent=None) -> None:
    """Initialize figure, axes, state, signals, event connections"""
    
def mouseDoubleClickEvent(self, event) -> None:
    """Intercept double-click to prevent macOS fullscreen toggle"""
    
def showEvent(self, event) -> None:
    """Mark dirty if needed, redraw if pending"""
    
def resizeEvent(self, event) -> None:
    """Keep loading overlay centered"""
```

**Extraction Target**: Keep in canvas (Qt integration required)

---

## GateController Method Organization

### Group 1: Gate Lifecycle (250 lines)
```python
def generate_unique_name(self, sample_id, prefix) -> str:
    """Find next available name like 'Gate 1', 'Gate 2', etc."""
    # Walks gate tree collecting existing names
    
def add_gate(
    self,
    gate: Gate,
    sample_id: str,
    name: Optional[str] = None,
    parent_node_id: Optional[str] = None,
) -> Optional[str]:
    """Add gate to sample, compute stats, trigger propagation
    - Special handling for QuadrantGate (creates 4 children)
    - Emits: gate_added, gate_stats_updated, propagation_requested
    """
    
def modify_gate(self, gate_id, sample_id, **kwargs) -> bool:
    """Update gate geometry (e.g., x_min=100, negated=True)
    - Finds all nodes sharing this gate
    - Updates geometry
    - Recomputes subtree stats
    - Emits: gate_stats_updated, propagation_requested
    """
    
def remove_population(self, sample_id, node_id) -> bool:
    """Remove node from tree
    - Emits: gate_removed
    """
    
def rename_population(self, sample_id, node_id, new_name) -> bool:
    """Rename a node and propagate
    - Emits: gate_renamed, gate_stats_updated, propagation_requested
    """
    
def split_population(self, sample_id, node_id) -> Optional[str]:
    """Create Inside/Outside sibling populations from same gate
    - Emits: gate_added, gate_stats_updated
    """
```

**Status**: Well-designed, keep as is

---

### Group 2: Statistics Computation (150 lines) ⚠️
```python
def recompute_all_stats(self, sample_id: str) -> None:
    """Full sample recompute via tree walk"""
    
def _compute_node_stats(self, node: GateNode, sample: Sample) -> None:
    """Compute count/%parent/%total for single node
    - Gets parent events via hierarchy
    - Applies gate mask
    - Respects node.negated flag
    - Stores in node.statistics dict
    """
    
def _recompute_subtree(self, node: GateNode, sample: Sample) -> None:
    """Recompute node + all descendants"""
    
def _walk_and_compute(
    self,
    node: GateNode,
    parent_events: pd.DataFrame,
    parent_count: int,
    total_count: int,
) -> None:
    """Recursive tree traversal, compute each node's stats"""
```

**Extraction Target**: `StatisticsService` (enables parallelization)

---

### Group 3: Gate Tree Cloning (100 lines)
```python
def copy_gates_to_group(self, source_sample_id: str) -> int:
    """Copy gate tree from one sample to all in same group(s)
    - Finds target samples
    - Deep-clones tree
    - Recomputes stats on targets
    """
    
def _clone_gate_tree(self, source_root, target) -> None:
    """Clear target tree, recursively clone source"""
    
def _clone_children(self, source: GateNode, target_parent) -> None:
    """Clone source's children into target_parent"""
    
def _find_root_gate_id(self, node: GateNode) -> Optional[str]:
    """Find nearest ancestor gate (for propagation)"""
```

**Status**: Keep as is (specialized workflow)

---

### Group 4: Special Gate Handling (50 lines) ⚠️
```python
def _add_quadrant_gate(self, gate: QuadrantGate, sample, parent_node) -> str:
    """Create QuadrantGate + 4 RectangleGate children
    - Hard-coded Q1/Q2/Q3/Q4 names
    - Hard-coded bounds (±1e9)
    """
```

**Status**: Move to `QuadrantGate.create_hierarchy()` class method

---

### Group 5: Gate Query (60 lines)
```python
def get_gates_for_display(
    self,
    sample_id: str,
    parent_node_id: Optional[str] = None,
) -> tuple[list[Gate], list[GateNode]]:
    """Return direct children of parent for canvas rendering"""
```

**Status**: Keep as is (thin query layer)

---

## Signal Map Reference

### FlowCanvas Signals
| Signal | Current | Recommendation |
|--------|---------|-----------------|
| `gate_created(Gate)` | ✅ Used | Keep |
| `gate_selected(gate_id or None)` | ✅ Used | Keep |
| `region_selected(dict)` | ❌ Never emitted | Remove |
| `gate_modified(str)` | ❌ Never emitted | Remove |
| `point_clicked(float, float)` | ❌ Never emitted | Remove |

### GateController Signals
| Signal | Connected From | Recommendation |
|--------|----------------|-----------------|
| `gate_added(sample_id, node_id)` | `add_gate()`, `_add_quadrant_gate()` | Keep (listeners: GateHierarchy, StatsPanel) |
| `gate_removed(sample_id, node_id)` | `remove_population()` | Keep |
| `gate_renamed(sample_id, node_id)` | `rename_population()` | Keep |
| `gate_stats_updated(sample_id, node_id)` | `add_gate()`, `modify_gate()`, `split_population()`, `rename_population()` | Keep |
| `all_stats_updated(sample_id)` | `recompute_all_stats()` | ❓ Listener unclear - verify usage |
| `propagation_requested(gate_id, source_sample_id)` | Multiple (lifecycle methods) | Keep (goes to GatePropagator) |

---

## Extraction Priority

### Tier 1 (Critical - Unblocks testing)
1. **GateFactory** - Move gate creation out of UI layer
2. **CoordinateMapper** - Enable coordinate transform reuse

### Tier 2 (High - Major simplifications)
3. **PlotRenderer** - 350 lines from FlowCanvas
4. **GateOverlayRenderer** - 250 lines from FlowCanvas
5. **StatisticsService** - 150 lines from GateController

### Tier 3 (Medium - Improves maintainability)
6. **DrawingStateMachine** - 300 lines from FlowCanvas
7. **Signal segregation** - Remove unused signals, group by purpose

### Tier 4 (Low - Polish)
8. **DataValidator** - Catch state inconsistency early
9. **DrawingProgressManager** - UI state helpers
