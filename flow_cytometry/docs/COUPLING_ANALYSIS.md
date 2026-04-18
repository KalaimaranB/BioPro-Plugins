# UI-Business Logic Coupling Analysis

## Current Signal Flow & Coupling

### 1. Gate Drawing & Creation Flow (TIGHT COUPLING)

```
User draws rectangle on canvas
    ↓
FlowCanvas._on_release()
    ↓
FlowCanvas._finalize_rectangle(x0, y0, x1, y1)
    ├─ Inverse transforms coordinates
    ├─ CREATES RectangleGate (⚠️ Business logic!)
    └─ gate_created.emit(gate)
    
    ↓
GraphWindow receives gate_created signal
    ├─ Calls gate_drawn.emit(gate, sample_id, parent_node_id)
    ↓
GraphManager._on_gate_drawn(gate, sample_id, parent_node_id)
    ├─ Gets or creates parent node
    ├─ Calls GateController.add_gate(gate, sample_id, parent_node_id)
    ↓
GateController.add_gate()
    ├─ Validates sample exists
    ├─ Generates unique name
    ├─ Adds GateNode to tree
    ├─ Computes stats via _compute_node_stats()
    ├─ Emits gate_added signal
    ├─ Emits propagation_requested signal
    ↓
GateController.gate_added signal
    ├─ Listener: GateHierarchy widget updates tree display
    ├─ Listener: StatsPanel refreshes statistics
    ↓
GateController.propagation_requested signal
    └─ Listener: GatePropagator copies gate to other samples
```

### 2. Gate Modification Flow

```
User clicks & drags gate handle (for editing) - NOT IMPLEMENTED YET
    ↓
FlowCanvas._on_motion()
    ├─ Detects gate is being edited
    ├─ Updates gate geometry
    └─ Would emit: gate_modified (UNUSED!)
    
Current workaround: Use GateController.modify_gate() directly
    ├─ GraphManager calls modify_gate() on double-click
    ├─ modify_gate() recomputes all sharing populations
    └─ Emits: gate_stats_updated, propagation_requested
```

### 3. Gate Selection Flow (MODERATE COUPLING)

```
User clicks on gate overlay
    ↓
FlowCanvas._on_press()
    ├─ _try_select_gate(x, y)
    ├─ Hit test all patches
    ├─ Update _selected_gate_id
    ├─ Re-render gate layer
    └─ gate_selected.emit(gate_id)
    
    ↓
GraphManager._on_gate_selection(gate_id)
    ├─ Highlights node in GateHierarchy
    ├─ Shows stats in StatsPanel
    └─ Calls canvas.select_gate(gate_id) to update rendering
```

### 4. Statistics Recomputation Flow

```
External trigger (e.g., sample changes, gating mode changed)
    ↓
GateController.recompute_all_stats(sample_id)
    ├─ Gets sample from state
    ├─ Walks tree via _walk_and_compute()
    ├─ Each node: applies gate mask, calculates %parent/%total
    ├─ Stores in node.statistics dict
    ├─ Emits: all_stats_updated (listener UNCLEAR)
    ↓
StatsPanel listener (if connected)
    └─ Refreshes display
```

---

## Tight Coupling Points (Detailed)

### 1. **Gate Creation in UI Layer** ⚠️ CRITICAL

**Location**: `FlowCanvas._finalize_rectangle/polygon/ellipse/quadrant/range()`

**Problem**:
```python
# WRONG - Business logic in UI layer
def _finalize_rectangle(self, x0, y0, x1, y1) -> None:
    rx0, rx1 = self._inverse_transform_x(np.array([min(x0, x1), max(x0, x1)]))
    ry0, ry1 = self._inverse_transform_y(np.array([min(y0, y1), max(y0, y1)]))
    
    # ⚠️ Gate instantiation - BUSINESS LOGIC
    gate = RectangleGate(
        x_param=self._x_param,
        y_param=self._y_param,
        x_min=rx0, x_max=rx1,
        y_min=ry0, y_max=ry1,
        x_scale=self._x_scale.copy(),
        y_scale=self._y_scale.copy(),
    )
    self.gate_created.emit(gate)
```

**Why It's Coupled**:
- UI layer depends on specific Gate subclass constructors
- Can't test gate drawing without importing gate classes
- Can't mock gates for unit testing canvas
- Can't change gate instantiation logic without touching canvas code

**Impact**:
- 0% unit testability of FlowCanvas
- Can't reuse drawing UI for other gate types
- Hard to add new gate types (must modify canvas)

**Solution**:
```python
# RIGHT - Delegate to factory
from .factories import GateFactory

def _finalize_rectangle(self, x0, y0, x1, y1) -> None:
    rx0, rx1 = self._inverse_transform_x(np.array([...]))
    ry0, ry1 = self._inverse_transform_y(np.array([...]))
    
    # Factory handles instantiation
    gate = GateFactory.create_rectangle(
        x_param=self._x_param,
        y_param=self._y_param,
        x0=rx0, x1=rx1, y0=ry0, y1=ry1,
        x_scale=self._x_scale,
        y_scale=self._y_scale,
    )
    self.gate_created.emit(gate)
```

---

### 2. **Coordinate Transformation Locked in Canvas**

**Location**: `FlowCanvas._transform_x/y(), _inverse_transform_x/y()`

**Problem**:
```python
# Transforms locked inside canvas
def _transform_x(self, x: np.ndarray) -> np.ndarray:
    x_kwargs = {
        "top": self._x_scale.logicle_t,
        "width": self._x_scale.logicle_w,
        ...
    } if self._x_scale.transform_type == TransformType.BIEXPONENTIAL else {}
    return apply_transform(x, self._x_scale.transform_type, **x_kwargs)

# Used by:
# - Rendering data
# - Drawing gates
# - Formatting axes
# - Editing gates (future)
```

**Why It's Coupled**:
- Same logic used in 4+ places in canvas
- Can't test transforms independently
- Can't reuse in other UIs (e.g., table view, export dialog)
- Hard to debug transform issues (tangled with rendering)

**Impact**:
- Code duplication if needed elsewhere
- Axis formatting hard to test
- New coordinate systems hard to add

**Solution**:
```python
class CoordinateMapper:
    def __init__(self, x_scale: AxisScale, y_scale: AxisScale):
        self.x_scale = x_scale
        self.y_scale = y_scale
    
    def transform_x(self, x: np.ndarray) -> np.ndarray:
        x_kwargs = {...}
        return apply_transform(x, self.x_scale.transform_type, **x_kwargs)
    
    def inverse_transform_x(self, x: np.ndarray) -> np.ndarray:
        x_kwargs = {...}
        return invert_transform(x, self.x_scale.transform_type, **x_kwargs)

# Used like:
mapper = CoordinateMapper(self._x_scale, self._y_scale)
display_x = mapper.transform_x(raw_x)
```

---

### 3. **Statistics Computation Tied to Lifecycle**

**Location**: `GateController.add_gate(), modify_gate(), _compute_node_stats()`

**Problem**:
```python
def add_gate(self, gate, sample_id, name, parent_node_id) -> Optional[str]:
    # ... validation ...
    child_node = parent_node.add_child(gate, name=name)
    
    # ⚠️ Stats computation happens inline
    self._compute_node_stats(child_node, sample)
    
    # Then emits signal
    self.gate_added.emit(sample_id, child_node.node_id)
    return child_node.node_id

def _compute_node_stats(self, node: GateNode, sample: Sample) -> None:
    if sample.fcs_data is None:
        return
    
    events = sample.fcs_data.events
    total_count = len(events)
    
    # ⚠️ Re-filters events on every call
    if node.parent and node.parent.gate is not None:
        parent_events = node.parent.apply_hierarchy(events)
    else:
        parent_events = events
    
    parent_count = len(parent_events)
    
    mask = node.gate.contains(parent_events)
    if node.negated:
        mask = ~mask
    gated_events = parent_events.loc[mask].copy()
    
    count = len(gated_events)
    # ... calculate percentages ...
    node.statistics = {...}
```

**Why It's Coupled**:
- Stats only computed when gate is added/modified
- Can't batch recompute multiple gates
- Can't parallelize stats (depends on sequential event re-filtering)
- Hard to test stats logic independently

**Impact**:
- Stats computation slow for large trees
- Can't update stats without gate modification
- Can't unit test stats logic

**Solution**:
```python
class StatisticsService:
    def compute_node_stats(
        self,
        node: GateNode,
        parent_events: pd.DataFrame,
        total_events: pd.DataFrame,
    ) -> Dict[str, float]:
        """Pure function: no side effects, no state access"""
        parent_count = len(parent_events)
        total_count = len(total_events)
        
        mask = node.gate.contains(parent_events)
        if node.negated:
            mask = ~mask
        gated_events = parent_events.loc[mask]
        
        count = len(gated_events)
        return {
            "count": count,
            "pct_parent": (count / parent_count * 100) if parent_count > 0 else 0,
            "pct_total": (count / total_count * 100) if total_count > 0 else 0,
        }

# GateController uses it:
def add_gate(self, ...):
    child_node = parent_node.add_child(gate, name=name)
    
    # Delegate stats computation
    stats = self._stats_service.compute_node_stats(
        child_node,
        parent_events,
        total_events,
    )
    child_node.statistics = stats
```

---

### 4. **Direct State Access (No Dependency Injection)**

**Location**: `GateController.__init__()` and throughout

**Problem**:
```python
class GateController(QObject):
    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state  # ⚠️ Holds reference to mutable state
    
    def add_gate(self, gate, sample_id, ...):
        # Direct access to nested objects
        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return
        
        # Further nesting
        parent_node = sample.gate_tree.find_node_by_id(parent_node_id)
        
        # Every method has this pattern
        events = sample.fcs_data.events
```

**Why It's Coupled**:
- Hard-coded path to data: `_state.experiment.samples[].gate_tree`
- Can't mock FlowState easily (must create entire structure)
- Can't test with different data sources
- Any change to FlowState structure breaks controller

**Impact**:
- Complex test setup
- Hard to support multiple state sources
- Hard to parallelize (everything goes through shared state)

**Solution**:
```python
class GateController:
    def __init__(self, sample_provider, stats_service, propagator):
        self._sample_provider = sample_provider  # Injected
        self._stats_service = stats_service
        self._propagator = propagator
    
    def add_gate(self, gate, sample_id, ...):
        sample = self._sample_provider.get_sample(sample_id)
        if sample is None:
            return
        
        # Same logic, but mockable
```

---

### 5. **No Validation Layer**

**Location**: `FlowCanvas.set_data(), set_axes(), set_scales()`

**Problem**:
```python
def set_data(self, events: pd.DataFrame) -> None:
    """⚠️ No validation!"""
    self._current_data = events
    self.redraw()

def set_axes(self, x_param, y_param, x_label, y_label) -> None:
    """⚠️ No validation!"""
    self._x_param = x_param
    self._y_param = y_param
    self.redraw()

# Result: If x_param not in events, silent failure during render
# _render_data_layer() catches KeyError, shows error message
# But by then, state is inconsistent
```

**Why It's Coupled**:
- State can become inconsistent (x_param specified but not in data)
- Errors detected late (during rendering, not assignment)
- Hard to debug (error message doesn't show what caused it)

**Impact**:
- Poor user experience (cryptic error after delay)
- Bugs hard to reproduce
- State machine gets confused

**Solution**:
```python
class CanvasDataValidator:
    @staticmethod
    def validate_data(df: pd.DataFrame) -> ValidationResult:
        if df is None or len(df) == 0:
            return ValidationResult(valid=False, error="No data")
        if not isinstance(df, pd.DataFrame):
            return ValidationResult(valid=False, error="Not a DataFrame")
        return ValidationResult(valid=True)
    
    @staticmethod
    def validate_axes(x_param, y_param, df):
        if x_param not in df.columns:
            return ValidationResult(valid=False, 
                                  error=f"X channel '{x_param}' not found")
        if y_param not in df.columns:
            return ValidationResult(valid=False,
                                  error=f"Y channel '{y_param}' not found")
        return ValidationResult(valid=True)

# Canvas uses it:
def set_axes(self, x_param, y_param, ...):
    result = CanvasDataValidator.validate_axes(x_param, y_param, self._current_data)
    if not result.valid:
        self._show_error(result.error)
        return False
    
    self._x_param = x_param
    self._y_param = y_param
    self.redraw()
    return True
```

---

### 6. **Gate Rendering Uses Matplotlib Patches Directly**

**Location**: `FlowCanvas._redraw_gate_overlays()`

**Problem**:
```python
def _redraw_gate_overlays(self) -> None:
    for gate_id, gate in zip(self._active_gates, ...):
        if isinstance(gate, RectangleGate):
            patch = MplRectangle((gate.x_min, gate.y_min), ...)
        elif isinstance(gate, PolygonGate):
            patch = MplPolygon(gate.vertices, ...)
        elif isinstance(gate, EllipseGate):
            patch = MplEllipse((gate.center, gate.width, gate.height), ...)
        
        self._ax.add_patch(patch)  # ⚠️ Matplotlib specific
```

**Why It's Coupled**:
- Can't render gates in non-matplotlib contexts
- Can't export gates to web/OpenGL/etc.
- Hard to test (matplotlib patches complex to mock)
- Gate type logic tied to matplotlib imports

**Impact**:
- No multi-backend support
- Can't unit test gate rendering
- Export/reporting hard to add

**Solution**:
```python
class GateOverlayRenderer:
    def render_gate(
        self,
        gate: Gate,
        selected: bool,
        ax: Axes,  # Injected dependency
    ) -> List[Artist]:
        """Render a gate on given axes, return artists"""
        artists = []
        
        if isinstance(gate, RectangleGate):
            patch = MplRectangle(...)
            ax.add_patch(patch)
            artists.append(patch)
        elif isinstance(gate, PolygonGate):
            patch = MplPolygon(...)
            ax.add_patch(patch)
            artists.append(patch)
        
        return artists

# Canvas uses it:
renderer = GateOverlayRenderer()
for gate in self._active_gates:
    artists = renderer.render_gate(gate, selected=..., ax=self._ax)
    self._gate_artists.extend(artists)
```

---

### 7. **Hard-Coded Gate Type Logic (Quadrant)**

**Location**: `GateController._add_quadrant_gate()`

**Problem**:
```python
def _add_quadrant_gate(self, gate: QuadrantGate, sample, parent_node):
    """⚠️ Hard-coded quadrant logic"""
    quad_node = parent_node.add_child(gate, name="Quadrants")
    
    # Hard-coded magic bounds
    xlim_hi = 1e9
    xlim_lo = -1e9
    
    # Hard-coded quadrant definitions
    q_defs = [
        ("Q1 ++", gate.x_mid, xlim_hi, gate.y_mid, xlim_hi),
        ("Q2 −+", xlim_lo, gate.x_mid, gate.y_mid, xlim_hi),
        ("Q3 −−", xlim_lo, gate.x_mid, xlim_lo, gate.y_mid),
        ("Q4 +−", gate.x_mid, xlim_hi, xlim_lo, gate.y_mid),
    ]
    
    # Creates child gates with hard-coded logic
    for name, xmin, xmax, ymin, ymax in q_defs:
        child_gate = RectangleGate(...)
        child_node = quad_node.add_child(child_gate, name=name)
```

**Why It's Coupled**:
- Gate-specific logic in controller (should be in gate class)
- Magic bounds `±1e9` not configurable
- Hard-coded names "Q1 ++", "Q2 −+" not internationalized
- Can't test quadrant logic independently

**Impact**:
- Can't add new gate types without modifying controller
- Quadrant gate can't be tested separately
- Hard-coded values brittle (breaks with different transforms)

**Solution**:
```python
class QuadrantGate(Gate):
    def create_hierarchy(self) -> Dict[str, Gate]:
        """Factory method: return child gates"""
        return {
            "Q1 ++": RectangleGate(..., x_min=self.x_mid, ...),
            "Q2 −+": RectangleGate(..., x_max=self.x_mid, ...),
            "Q3 −−": RectangleGate(..., x_max=self.x_mid, y_max=self.y_mid),
            "Q4 +−": RectangleGate(..., x_min=self.x_mid, y_max=self.y_mid),
        }

# GateController calls it:
def _add_quadrant_gate(self, gate: QuadrantGate, sample, parent_node):
    quad_node = parent_node.add_child(gate, name="Quadrants")
    
    for name, child_gate in gate.create_hierarchy().items():
        child_node = quad_node.add_child(child_gate, name=name)
        self._compute_node_stats(child_node, sample)
```

---

## Summary: Coupling Score

| Coupling | Severity | Detangling Effort |
|----------|----------|-----------------|
| Gate creation in UI | 🔴 CRITICAL | Medium (1-2h) |
| Transforms locked in canvas | 🔴 CRITICAL | Low (1h) |
| Stats tied to lifecycle | 🟠 HIGH | Medium (2-3h) |
| No validation layer | 🟠 HIGH | Low (1h) |
| Direct state access | 🟠 HIGH | Medium (2-3h) |
| Hard-coded quadrant logic | 🟡 MEDIUM | Low (30m) |
| matplotlib patches direct use | 🟡 MEDIUM | Medium (2-3h) |
| **Total Impact** | **6 CRITICAL** | **~10-15h** |

---

## Recommended Decoupling Order

1. **Day 1**: GateFactory + CoordinateMapper (2-3h) → Unblocks testing
2. **Day 2**: PlotRenderer + GateOverlayRenderer (6-8h) → 60% of FlowCanvas extracted
3. **Day 3**: StatisticsService (2-3h) → Enables parallelization
4. **Day 4**: DrawingStateMachine (3-4h) → Final extraction
5. **Polish**: Signal segregation, validation layer, remove unused code (2-3h)

**Total**: 15-20 hours → 85% SRP adherence, 70% unit testable
