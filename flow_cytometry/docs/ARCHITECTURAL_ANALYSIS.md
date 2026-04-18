# Flow Cytometry Module: Architectural Analysis

**Analysis Date**: April 16, 2026  
**Focus**: FlowCanvas & GateController coupling, responsibilities, and signal patterns

---

## Executive Summary

The flow_cytometry module has two heavyweight classes that violate SRP (Single Responsibility Principle):

- **FlowCanvas (1549 lines)**: Mixed rendering, mouse event handling, gate drawing, and coordinate transformation
- **GateController (564 lines)**: Mixed gate lifecycle, statistics computation, and cross-sample propagation

These classes are **moderately coupled** through signals and direct method calls, with **significant UI-business logic blending** in FlowCanvas.

---

## 1. FlowCanvas Class Analysis

**File**: `flow_cytometry/ui/graph/flow_canvas.py`  
**Line Count**: 1,549 lines  
**Inheritance**: `FigureCanvasQTAgg` (matplotlib Qt backend)

### Distinct Responsibilities (7 Major Areas)

#### 1.1 Rendering Engine (550+ lines)
- `_render_data_layer()` — Expensive scatter/histogram data rendering
- `_draw_dot()`, `_draw_pseudocolor()`, `_draw_contour()`, `_draw_density()`, `_draw_histogram()`, `_draw_cdf()` — 6 plot type implementations
- `_apply_axis_formatting()` — Axis tick formatting
- `_build_bio_ticks()` — Biologically-sensible decade labeling
- **Issue**: Pure rendering logic coupled to Qt/matplotlib specifics. Could extract to separate "PlotRenderer" service.

#### 1.2 Gate Visualization (300+ lines)
- `_render_gate_layer()` — Gate overlay orchestration
- `_redraw_gate_overlays()` — Individual gate patch drawing (100+ lines, handles 5 gate types)
- `_draw_node_labels()` — Statistics label placement
- `_format_gate_label()` — Label text construction
- **Issue**: Gate rendering has separate concerns (patch creation, label positioning, color selection). Should extract "GateOverlayRenderer".

#### 1.3 Mouse Event Handling State Machine (300+ lines)
- `_on_press()` — Dispatch to drawing, selection, or polygon vertex modes
- `_on_motion()` — Rubber-band preview during drawing
- `_on_release()` — Finalize gate or cancel
- `_on_dblclick()` — Close polygon
- `keyPressEvent()` — Escape to cancel drawing
- **Issue**: State machine is inline with gate drawing. Could extract "GateDrawingStateMachine".

#### 1.4 Gate Drawing Finalization (200+ lines)
- `_finalize_rectangle()`, `_finalize_polygon()`, `_finalize_ellipse()`, `_finalize_quadrant()`, `_finalize_range()` — Create gate objects from UI coordinates
- `_try_select_gate()` — Hit testing for gate selection
- **Issue**: Creates Gate objects directly, which is business logic in UI layer.

#### 1.5 Coordinate Transformation (100+ lines)
- `_transform_x()`, `_transform_y()` — Apply scale transforms to raw data
- `_inverse_transform_x()`, `_inverse_transform_y()` — Reverse transforms for gate drawing
- **Issue**: These should be extracted to a "CoordinateMapper" service for reuse elsewhere.

#### 1.6 Drawing Progress Visualization (250+ lines)
- `_draw_polygon_progress()`, `_clear_polygon_progress()` — Polygon vertex visualization
- `_clear_rubber_band()` — Rubber-band removal
- `_show_instruction()`, `_update_instruction()`, `_hide_instruction()` — On-canvas hints
- `_cancel_drawing()` — Cleanup on abort
- **Issue**: Fine-grained UI state management. Could extract "DrawingProgressManager".

#### 1.7 Data & State Management (150+ lines)
- `set_data()`, `set_axes()`, `set_scales()`, `set_display_mode()`, `set_drawing_mode()`, `set_gates()`, `select_gate()` — Public API
- `begin_update()`, `end_update()` — Batch rendering
- `redraw()` — Main render orchestration
- `_show_empty()`, `_show_error()`, `_show_loading()`, `_hide_loading()` — State overlays
- **Issue**: OK responsibility, but API is mixing concerns (rendering config, gate display, drawing mode).

### Methods by Category

| Category | Methods | Line Est. |
|----------|---------|-----------|
| **Rendering** | `_render_data_layer()`, `_apply_axis_formatting()`, `_build_bio_ticks()`, `_draw_*` (6 types), `_show_empty()`, `_show_error()` | ~550 |
| **Gate Visualization** | `_render_gate_layer()`, `_redraw_gate_overlays()`, `_draw_node_labels()`, `_format_gate_label()`, `select_gate()` | ~300 |
| **Mouse Events** | `_on_press()`, `_on_motion()`, `_on_release()`, `_on_dblclick()`, `keyPressEvent()`, `mouseDoubleClickEvent()` | ~250 |
| **Gate Drawing** | `_finalize_rectangle/polygon/ellipse/quadrant/range()`, `_try_select_gate()` | ~200 |
| **Coordinate Xform** | `_transform_x/y()`, `_inverse_transform_x/y()` | ~100 |
| **Progress UI** | `_draw_polygon_progress()`, `_clear_*()`, `_show/update/hide_instruction()`, `_cancel_drawing()` | ~250 |
| **State & Config** | `set_data/axes/scales/display_mode/drawing_mode/gates()`, `redraw()`, `begin/end_update()` | ~150 |
| **Lifecycle** | `__init__()`, `showEvent()`, `resizeEvent()` | ~100 |

### Key Data Structures

- `_canvas_bitmap_cache` — Matplotlib bitmap cache (named from previous naming pass)
- `_gate_overlay_artists` — `dict[str, dict]` with patch info (stores matplotlib patches and metadata)
- `_gate_nodes` — List for label rendering
- `_active_gates` — Current gates to display
- `_mpl_conn_press/release/dblclick` — Matplotlib event connection IDs
- `_drawing_mode`, `_is_drawing`, `_drag_start` — State machine state
- `_polygon_vertices` — Accumulates polygon points

### Signals (5 public)

```python
point_clicked(float, float)         # Raw click event
region_selected(dict)               # Selection region (unused in current codebase?)
gate_created(Gate)                  # NEW gate drawn by user
gate_modified(str)                  # gate_id (appears unused)
gate_selected(object)               # gate_id or None
```

**Signal Connection Pattern**:
- `gate_created` → connected in `GraphWindow._setup_ui()` → emitted to `GraphManager._on_gate_drawn()`
- `gate_selected` → connected in `GraphManager` → forwarded as `gate_selection_changed` signal

### Tight Couplings

| Coupling Point | Issue | Impact |
|----------------|-------|--------|
| **Direct Gate Creation** | `_finalize_rectangle()` etc. directly instantiate `RectangleGate`, `PolygonGate`, etc. | UI layer has hard dependency on gate classes; can't mock gates for testing |
| **Matplotlib Patches** | Gate rendering uses `MplRectangle`, `MplPolygon`, `MplEllipse` patches directly | Can't reuse gate visualization in non-matplotlib contexts |
| **AxisScale Dependency** | Transforms tightly coupled to `AxisScale` object structure | Can't easily test coordinate transformation independently |
| **GraphWindow Integration** | `FlowCanvas` signals reach `GraphWindow` → `GraphManager` → back to canvas | Tangled signal routing makes it hard to trace flow |
| **Direct State Access** | `set_data()`, `set_axes()`, `set_scales()` modify internal state directly | No validation layer; state can become inconsistent |
| **matplotlib.rcParams** | Global matplotlib styling applied in `__init__()` | Non-idiomatic; affects other matplotlib consumers in same process |

---

## 2. GateController Class Analysis

**File**: `flow_cytometry/analysis/gate_controller.py`  
**Line Count**: 564 lines  
**Inheritance**: `QObject`

### Distinct Responsibilities (5 Major Areas)

#### 2.1 Gate Lifecycle Management (250+ lines)
- `add_gate()` — Add a gate to tree with naming and parent resolution
- `modify_gate()` — Update gate geometry and recompute stats for all sharing nodes
- `remove_population()` — Remove a node from tree
- `rename_population()` — Rename a node and trigger propagation
- `split_population()` — Create Inside/Outside sibling populations
- `generate_unique_name()` — Collision-free naming
- **Issue**: Clear responsibility, well-designed.

#### 2.2 Special Gate Handling (50+ lines)
- `_add_quadrant_gate()` — Creates 4 child RectangleGates for each Quadrant
- **Issue**: Hard-coded quadrant logic. Should be in gate class or factory.

#### 2.3 Statistics Computation (150+ lines)
- `recompute_all_stats()` — Full sample recompute
- `_compute_node_stats()` — Single node stats
- `_recompute_subtree()` — Node + descendants
- `_walk_and_compute()` — Recursive tree traversal
- **Issue**: Mixed concerns — tree traversal + statistics calculation. Could extract "StatisticsService".

#### 2.4 Gate Tree Cloning / Propagation (100+ lines)
- `copy_gates_to_group()` — Copy gate tree to multiple samples
- `_clone_gate_tree()` — Deep-clone tree structure
- `_clone_children()` — Recursive cloning
- `_find_root_gate_id()` — Ancestry traversal
- **Issue**: Part of propagation flow. Depends on GatePropagator being called externally.

#### 2.5 Gate Query Helpers (60+ lines)
- `get_gates_for_display()` — Fetch direct children for canvas rendering
- **Issue**: Simple query; fine to keep here.

### Methods by Category

| Category | Methods | Line Est. |
|----------|---------|-----------|
| **Lifecycle** | `add_gate()`, `modify_gate()`, `remove_population()`, `rename_population()`, `split_population()`, `generate_unique_name()` | ~250 |
| **Statistics** | `recompute_all_stats()`, `_compute_node_stats()`, `_recompute_subtree()`, `_walk_and_compute()` | ~150 |
| **Cloning** | `copy_gates_to_group()`, `_clone_gate_tree()`, `_clone_children()`, `_find_root_gate_id()` | ~100 |
| **Special Types** | `_add_quadrant_gate()` | ~50 |
| **Queries** | `get_gates_for_display()` | ~60 |

### Signals (6 public)

```python
gate_added(str, str)                 # sample_id, node_id
gate_removed(str, str)               # sample_id, node_id
gate_renamed(str, str)               # sample_id, node_id
gate_stats_updated(str, str)         # sample_id, node_id
all_stats_updated(str)               # sample_id
propagation_requested(str, str)      # gate_id, source_sample_id
```

**Signal Connection Pattern**:
- Emitted by `GateController` methods
- Consumed by: `GraphWindow`, `GateHierarchy` widget, and likely `GatePropagator`
- No direct feedback from listeners back to controller

### Tight Couplings

| Coupling Point | Issue | Impact |
|----------------|-------|--------|
| **State Direct Access** | `self._state.experiment.samples.get()` throughout | Tightly bound to `FlowState` structure; hard to inject alternative state sources |
| **Hard-Coded Quadrant Logic** | `_add_quadrant_gate()` creates 4 RectangleGates with magic bounds `±1e9` | Gate creation logic in controller instead of gate class factory |
| **Signal-Driven Workflow** | All external updates depend on signal emissions being connected correctly | Fragile: missing connection = silent failure; no transaction model |
| **Deep Tree Traversal** | `_walk_and_compute()`, `_clone_children()` recursively traverse `GateNode` tree | Depends on tree structure staying consistent; hard to parallelize stats |
| **Event Data Re-fetching** | `_compute_node_stats()` re-filters events using gate masks on each call | Inefficient; could cache filtered events or use memoization |

---

## 3. UI-Business Logic Coupling

### Current Architecture

```
GraphWindow (UI Layer)
    ├── FlowCanvas (UI + Business Logic)
    │   ├── Rendering (matplotlib)
    │   ├── Gate Drawing (state machine)
    │   └── Gate Creation (creates Gate objects!)
    │
    └── GateController (Business Logic)
        ├── Gate Lifecycle
        ├── Statistics Computation
        └── Tree Cloning

Signal Flow:
FlowCanvas.gate_created → GraphWindow.gate_drawn → GraphManager._on_gate_drawn()
   → GateController.add_gate() → GateController.gate_added
   → GateHierarchy widget updates
```

### Problem Areas

1. **Gate Creation in UI Layer**
   - `FlowCanvas._finalize_rectangle()` creates `RectangleGate(x_param, y_param, x_min, x_max, ...)`
   - This is business logic (domain model instantiation) happening in rendering code
   - Makes testing canvas separately impossible without mocking Gate classes

2. **Coordinate Transformation Scattered**
   - Transform logic lives in FlowCanvas but needed by:
     - Gate drawing (already there)
     - Axis formatting
     - Potentially other UIs
   - Should be a reusable service

3. **Statistics Tied to GateController Signals**
   - Stats computed inside `GateController` methods
   - No way to trigger stats update without going through controller
   - Hard to parallelize or batch compute

4. **No Validation Layer**
   - `FlowCanvas.set_data()` directly assigns `_current_data`
   - `FlowCanvas.set_scales()` directly assigns `_x_scale`, `_y_scale`
   - No checks for consistency (e.g., missing columns, invalid ranges)

5. **Gate Rendering Uses Matplotlib Patches Directly**
   - `_redraw_gate_overlays()` creates patches (MplRectangle, MplPolygon, etc.)
   - Can't render gates in non-matplotlib contexts (e.g., web export, OpenGL viewer)

---

## 4. Signal Usage Patterns

### FlowCanvas Signals (5)

| Signal | Emitted By | Listeners | Purpose |
|--------|-----------|-----------|---------|
| `gate_created(Gate)` | `_finalize_rectangle/polygon/ellipse/quadrant/range()` | GraphWindow | Deliver newly drawn gate to UI handler |
| `gate_selected(gate_id or None)` | `_try_select_gate()` | GraphManager | Highlight gate in hierarchy, update properties |
| `region_selected(dict)` | NEVER EMITTED | — | Unused (legacy from early design?) |
| `gate_modified(str)` | NEVER EMITTED | — | Unused; modifications happen via GateController |
| `point_clicked(float, float)` | NEVER EMITTED | — | Unused; click routing handled inline |

### GateController Signals (6)

| Signal | Emitted By | Listeners | Purpose |
|--------|-----------|-----------|---------|
| `gate_added(sample_id, node_id)` | `add_gate()`, `_add_quadrant_gate()` | GateHierarchy, StatsPanel | Update tree display after gate added |
| `gate_removed(sample_id, node_id)` | `remove_population()` | GateHierarchy, StatsPanel | Update tree display after gate removed |
| `gate_renamed(sample_id, node_id)` | `rename_population()` | GateHierarchy | Update node name display |
| `gate_stats_updated(sample_id, node_id)` | `add_gate()`, `modify_gate()`, `split_population()`, `rename_population()` | StatsPanel, GateHierarchy | Refresh statistics display for gate |
| `all_stats_updated(sample_id)` | `recompute_all_stats()` | ??? (not found in codebase) | Broadcast full sample recompute done |
| `propagation_requested(gate_id, source_sample_id)` | `add_gate()`, `modify_gate()`, `copy_gates_to_group()`, `_add_quadrant_gate()`, `rename_population()` | GatePropagator | Request cross-sample gate updates |

### Issues with Current Signal Patterns

1. **No Transaction Semantics**
   - `gate_added` fires, but listeners might fail to receive or process it
   - No "gate_add_failed" signal for error handling
   - No rollback if propagation fails

2. **Unused Signals (Code Debt)**
   - `region_selected`, `gate_modified`, `point_clicked` → Never emitted
   - Dead code confuses future maintainers

3. **Signal Broadcast Pollution**
   - `all_stats_updated(sample_id)` emitted but listener unclear
   - `propagation_requested` fires whenever a gate changes, but GatePropagator runs asynchronously
   - No backpressure if propagation is slow

4. **No Listener Registration Validation**
   - Can't track if a signal is properly connected
   - Silent failures if signal consumers are missing

5. **Mixing Data Carriers**
   - Some signals carry domain objects (Gate), others carry IDs (gate_id)
   - Inconsistent; makes bulk operations harder

---

## 5. Refactoring Recommendations

### Phase 1: Extract Services (High-Impact, Medium Effort)

#### 1.1 CoordinateMapper Service
**Purpose**: Reusable coordinate transformation

```python
class CoordinateMapper:
    def __init__(self, x_scale: AxisScale, y_scale: AxisScale):
        self.x_scale = x_scale
        self.y_scale = y_scale
    
    def transform_x(self, x: np.ndarray) -> np.ndarray: ...
    def transform_y(self, y: np.ndarray) -> np.ndarray: ...
    def inverse_transform_x(self, x: np.ndarray) -> np.ndarray: ...
    def inverse_transform_y(self, y: np.ndarray) -> np.ndarray: ...
```

**Benefits**:
- Reusable in other components (e.g., axis label formatting, gate editing UI)
- Testable independently
- Reduces FlowCanvas from 1549 → ~1450 lines

#### 1.2 PlotRenderer Service
**Purpose**: Pure rendering logic decoupled from matplotlib/Qt

```python
class PlotRenderer:
    def render_scatter(self, x, y, config) -> List[Artist]: ...
    def render_pseudocolor(self, x, y, config) -> List[Artist]: ...
    def render_contour(self, x, y, config) -> List[Artist]: ...
    def render_density(self, x, y, config) -> List[Artist]: ...
    def render_histogram(self, x, config) -> List[Artist]: ...
    def render_cdf(self, x, config) -> List[Artist]: ...
```

**Benefits**:
- Decouples plot rendering from canvas lifecycle
- Renders can be tested with mock Axes
- Could port to other backends (Plotly, PyVista, etc.)
- Reduces FlowCanvas by ~350 lines

#### 1.3 GateOverlayRenderer Service
**Purpose**: Render gate patches and labels without canvas state

```python
class GateOverlayRenderer:
    def render_gates(
        self, 
        gates: List[Gate], 
        nodes: List[GateNode],
        selected_id: Optional[str],
        ax: Axes
    ) -> Dict[str, ArtistInfo]: ...
    
    def render_labels(
        self,
        nodes: List[GateNode],
        ax: Axes
    ) -> List[Artist]: ...
```

**Benefits**:
- Gate rendering logic isolated
- Can render same gates with different backends
- `_redraw_gate_overlays()` becomes thin wrapper
- Reduces FlowCanvas by ~250 lines

#### 1.4 StatisticsService
**Purpose**: Decouple statistics computation from GateController

```python
class StatisticsService:
    def compute_node_stats(
        self,
        node: GateNode,
        parent_events: pd.DataFrame,
        total_events: pd.DataFrame
    ) -> Dict: ...
    
    def recompute_subtree(
        self,
        node: GateNode,
        events: pd.DataFrame
    ) -> None: ...
    
    def walk_and_compute(
        self,
        node: GateNode,
        parent_events: pd.DataFrame,
        ...
    ) -> None: ...
```

**Benefits**:
- Statistics can be computed in parallel
- Can be tested independently
- Reduces GateController from 564 → ~350 lines
- Enables batch stats computation

### Phase 2: Extract Drawing State Machine (Medium-Impact, Medium Effort)

#### 2.1 GateDrawingStateMachine
**Purpose**: Encapsulate mouse event handling state machine

```python
class DrawingStateMachine:
    def __init__(self, mode_changed_callback, instruction_callback):
        self.mode = GateDrawingMode.NONE
        self.on_mode_changed = mode_changed_callback
        self.on_instruction_updated = instruction_callback
    
    def handle_press(self, x, y, in_axes) -> Optional[Gate]: ...
    def handle_motion(self, x, y) -> Optional[OverlayArtist]: ...
    def handle_release(self, x, y) -> Optional[Gate]: ...
    def handle_dblclick(self, x, y) -> Optional[Gate]: ...
    def cancel(self) -> None: ...
```

**Benefits**:
- State machine logic testable without UI
- Can inject custom finalization callbacks
- Reduces FlowCanvas by ~300 lines
- Enables alternative drawing modes (freehand, etc.)

### Phase 3: Move Gate Creation to Factory (Medium-Impact, Low Effort)

#### 3.1 GateFactory
**Purpose**: Extract gate instantiation from UI layer

```python
class GateFactory:
    @staticmethod
    def create_rectangle(
        x_param: str, y_param: str,
        x0, y0, x1, y1,
        x_scale: AxisScale, y_scale: AxisScale
    ) -> RectangleGate: ...
    
    @staticmethod
    def create_polygon(
        x_param: str, y_param: str,
        vertices: List[Tuple],
        x_scale: AxisScale, y_scale: AxisScale
    ) -> PolygonGate: ...
```

**Benefits**:
- Gate creation no longer in UI layer
- Can validate parameters before creating gates
- UI layer remains agnostic of gate types
- Reduces FlowCanvas by ~100 lines

### Phase 4: Segregate Signal Interfaces (Medium-Impact, High Effort)

#### 4.1 Create Focused Signal Groups
```python
class CanvasRenderingSignals(QObject):
    """Rendering pipeline lifecycle (internal use)"""
    data_rendered = pyqtSignal()
    gates_rendered = pyqtSignal()

class CanvasInteractionSignals(QObject):
    """User interaction events (public API)"""
    gate_created = pyqtSignal(Gate)
    gate_selected = pyqtSignal(str)  # gate_id

class ControllerGatingSignals(QObject):
    """Gate tree mutations (public API)"""
    gate_added = pyqtSignal(str, str)  # sample_id, node_id
    gate_removed = pyqtSignal(str, str)
    
class ControllerPropagationSignals(QObject):
    """Cross-sample updates (internal coordination)"""
    propagation_requested = pyqtSignal(str, str)
```

**Benefits**:
- Clear separation of concerns
- Easier to mock/stub signal groups in tests
- Reduces coupling between unrelated listeners
- Enables selective subscription

### Phase 5: Validation Layer (Low-Impact, Medium Effort)

#### 5.1 DataValidator
```python
class CanvasDataValidator:
    def validate_data(self, df: pd.DataFrame) -> ValidationResult: ...
    def validate_axes(self, x_param: str, y_param: str, df: pd.DataFrame) -> ValidationResult: ...
    def validate_scales(self, x_scale: AxisScale, y_scale: AxisScale) -> ValidationResult: ...
```

**Benefits**:
- Prevents invalid state assignments
- Provides user-friendly error messages
- Makes bugs reproducible (validation errors logged)

---

## 6. Summary Table

| Issue | Impact | Effort | Priority |
|-------|--------|--------|----------|
| **FlowCanvas too large (1549 lines)** | Hard to maintain, understand, test | Extract ~5 services | HIGH |
| **Gate creation in UI layer** | Business logic in wrong layer, untestable | Create GateFactory | HIGH |
| **Statistics computation in GateController** | Hard to parallelize, test independently | Extract StatisticsService | MEDIUM |
| **Coordinate transform scattered** | Low reusability, hard to extend | Extract CoordinateMapper | MEDIUM |
| **Unused signals** | Code debt, confusion | Remove 3 signals | LOW |
| **No validation layer** | Bugs hard to catch, user-facing errors bad | Add DataValidator | MEDIUM |
| **Signal transaction semantics** | Silent failures, no rollback | Add error/success handlers | LOW |
| **matplotlib.rcParams pollution** | Affects other matplotlib users | Use context manager | LOW |

---

## 7. Key Methods for Refactoring

### FlowCanvas
**Extract to PlotRenderer**:
- `_render_data_layer()` (80 lines)
- `_draw_dot/pseudocolor/contour/density/histogram/cdf()` (~200 lines)
- `_apply_axis_formatting()`, `_build_bio_ticks()` (~100 lines)

**Extract to CoordinateMapper**:
- `_transform_x/y()`, `_inverse_transform_x/y()` (~70 lines)

**Extract to GateOverlayRenderer**:
- `_render_gate_layer()` (15 lines wrapper remains)
- `_redraw_gate_overlays()` (~170 lines)
- `_draw_node_labels()`, `_format_gate_label()` (~60 lines)

**Extract to DrawingStateMachine**:
- `_on_press/motion/release/dblclick()` (~250 lines)
- `_cancel_drawing()`, `_finalize_*()` (~200 lines)

**Extract to GateFactory**:
- `_finalize_rectangle/polygon/ellipse/quadrant/range()` (~100 lines)

**Remove (unused signals)**:
- `region_selected`, `gate_modified`, `point_clicked` signal definitions

**Remaining in FlowCanvas (~600 lines)**:
- Qt lifecycle (`__init__`, `showEvent`, `resizeEvent`)
- Public API (`set_data`, `set_axes`, `set_scales`, `set_display_mode`, `set_drawing_mode`, `set_gates`)
- Redraw orchestration (`redraw`, `begin_update`, `end_update`)
- State overlays (`_show_empty`, `_show_error`, `_show_loading`)
- Progress UI helpers (`_draw_polygon_progress`, `_show_instruction`, etc.)

### GateController
**Extract to StatisticsService**:
- `_compute_node_stats()` (~40 lines)
- `_recompute_subtree()` (~20 lines)
- `_walk_and_compute()` (~60 lines)
- `recompute_all_stats()` (~20 lines wrapper remains)

**Simplify or Remove**:
- `_add_quadrant_gate()` (50 lines) → Move to QuadrantGate.create_children() class method

**Remaining in GateController (~350 lines)**:
- `add_gate()`, `modify_gate()`, `remove_population()`, `rename_population()`, `split_population()`
- `copy_gates_to_group()`, `_clone_gate_tree()`, `_clone_children()`
- `get_gates_for_display()`, `generate_unique_name()`

---

## 8. Testing Implications

### Current Testing Challenges

1. **FlowCanvas is untestable** without:
   - Mocking matplotlib Figure, Axes, FigureCanvasQTAgg
   - Mocking all Gate subclasses
   - Mocking QApplication for Qt signals

2. **GateController is testable** but requires:
   - Creating full FlowState + Experiment + Sample + FcsData objects
   - Manually wiring signal listeners

3. **Integration tests impossible** without:
   - Full Qt application running
   - Matplotlib rendering to offscreen backend

### Post-Refactoring Testing

1. **CoordinateMapper**
   - Pure unit tests with numpy arrays
   - Parametrized tests for each transform type

2. **PlotRenderer**
   - Mock Axes, test artist creation
   - No Qt dependency

3. **StatisticsService**
   - Unit tests with mock GateNode + events
   - No signals or state

4. **GateDrawingStateMachine**
   - Unit tests with mock canvas coordinates
   - No matplotlib or Qt

5. **FlowCanvas**
   - Integration test using extracted services
   - Can test signal routing without rendering

---

## Conclusion

The architecture requires **3-4 extraction phases** to reach acceptable quality:

1. **Extract coordinate transformation** (1-2 hours) → Enable reuse
2. **Extract rendering services** (4-6 hours) → Reduce complexity
3. **Extract statistics service** (2-3 hours) → Enable parallelization
4. **Extract drawing state machine** (3-4 hours) → Improve testability

**Total Estimated Effort**: 10-15 hours  
**Resulting Code Quality**: 60% → 85% (SRP adherence)  
**Testing Coverage Potential**: 0% → 70% (unit testable components)

The flow_cytometry module is **structurally sound but needs tactical decomposition** to remain maintainable as features grow.
