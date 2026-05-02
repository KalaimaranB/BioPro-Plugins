# Flow Cytometry Module — Architecture

The BioPro flow cytometry module enforces a strict separation of concerns, heavily prioritizing decoupled state management and UI abstraction over monolithic signal-slot spaghetti.

---

## 1. The Core Dependency: FlowKit

Rather than reinventing binary FCS parsers or slow Python-based data transform algorithms, this module wraps **FlowKit**.

*   **FCS Parsing:** `flowkit.Sample` perfectly handles FCS 2.0, 3.0, and 3.1 file parsing inherently dealing with strange byte-orders, string decoding, and instrument metadatas.
*   **C-Extensions:** The performance-critical Logicle and biexponential transforms are handled by the associated compiled `flowutils` backend.

All interactions with FlowKit are constrained strictly to the `analysis/` directory. The UI PyQt6 widgets never import `flowkit`. Instead, they interact entirely through the intermediary `FCSData` and `Experiment` dataclass wrappers.

---

## 2. Directory Structure

```text
flow_cytometry/
├── __init__.py           # Exposes FlowCytometryPanel
├── manifest.json         # BioPro Registry Metadata
├── analysis/             # SCALAR LOGIC ONLY
├── analysis/             # SCALAR LOGIC (No GUI dependencies)
│   ├── state.py          # Session state container
│   ├── experiment.py     # Experiment model + workflow templates
│   ├── scaling.py        # Axis scaling and coordinate math
│   ├── transforms.py     # Logicle/log/linear via flowkit
│   ├── gating/           # Gating logic (Decoupled into types)
│   ├── rendering.py      # Core density/contour math
│   └── services/         # Domain-specific logic (splitters, modifiers)
├── ui/                   # GUI VIEW LAYER
│   ├── graph/            # Matplotlib canvas and rendering layers
│   │   ├── canvas/       # Decoupled Data and Gate layers (SOLID)
│   │   ├── render_panels/# Context-sensitive settings panels
│   │   └── renderers/    # Strategy-based plot renderers
│   ├── widgets/          # Sidebar panels (groups, tree, props)
│   └── main_panel.py     # Root orchestrator
├── workflows/            # Pre-built workflow templates (JSON)
└── docs/                 # Knowledge Hub
```

---

## 3. Layered Graphical Design (SOLID)

To prevent the "God Object" anti-pattern in `FlowCanvas`, the graphical engine is decomposed into three distinct, specialized layers:

1. **Data Layer (`DataLayerRenderer`)**: Responsible for pure event rendering (Pseudocolor, Histogram, etc.). It communicates with the background `RenderTask` to compute densities without blocking the UI thread.
2. **Gate Layer (`GateLayerRenderer`)**: Handles the interactive overlay of gating geometry. It sits on top of the data layer and manages its own artists for performance isolation.
3. **Event Layer (`CanvasEventHandler`)**: Captures mouse/keyboard interaction and drives the `GateDrawingFSM` (Finite State Machine).

This separation ensures that a bug in gate selection doesn't crash the background data rendering pipeline, and vice-versa.

---

## 4. The `FlowState` Architecture

Like all BioPro architecture, the module uses a Unidirectional Data Flow. The beating heart of the plugin is `FlowState`.

```python
@dataclass
class FlowState:
    experiment: Experiment
    render_config: RenderConfig  # Centralized visualization params
    current_sample_id: str
    active_x_param: str
    active_display_mode: DisplayMode
```

**State is highly segregated from the GUI:**
1. The user adjusts a slider in the `PseudocolorSettingsPanel`.
2. The panel updates the `RenderConfig` inside the `FlowState`.
3. The panel emits a `render_settings_changed` signal.
4. The `FlowCanvas` hears the signal, triggers a new `RenderTask` with the updated config, and repaints once the math is finished.

---

## 5. Sub-system Deep Dives

*   **[API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**: Detailed signatures for Gating, Scaling, and Config models.
*   **[UI Engine & Rendering](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/02_UI_ENGINE.md)**: Details on the asynchronous pipeline and strategy-based rendering.
*   **[Testing & QA](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**: Guidelines for the unit and integration test suites.

---

## 🔬 Core References
- **Parks, D.R., et al. (2006)**. A new "Logicle" display method. *Cytometry Part A*.
- **FlowKit Documentation**: [GitHub Link](https://github.com/whitews/FlowKit)
