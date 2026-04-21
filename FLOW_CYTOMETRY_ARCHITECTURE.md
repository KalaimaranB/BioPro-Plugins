# Flow Cytometry Module Architecture Overview

## Quick Navigation
- [1. Main UI Components](#1-main-ui-components)
- [2. Gating Architecture](#2-gating-architecture)
- [3. Rendering System](#3-rendering-system)
- [4. Sample Management](#4-sample-management)
- [5. Event/Signal Architecture](#5-eventsignal-architecture)
- [6. Data Flow Diagram](#6-data-flow-diagram)
- [7. Key Classes & Responsibilities](#7-key-classes--responsibilities)

---

## 1. Main UI Components

### 1.1 Entry Point: `ui/main_panel.py` — FlowCytometryPanel
**Purpose**: Root widget injected by BioPro. Orchestrates the entire workspace.

**Layout Structure**:
```
┌─────────────────────────────────────────────────────────────┐
│  Tab Bar: Workspace | Compensation | Gating | Statistics   │
├─────────────────────────────────────────────────────────────┤
│                   Ribbon Stack (height: 64px)               │
├──────────────────┬────────────────────┬────────────────────┤
│  Groups Panel    │                    │  Properties Panel  │
├──────────────────┤                    │  (scrollable,      │
│  Sample List     │  Graph Manager     │   context-        │
├──────────────────┤  (Tabbed Graphs)   │   sensitive)       │
│  Gate Hierarchy  │                    │                    │
│  (splitter       │                    │                    │
│   vertical)      │                    │                    │
└──────────────────┴────────────────────┴────────────────────┘
```

**Key Responsibilities**:
- Manages 5 ribbon tabs (Workspace, Compensation, Gating, Statistics, Reports)
- Owns `FlowState` — single source of truth for session state
- Instantiates `GateController` and `GatePropagator` for gate lifecycle
- Wires all internal signal/slot connections
- Emits `state_changed` to BioPro's HistoryManager for undo/redo

**Signal Emission Points**:
- `state_changed()` — on any gate add/remove (connected to BioPro)
- `results_ready()` — when analysis completes

---

### 1.2 Left Sidebar: Sample & Gate Management

#### 1.2a `ui/widgets/sample_list.py` — SampleList
**Purpose**: Flat list of all loaded samples without hierarchy.

**Features**:
- Lists samples with role badges: `○` (tube), `◉` (FMO), `◧` (compensation), `◌` (blank)
- Shows event count per sample
- Filterable by group
- Double-click → opens graph for sample

**Key Methods**:
- `filter_by_group(group_id)` — updates displayed samples
- `refresh()` — rebuilds from current state
- `update_all_sample_stats()` — accepts stats updates from signals

**Signals**:
- `sample_double_clicked(sample_id)` → GraphManager opens graph
- `selection_changed(sample_id)` → PropertiesPanel shows sample info

#### 1.2b `ui/widgets/gate_hierarchy.py` — GateHierarchy
**Purpose**: Tree view of the gating strategy with two modes.

**Modes**:
- **Current Sample** (default): Shows gates for the currently active sample
- **Global Strategy**: Shows a template/reference gating tree (for adaptive gates)

**Features**:
- Hierarchical display with depth-based colors: cyan, amber, teal, etc.
- Columns: Population, Events, %Parent
- Right-click context menu for rename/delete/split/copy
- Double-click → opens graph filtered to that gate

**Key Concept — "Global Strategy" vs "Current Sample"**:
- **Current Sample**: The gate tree specific to one sample (`sample.gate_tree`)
- **Global Strategy**: A reference gating tree template used for adaptive repositioning
  - When drawing a gate on Sample A, it's stored in A's tree
  - The gate can then be "propagated" to Samples B, C, D via `GatePropagator`
  - Each sample gets its own copy of the gate, adapted to that sample's data distribution

**Signals**:
- `gate_double_clicked(node_id)` → GraphManager opens graph at gate
- `selection_changed(node_id)` → PropertiesPanel shows gate stats
- `gate_rename_requested(sample_id, node_id, new_name)` → GateController
- `gate_delete_requested(sample_id, node_id)` → GateController

---

### 1.3 Center: Graph Rendering

#### 1.3a `ui/graph/graph_manager.py` — GraphManager
**Purpose**: Tabbed container for multiple graph windows.

**Features**:
- Manages multiple `GraphWindow` instances as tabs
- Shows welcome screen when empty
- Forwards drawing tool selections to active graph
- Tracks which graphs are open

**Key Methods**:
- `open_graph_for_sample(sample_id, node_id=None)` — creates/focuses tab
- `set_drawing_mode(tool_name)` — broadcasts tool to active canvas

**Signals**:
- `gate_drawn(Gate, sample_id, parent_node_id)` → GateController
- `gate_selection_changed(gate_id)` → PropertiesPanel highlights in tree

---

#### 1.3b `ui/graph/graph_window.py` — GraphWindow
**Purpose**: Single interactive FACS plot with controls.

**Features**:
- X/Y axis dropdowns (channel selection)
- Display mode selector (Pseudocolor, Dot Plot, Contour, Density, Histogram, CDF)
- Transform button (opens `TransformDialog` for scaling config)
- Prev/Next sample navigation buttons
- Breadcrumb showing gate hierarchy path
- Canvas rendering via `FlowCanvas`

**Key Methods**:
- `set_data(events)` → updates scatter plot
- `set_axes(x_param, y_param)` → changes parameters
- `set_scales(x_scale, y_scale)` → updates transforms
- `set_display_mode(mode)` → changes plot type
- `set_drawing_mode(mode)` → activates gate drawing tool
- `set_gates(gates, gate_nodes)` → renders gate overlays

**Signals**:
- `gate_drawn(Gate, sample_id, parent_node_id)` → forwarded from canvas
- `gate_selection_changed(gate_id)` → forwarded from canvas
- `axis_scale_sync_requested(channel, scale)` → broadcast scale to other graphs
- `navigation_requested("prev_sample"|"next_sample"|"parent_gate")` → GraphManager

---

#### 1.3c `ui/graph/flow_canvas.py` — FlowCanvas
**Purpose**: Core matplotlib rendering engine for FACS data.

**Architecture** (SOLID principles):
- **FlowCanvas**: Orchestration, state machine (drawing mode), mouse event handling
- **CoordinateMapper** (flow_services.py): Transform/inverse-transform coordinates
- **GateFactory** (flow_services.py): Create gate objects from drawing parameters
- **GateOverlayRenderer** (flow_services.py): Render gate patches onto axes

**Rendering System**:
1. **Data Layer** (expensive):
   - Scatter plot (dot plot): All events as transparent points
   - Pseudocolor (hexbin): 2D histogram with heatmap colors
   - Contour: Kernel density estimation contours
   - Density: KDE smooth plot
   - Histogram: 1D distribution
   - CDF: Cumulative distribution

2. **Gate Layer** (cheap, redrawn frequently):
   - Overlay patches (rectangles, polygons, ellipses, quadrants)
   - Color-coded by depth: `_GATE_PALETTE` (8 colors cycling)
   - Fill alpha: 0.12, edge alpha: 0.9
   - Selected gate highlighted in amber

3. **Caching Strategy**:
   - `_canvas_bitmap_cache`: Stores rendered scatter data as bitmap
   - `_gate_overlay_artists`: Dict of gate_id → matplotlib patches
   - Only redraw data layer when axes/transform/mode changes
   - Redraw gate layer quickly when gates are added/modified

**Rendering Constraints**:
- `_max_events`: Subsampling limit (default 100,000). Set to `None` for full render
- `_quality_multiplier`: Grid resolution scaler (1.0 = normal, 2.0 = high quality)
- Used by `RenderWindow` (full render): `_max_events = None`, `_quality_multiplier = 2.0`

**Display Modes**:
```python
class DisplayMode(Enum):
    PSEUDOCOLOR = "Pseudocolor"  # Hexbin density heatmap
    DOT_PLOT = "Dot Plot"        # Scatter of all events
    CONTOUR = "Contour"          # KDE contours
    DENSITY = "Density"          # KDE smooth surface
    HISTOGRAM = "Histogram"      # 1D distribution
    CDF = "CDF"                  # Cumulative distribution
```

**Gate Drawing State Machine**:
- `_drawing_mode`: Tool selection (rectangle, polygon, ellipse, quadrant, range)
- `_is_drawing`: Flag for active drawing
- `_polygon_vertices`: Accumulated points for polygon gates
- `_rubber_band_patch`: Visual feedback during drawing
- Mouse events: press/release/motion → build gate → emit `gate_created`

**Key Signals**:
- `gate_created(Gate)` → GraphWindow → GateController
- `gate_selected(gate_id)` → PropertiesPanel highlights in tree
- `gate_modified(gate_id)` → GateController recomputes stats

---

#### 1.3d `ui/graph/render_window.py` — RenderWindow
**Purpose**: Modeless window for high-quality, full-dataset rendering.

**Configuration**:
```python
self._canvas._max_events = None           # No subsampling
self._canvas._quality_multiplier = 2.0    # Double grid resolution
```

**Features**:
- Copy to clipboard
- Save high-res image (PNG @ 300 DPI, PDF, SVG)
- Full dataset rendering (no event subsampling)
- Double grid resolution for publication quality

---

### 1.4 Right Sidebar: Context Aware Display

#### 1.4a `ui/widgets/properties_panel.py` — PropertiesPanel
**Purpose**: Dynamic detail view for selected samples or gates.

**Display Content**:
- **Sample Selected**: file metadata, keywords, channel list, marker assignments
- **Gate Selected**: gate type, parameters, event count, %parent, %total, statistics (Mean, MFI, CV)
- **No Selection**: general workspace info

**Key Methods**:
- `show_sample_properties(sample_id, gate_id=None)` — update display
- Refreshes when `GateController.gate_stats_updated` fires

---

---

## 2. Gating Architecture

### 2.1 Gate Model: `analysis/gating.py`

#### Gate Hierarchy
```
┌─────────────────────────────────────────────┐
│  GateNode (root, is_root=True)              │
│  ├─ Gate: "Lymphocytes" (1-D range)        │
│  ├─ Gate: "CD4+ CD8-" (2-D rectangle)      │
│  │  └─ GateNode (parent: lymphocytes)      │
│  │     ├─ Gate: "CD4 Hi" (polygon)        │
│  │     └─ Gate: "CD4 Low" (polygon)       │
│  └─ ...                                    │
└─────────────────────────────────────────────┘
```

#### Gate Base Class
```python
class Gate(ABC):
    gate_id: str          # UUID for serialization
    x_param: str          # Channel name (e.g., "FSC-A")
    y_param: Optional[str] # None for 1-D gates
    adaptive: bool        # Supports auto-repositioning
    
    def contains(events: pd.DataFrame) -> np.ndarray
    def apply(events: pd.DataFrame) -> pd.DataFrame
    def adapt(events: pd.DataFrame) -> None  # Optional
```

#### Concrete Gate Types
1. **RectangleGate**: 2-D or 1-D range gate (min/max bounds)
2. **PolygonGate**: Free-form polygon with N vertices
3. **EllipseGate**: Gaussian-like elliptical gate
4. **QuadrantGate**: 4-way split (CD4+ CD8+ | CD4+ CD8- | CD4- CD8+ | CD4- CD8-)
5. **RangeGate**: 1-D threshold gate

**Key Property: Scale-Aware Containment**
- Gates store bounds in **raw data space** (e.g., -1000 to 262000)
- `contains()` projects both events and bounds into **display space** using axis scales
- This ensures gate boundaries remain correct on all axis types (linear, log, biexponential)

```python
# Example: Rectangle gate with logicle transform
# Raw space: x_min=-100, x_max=5000
# Display space: transformed by logicle, then compared against events
```

#### GateNode Tree Structure
```python
@dataclass
class GateNode:
    node_id: str
    gate: Optional[Gate]           # None if root
    children: list[GateNode]       # Child gates
    parent: Optional[GateNode]     # Parent reference
    is_root: bool
    
    def find_node_by_id(node_id) -> Optional[GateNode]
    def apply_hierarchy(events) -> pd.DataFrame  # Apply all gates top-down
```

**Hierarchy Application** (Phase 4 deliverable):
- Call `apply_hierarchy(events)` on root node
- Recursively apply each gate to filter events down the tree
- Result: events that passed all ancestor gates

---

### 2.2 Gate Controller: `analysis/gate_controller.py`
**Purpose**: Central orchestrator for gate lifecycle and statistics.

**Responsibilities**:
1. **Gate Lifecycle**: add/modify/delete gates in sample's `GateNode` tree
2. **Statistics Computation**: count, %parent, %total for each population
3. **UI Signals**: emit updates so UI can refresh incrementally
4. **Propagation Trigger**: kick off `GatePropagator` for cross-sample updates

**Key Methods**:
```python
def add_gate(gate, sample_id, name, parent_node_id, ...)
def modify_gate(gate_id, sample_id, new_gate, ...)
def remove_population(sample_id, node_id)
def rename_population(sample_id, node_id, new_name)
```

**Signal Emission Points**:
- `gate_added(sample_id, gate_id)` → trigger UI refresh
- `gate_removed(sample_id, gate_id)` → same
- `gate_stats_updated(sample_id, gate_id)` → PropertiesPanel refresh
- `all_stats_updated(sample_id)` → full sample refresh
- `propagation_requested(gate_id, source_sample_id)` → GatePropagator

---

### 2.3 Gate Propagator: `analysis/gate_propagator.py`
**Purpose**: Background worker that re-applies gate tree to other samples in a group.

**Key Concept: "Global Strategy"**
- When a scientist draws a gate on Sample A, it's specific to A's data
- To reuse the gate on Samples B, C, D, the `GatePropagator`:
  1. Serializes the gate tree from A
  2. Re-applies each gate to B, C, D's event data
  3. Recomputes statistics for each sample
  4. Updates each sample's gate tree with adapted gates
  5. Emits signals to refresh UI (~200ms debounce)

**Workflow**:
```
User draws gate on Sample A
↓
GateController.add_gate() → gate_added signal
↓
GateController.propagation_requested(gate_id, sample_A_id)
↓
GatePropagator receives gate tree snapshot
↓
For each sample in group (B, C, D):
  - Reconstruct gate tree
  - Apply each gate to sample's events
  - Compute statistics
  - Store updated tree in sample.gate_tree
↓
UI updates via all_stats_updated signal
```

**Debounce Mechanism**:
- 200ms timer prevents redundant recalculations
- If user is dragging a gate handle, debounce waits until mouse released
- Single propagation pass after drag completes

---

### 2.4 Global Strategy vs Current Sample

| Aspect | Global Strategy | Current Sample |
|--------|-----------------|----------------|
| **Where Stored** | `experiment.workflow_template.gate_tree` (reference) | `sample.gate_tree` (actual) |
| **Purpose** | Template for adaptive repositioning | Working gates for this sample |
| **Mode** | Gate Hierarchy toggle button → "Global Strategy" | Gate Hierarchy toggle button → "Current Sample" |
| **Use Case** | Scientist designs a reusable workflow | Scientist refines gates for specific sample |
| **When Applied** | Loaded via "Load Workflow Template" ribbon button | When gates are drawn or propagated |

---

---

## 3. Rendering System

### 3.1 Rendering Pipeline

```
┌────────────────────────────────────────────────────────┐
│ set_data(events) → redraw()                           │
└────────────────────┬─────────────────────────────────┘
                     ↓
        ┌────────────────────────────┐
        │ _render_data_layer()       │  (expensive)
        │ - Transform events         │
        │ - Create scatter/hexbin    │
        │ - Cache as bitmap          │
        └─────────────┬──────────────┘
                      ↓
        ┌────────────────────────────┐
        │ _render_gate_layer()       │  (cheap, frequent)
        │ - For each gate:           │
        │   • Transform vertices     │
        │   • Create patch artist    │
        │   • Add to axes            │
        │ - Draw handles if editing  │
        │ - Draw instruction text    │
        └────────────────┬───────────┘
                         ↓
        ┌────────────────────────────┐
        │ draw()                     │
        │ (matplotlib canvas update) │
        └────────────────────────────┘
```

### 3.2 Optimization Strategies

#### Strategy 1: Event Subsampling
- **Default**: 100,000 events max (`_max_events`)
- **Use Case**: Interactive UI responsiveness
- **Full Render**: Set `_max_events = None` in RenderWindow
- **Subsampling**: Random uniform sampling of events

#### Strategy 2: Hexbin Grid Resolution
- **Normal**: `_quality_multiplier = 1.0` (standard grid)
- **High Quality**: `_quality_multiplier = 2.0` (double resolution)
- **Algorithm**: `fast_histogram.histogram2d` for speed
- **Colors**: Matplotlib "turbo" colormap (outliers in dark purple)

#### Strategy 3: Bitmap Caching
- Render scatter data once, cache as bitmap (`_canvas_bitmap_cache`)
- Gate overlays drawn on top without re-rendering scatter
- Invalidate cache only when:
  - Axes change
  - Transform changes
  - Display mode changes
  - Data changes

#### Strategy 4: Rendering Quality vs Responsiveness
| Metric | Optimized | Full Quality |
|--------|-----------|--------------|
| `_max_events` | 100,000 | None (all) |
| `_quality_multiplier` | 1.0 | 2.0 |
| Plot Size | Any | Small (fit on screen) |
| Hexbin Grid | Standard | Double resolution |
| Use Case | Interactive gating | Publication-ready export |

### 3.3 Service Classes (SOLID Design)

#### `CoordinateMapper` (flow_services.py)
```python
class CoordinateMapper:
    def transform_x(x: np.ndarray) -> np.ndarray
    def transform_y(y: np.ndarray) -> np.ndarray
    def inverse_transform_x(x: np.ndarray) -> np.ndarray
    def inverse_transform_y(y: np.ndarray) -> np.ndarray
    def transform_point(x, y) -> Tuple[float, float]
    def untransform_point(x, y) -> Tuple[float, float]
```
- Handles **all coordinate transformations** (data space ↔ display space)
- Respects axis scales (linear, log, biexponential with parameters)
- Testable without UI

#### `GateFactory` (flow_services.py)
```python
class GateFactory:
    def create_rectangle_gate(x1, y1, x2, y2) -> RectangleGate
    def create_polygon_gate(vertices) -> PolygonGate
    def create_ellipse_gate(center, axes) -> EllipseGate
    # ... etc
```
- Creates gate objects from drawing parameters
- Converts display coordinates → raw data coordinates
- Separates business logic from UI

#### `GateOverlayRenderer` (flow_services.py)
```python
class GateOverlayRenderer:
    def render_gate(ax, gate, ...) -> matplotlib.patch
```
- Renders gate overlays onto matplotlib axes
- Handles different gate types (rectangle, polygon, ellipse, etc.)
- Color and transparency management

### 3.4 Transform Types

Located in `analysis/transforms.py`:

```python
class TransformType(Enum):
    LINEAR = "linear"              # y = x
    LOGARITHMIC = "log"            # y = log10(x)
    BIEXPONENTIAL = "biexponential" # Logicle-like
    ASINH = "asinh"                # y = arcsinh(x / sinh_factor)
```

**Biexponential Parameters** (stored in `AxisScale`):
```python
logicle_t: float = 262144  # Top of scale
logicle_w: float = 0.5     # Linear decade width
logicle_m: float = 4.5     # Positive decades
logicle_a: float = 0       # Negative decades
```

**Key Files**:
- `analysis/transforms.py` — transform/inverse-transform functions
- `analysis/scaling.py` — `AxisScale` dataclass, auto-range detection

---

---

## 4. Sample Management

### 4.1 Data Model: `analysis/experiment.py`

#### Sample
```python
@dataclass
class Sample:
    sample_id: str
    display_name: str
    fcs_data: Optional[FCSData]        # Loaded FCS file
    role: SampleRole                   # tube, fmo, compensation, blank, etc.
    markers: list[str]                 # ["CD4", "CD8", "CD3"]
    fmo_minus: Optional[str]           # If FMO, which marker excluded
    group_ids: list[str]               # Groups this sample belongs to
    gate_tree: GateNode                # Hierarchical gating tree
    keywords: dict[str, str]           # Metadata from FCS file
    is_compensated: bool
```

#### Group
```python
@dataclass
class Group:
    group_id: str
    name: str
    role: GroupRole                    # compensation, control, test, all_samples, custom
    color: str                         # Hex color for UI display
    sample_ids: list[str]              # Which samples in this group
```

#### FCSData (lazy-loaded)
```python
@dataclass
class FCSData:
    file_path: Path
    events: pd.DataFrame               # n_events × n_channels
    channels: list[str]                # Channel names
    keywords: dict[str, str]           # FCS metadata
    num_events: int
```

#### Experiment (container)
```python
@dataclass
class Experiment:
    samples: dict[str, Sample]         # sample_id → Sample
    groups: dict[str, Group]           # group_id → Group
    marker_mappings: dict[str, MarkerMapping]  # "CD4" → color, fluorophore
    workflow_template: Optional[WorkflowTemplate]
```

---

### 4.2 Sample Lifecycle

1. **Load Samples** (Workspace ribbon):
   - User selects FCS files
   - Create Sample objects, lazy-load FCS data
   - Add to experiment
   - Emit `samples_loaded` signal

2. **Organize into Groups** (Groups panel):
   - Create Group
   - Add samples to group
   - Assign roles (test, control, compensation)

3. **Apply Compensation** (Compensation ribbon):
   - Compute or import compensation matrix
   - Apply to samples in compensation group
   - Mark as `is_compensated = True`

4. **Draw Gates** (Gating ribbon + canvas):
   - Select sample via SampleList
   - GraphWindow opens
   - Draw gates on canvas
   - GateController adds to sample.gate_tree
   - GatePropagator applies to other samples in group

5. **Compute Statistics** (GateController + GatePropagator):
   - For each gate: count, %parent, %total
   - Display in GateHierarchy columns and PropertiesPanel

---

### 4.3 Serialization

#### Export Workflow (save state)
```python
# FlowState.to_workflow_dict() → JSON
{
    "experiment": {
        "samples": {...},
        "groups": {...},
        "marker_mappings": {...},
        "workflow_template": {...}
    },
    "sample_paths": {
        "sample_1_id": "/path/to/file.fcs",
        ...
    },
    "compensation": {...},
    "view": {
        "current_sample_id": "...",
        "active_x_param": "FSC-A",
        "active_y_param": "SSC-A",
        ...
    },
    "channel_scales": {...}
}
```

#### Import Workflow (load state)
```python
# FlowState.from_workflow_dict(data)
# - Restores experiment structure
# - Reloads FCS files from sample_paths
# - Restores compensation matrix
# - Restores view state (axis selection, transforms)
```

---

---

## 5. Event/Signal Architecture

### 5.1 Signal Flow Diagram

```
USER ACTIONS
  ↓
┌─────────────────────────────────────────────────────────┐
│ UI LAYER (Widgets)                                      │
│ ┌─────────────────┐ ┌──────────────┐ ┌──────────────┐  │
│ │ SampleList      │ │ GateHierarchy│ │FlowCanvas    │  │
│ │ .sample_double_ │ │ .selection_  │ │.gate_created │  │
│ │  clicked        │ │  changed     │ │.gate_selected│  │
│ └────────┬────────┘ └──────┬───────┘ └──────┬───────┘  │
│          │                 │                 │          │
│          └────────┬────────┴────────┬────────┘          │
│                   ↓                 ↓                    │
│          GraphManager:      GateHierarchy:             │
│          gate_drawn →       selection_changed →         │
│          open_graph_for     GateController.add_gate     │
│          sample()                                       │
└─────────────────────┬───────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│ ANALYSIS LAYER (Controllers & Models)                   │
│ ┌──────────────────────────────────────────────────┐    │
│ │ GateController (QObject with signals)            │    │
│ │ ├─ gate_added(sample_id, gate_id)               │    │
│ │ ├─ gate_removed(sample_id, gate_id)             │    │
│ │ ├─ gate_stats_updated(sample_id, gate_id)       │    │
│ │ ├─ all_stats_updated(sample_id)                 │    │
│ │ └─ propagation_requested(gate_id, source_id)   │    │
│ └──────────────┬────────────────────────────────┬─┘    │
│                │                                │       │
│  ┌─────────────↓──────────────┐                │       │
│  │ Sample.gate_tree updated   │ ←──────────────┘       │
│  │ Statistics computed        │ (GatePropagator       │
│  └──────────────┬─────────────┘  returns results)      │
│                 ↓                                       │
│  ┌──────────────────────────────┐                      │
│  │ GatePropagator (background)  │                      │
│  │ - Serializes gate tree       │                      │
│  │ - Re-applies to group        │                      │
│  │ - Returns propagation_results│                      │
│  └──────────────┬───────────────┘                      │
│                 ↓                                       │
│  Updates other samples' gate_tree                      │
└─────────────────┬───────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────┐
│ UI REFRESH (widgets listen to controller signals)      │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│ │SampleList│ │GateHierarchy│ │PropsPanel│ │GraphWin│    │
│ │refresh() │ │refresh() │ │refresh() │ │refresh()│    │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
└─────────────────────────────────────────────────────────┘
                  ↓
            [Screen Updates]
```

### 5.2 Key Signal Connections (wired in main_panel._wire_signals)

```python
# Sample List → Graph + Properties
self._sample_list.sample_double_clicked.connect(
    self._graph_manager.open_graph_for_sample
)
self._sample_list.selection_changed.connect(
    lambda sid: self._properties_panel.show_sample_properties(sid, None)
)

# Gate Hierarchy → Graph + Properties
self._gate_hierarchy.gate_double_clicked.connect(
    self._on_gate_double_clicked
)
self._gate_hierarchy.selection_changed.connect(
    self._on_gate_selection_changed
)

# Canvas Drawing → Gate Controller
self._graph_manager.gate_drawn.connect(
    self._on_gate_drawn  # calls GateController.add_gate()
)

# Gate Controller → UI Refresh
self._gate_controller.gate_added.connect(self.state_changed)  # BioPro hook
self._gate_controller.gate_stats_updated.connect(
    self._on_gate_stats_updated  # PropertiesPanel refresh
)

# Compensation Ribbon → State Update
self._compensation_ribbon.compensation_changed.connect(
    self._on_compensation_changed
)

# Gating Ribbon → Canvas Tool Selection
self._gating_ribbon.tool_selected.connect(
    self._graph_manager.set_drawing_mode
)
```

### 5.3 Signal Types

| Signal | Emitter | Receiver | Purpose |
|--------|---------|----------|---------|
| `sample_double_clicked(id)` | SampleList | GraphManager | Open graph |
| `selection_changed(id)` | SampleList, GateHierarchy | PropertiesPanel | Update sidebar |
| `gate_created(Gate)` | FlowCanvas | GraphWindow → GateController | Store gate |
| `gate_drawn(Gate, sid, parent_id)` | GraphManager | GateController | Add to tree |
| `gate_added(sid, gate_id)` | GateController | main_panel, GateHierarchy | Refresh UI, emit state_changed |
| `gate_stats_updated(sid, gate_id)` | GateController | PropertiesPanel | Update stats display |
| `propagation_requested(gate_id, sid)` | GateController | GatePropagator | Trigger cross-sample update |
| `state_changed()` | main_panel | BioPro HistoryManager | Trigger undo/redo snapshot |
| `tool_selected(tool)` | GatingRibbon | GraphManager | Activate drawing mode |

---

---

## 6. Data Flow Diagram

### 6.1 Gate Drawing Workflow

```
┌─────────────────────────────────────────────┐
│ USER: Double-clicks sample in SampleList    │
└────────────────┬──────────────────────────┘
                 ↓
        GraphManager.open_graph_for_sample(sample_id)
                 ↓
        ┌────────────────────────────────┐
        │ Create GraphWindow tab         │
        │ ├─ Load sample data            │
        │ ├─ Set axes                    │
        │ └─ Display with empty gates    │
        └────────────────┬───────────────┘
                         ↓
        ┌────────────────────────────────┐
        │ USER: Clicks "Rectangle" tool  │
        │ in Gating Ribbon               │
        └────────────┬───────────────────┘
                     ↓
        GatingRibbon.tool_selected("rectangle")
                     ↓
        GraphManager.set_drawing_mode(GateDrawingMode.RECTANGLE)
                     ↓
        FlowCanvas.set_drawing_mode(GateDrawingMode.RECTANGLE)
                     ↓
        Canvas cursor becomes crosshair
                     ↓
        ┌────────────────────────────────┐
        │ USER: Drags rectangle on plot  │
        └────────────┬───────────────────┘
                     ↓
        Mouse Press: FlowCanvas._on_press()
        ├─ Record drag_start coordinates (display space)
        ├─ Show rubber-band feedback
        
        Mouse Motion: FlowCanvas._on_motion()
        ├─ Update rubber-band position
        
        Mouse Release: FlowCanvas._on_release()
        ├─ Convert display coords → raw data coords via CoordinateMapper
        ├─ GateFactory.create_rectangle_gate() builds RectangleGate
        ├─ Emit gate_created(gate) signal
                     ↓
        GraphWindow.canvas.gate_created.connect(...)
                     ↓
        GraphWindow._on_gate_created(Gate)
                     ↓
        GraphWindow.gate_drawn.emit(Gate, sample_id, parent_node_id)
                     ↓
        GraphManager.gate_drawn.emit(Gate, sample_id, parent_node_id)
                     ↓
        FlowCytometryPanel._on_gate_drawn(Gate, sample_id, parent_node_id)
                     ↓
        GateController.add_gate(gate, sample_id, name, parent_node_id)
        ├─ Add gate to sample.gate_tree
        ├─ Generate unique name
        ├─ Compute statistics (count, %parent, %total)
        ├─ Emit gate_added(sample_id, gate_id) signal
        └─ Emit propagation_requested(gate_id, sample_id) signal
                     ↓
        ┌────────────────────────────────┐
        │ UI REFRESH (all listeners)      │
        ├─ GateHierarchy.refresh() → tree │
        ├─ PropertiesPanel.refresh()      │
        ├─ main_panel.state_changed()     │
        │  → BioPro HistoryManager        │
        └────────────────────────────────┘
                     ↓
        GatePropagator runs in background (200ms debounce)
        ├─ Serialize gate tree from sample A
        ├─ Re-apply to samples B, C, D in group
        ├─ Recompute stats for each sample
        ├─ Update their gate_tree
        ├─ Emit all_stats_updated(sample_id) for each
                     ↓
        [Final Result]
        Sample A: gate drawn and selected
        Samples B, C, D: gate propagated, stats updated
        All UI elements refreshed
```

### 6.2 Rendering Workflow

```
┌─────────────────────────────────────┐
│ GraphWindow.set_data(events)        │
└─────────────┬───────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ FlowCanvas.set_data(events)         │
├─ Store in _current_data             │
├─ Invalidate _canvas_bitmap_cache    │
├─ Call redraw()                      │
└─────────────┬───────────────────────┘
              ↓
         Is batch_update? NO
         Is visible?      YES
              ↓
    ┌────────────────────────────────────────┐
    │ _show_loading()                        │
    │ Show "⟳ Rendering…" overlay            │
    └─────────────────┬──────────────────────┘
                      ↓
    ┌────────────────────────────────────────┐
    │ _render_data_layer() [EXPENSIVE]      │
    │ ├─ Subsample events (if _max_events)  │
    │ ├─ Transform via CoordinateMapper     │
    │ ├─ Create plot based on display_mode │
    │ │  (scatter/hexbin/contour/kde/hist) │
    │ ├─ Cache as _canvas_bitmap_cache     │
    │ └─ Draw to axes                      │
    └─────────────────┬──────────────────────┘
                      ↓
    ┌────────────────────────────────────────┐
    │ _render_gate_layer() [CHEAP]          │
    │ For each gate in _active_gates:       │
    │ ├─ Transform vertices (display space)│
    │ ├─ Create matplotlib patch           │
    │ ├─ Set color (from _GATE_PALETTE)    │
    │ └─ Add to axes                       │
    │                                      │
    │ If editing gate:                     │
    │ ├─ Draw resize handles               │
    │ └─ Show instruction text             │
    └─────────────────┬──────────────────────┘
                      ↓
    ┌────────────────────────────────────────┐
    │ canvas.draw()                          │
    │ (Matplotlib renders to screen)         │
    └─────────────────┬──────────────────────┘
                      ↓
    ┌────────────────────────────────────────┐
    │ _hide_loading()                        │
    │ Hide "⟳ Rendering…" overlay            │
    └────────────────────────────────────────┘
```

---

---

## 7. Key Classes & Responsibilities

### Analysis Layer

| Class | File | Purpose |
|-------|------|---------|
| `FlowState` | `analysis/state.py` | Single source of truth for session (experiment, compensation, view state) |
| `Experiment` | `analysis/experiment.py` | Container for samples, groups, marker mappings |
| `Sample` | `analysis/experiment.py` | Individual FCS file with metadata, gate tree |
| `Gate` (base) | `analysis/gating.py` | Abstract gate with `contains()` method |
| `RectangleGate`, etc. | `analysis/gating.py` | Concrete gate types |
| `GateNode` | `analysis/gating.py` | Tree node for hierarchical gating |
| `GateController` | `analysis/gate_controller.py` | Orchestrates gate add/modify/delete + stats |
| `GatePropagator` | `analysis/gate_propagator.py` | Background worker for cross-sample gate updates |
| `CompensationMatrix` | `analysis/compensation.py` | Spectral overlap correction |
| `AxisScale` | `analysis/scaling.py` | Transform type + biexponential parameters |
| `TransformType` | `analysis/transforms.py` | Enum: linear, log, biexponential, asinh |

### UI Layer

| Class | File | Purpose |
|-------|------|---------|
| `FlowCytometryPanel` | `ui/main_panel.py` | Root workspace widget, wires all signals |
| `SampleList` | `ui/widgets/sample_list.py` | Lists samples, emit selection signals |
| `GateHierarchy` | `ui/widgets/gate_hierarchy.py` | Tree of gates with Current/Global mode |
| `PropertiesPanel` | `ui/widgets/properties_panel.py` | Context-aware detail view |
| `GroupsPanel` | `ui/widgets/groups_panel.py` | Lists sample groups, filter SampleList |
| `GraphManager` | `ui/graph/graph_manager.py` | Tabbed container for GraphWindows |
| `GraphWindow` | `ui/graph/graph_window.py` | Single plot with axis/mode/transform controls |
| `FlowCanvas` | `ui/graph/flow_canvas.py` | Matplotlib rendering + gate drawing |
| `RenderWindow` | `ui/graph/render_window.py` | High-quality full-resolution rendering |
| `CoordinateMapper` | `ui/graph/flow_services.py` | Transform ↔ inverse-transform coordinates |
| `GateFactory` | `ui/graph/flow_services.py` | Create gates from drawing parameters |
| `GateOverlayRenderer` | `ui/graph/flow_services.py` | Render gate patches onto axes |

### Ribbon/Ribbon Layer

| Class | File | Purpose |
|-------|------|---------|
| `WorkspaceRibbon` | `ui/ribbons/workspace_ribbon.py` | Add Samples, Load Template |
| `CompensationRibbon` | `ui/ribbons/compensation_ribbon.py` | Compute/import compensation matrix |
| `GatingRibbon` | `ui/ribbons/gating_ribbon.py` | Tool selection (rectangle, polygon, etc.) |
| `StatisticsRibbon` | `ui/ribbons/statistics_ribbon.py` | Export statistics, reports |
| `ReportsRibbon` | `ui/ribbons/reports_ribbon.py` | Generate flow cytometry reports |

---

---

## 8. Common Workflows

### Workflow 1: Load Samples & Set Up Groups
```
1. Click "Add Samples" in Workspace Ribbon
2. Select FCS files
3. WorkspaceRibbon.samples_loaded emits
4. main_panel._on_samples_loaded():
   - Update SampleList
   - Update GroupsPanel
5. User clicks "Grouping" area to organize into groups (control, test, etc.)
6. GroupsPanel creates Groups, updates Experiment
```

### Workflow 2: Draw Gates & Propagate
```
1. Double-click sample in SampleList
2. GraphWindow opens with empty gates
3. Select tool in Gating Ribbon (e.g., Rectangle)
4. Draw rectangle on canvas
5. FlowCanvas.gate_created emits
6. GateController.add_gate():
   - Adds to sample.gate_tree
   - Computes stats
   - Emits gate_added
7. GatePropagator kicks in (200ms debounce):
   - Re-applies gate to other samples in group
   - Updates their gate_tree
   - Emits all_stats_updated for each sample
8. UI refreshes: GateHierarchy, PropertiesPanel, SampleList stats
```

### Workflow 3: Apply Compensation
```
1. Load compensation samples or matrix file
2. Click "Calculate Compensation" or "Import Matrix" in Compensation Ribbon
3. CompensationRibbon.compensation_changed emits
4. main_panel._on_compensation_changed():
   - Stores in state.compensation
   - Marks samples as is_compensated = True
   - Refreshes all graphs (transforms applied with compensation)
5. UI updates immediately
```

### Workflow 4: High-Quality Export
```
1. Graph window is active and displaying desired plot
2. Right-click on canvas → "Deep Render"
3. RenderWindow opens with:
   - _max_events = None (full dataset)
   - _quality_multiplier = 2.0 (double resolution)
4. Click "Save High-Res Image" → PNG at 300 DPI, PDF, or SVG
```

### Workflow 5: Undo/Redo
```
1. User adds gate (state_changed emitted)
2. BioPro HistoryManager snapshots FlowState via state_changed hook
3. User modifies gate (state_changed emitted again)
4. Another snapshot created
5. User presses Ctrl+Z (BioPro)
6. HistoryManager restores previous FlowState
7. UI updates via state observer pattern (TBD: verify mechanism)
```

---

---

## Summary: Key Takeaways

1. **Single Source of Truth**: `FlowState` holds entire session state
2. **Separation of Concerns**: Analysis (gate_controller, gate_propagator) separate from UI
3. **Signal-Driven Architecture**: PyQt signals coordinate UI ↔ analysis ↔ UI
4. **Hierarchical Gating**: `GateNode` tree for multi-level populations
5. **Cross-Sample Propagation**: `GatePropagator` applies gate tree to multiple samples in background
6. **Rendering Optimization**: Bitmap caching + event subsampling for interactive responsiveness
7. **Scale-Aware Gates**: Gates stored in raw space, applied in display space
8. **Global Strategy**: Reference gate template for workflow reuse via adaptive repositioning
9. **SOLID Principles**: `CoordinateMapper`, `GateFactory`, `GateOverlayRenderer` for testability
10. **Modeless Windows**: `RenderWindow` for high-quality exports without blocking UI

---

## Next Steps for Development

- **Phase 4 Completion**: Verify cross-sample gate propagation timing (~200ms)
- **Unit Tests**: Service classes (`CoordinateMapper`, `GateFactory`)
- **Integration Tests**: Full workflow (load → gate → propagate → export)
- **Performance**: Profile hexbin rendering with 1M+ events
- **Adaptive Gates**: Implement `Gate.adapt()` for automatic repositioning
- **Scripting API**: Expose analysis layer for programmatic access

---

**Document Generated**: 2026-04-21
**Module**: flow_cytometry v1.0
**BioPro SDK**: Integration Points documented above
