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
│   ├── state.py          # Session state container
│   ├── experiment.py     # Experiment model + workflow templates
│   ├── compensation.py   # Spillover matrix engine
│   ├── transforms.py     # Logicle/log/linear via flowkit
│   ├── gating.py         # Gate types + hierarchical tree
│   ├── statistics.py     # Population statistics
│   └── fcs_io.py         # FlowKit-backed FCS loading
├── ui/                   # GUI VIEW LAYER
│   ├── main_panel.py     # Root workspace widget
│   ├── graph/            # FlowCanvas (matplotlib) + services
│   ├── ribbons/          # Toolbar action components
│   └── widgets/          # Sidebar panels (groups, tree, props)
├── workflows/             # Pre-built workflow templates (JSON)
└── docs/                  # This documentation suite```

---

## 3. The `FlowState` Architecture

Like all BioPro architecture, the module uses a Unidirectional Data Flow. The beating heart of the plugin is `FlowState`.

```python
@dataclass
class FlowState:
    experiment: Experiment
    compensation: CompensationMatrix
    current_sample_id: str
    active_x_param: str
    active_plot_type: str
```

**State is highly segregated from the GUI:**
1. The user clicks a button in `CompensationRibbon`.
2. The ribbon calls pure python math housed in `analysis/compensation.py`.
3. The math returns a generic `CompensationMatrix` dataclass.
4. The ribbon binds that dataclass matrix to `self._state.compensation = new_matrix`.
5. The ribbon calls `self.compensation_changed.emit()`.
6. The main panel hears the emit, calls `.refresh()` on all UI components (which blindly re-read values from `self._state`), and instantly pipes `state_changed` to the BioPro HistoryManager so the state can be saved for Undo/Redo.

---

## 4. BioPro Plugin Contract

The module integrates dynamically into BioPro. It exports `FlowCytometryPanel` satisfying the rigid Core integration APIs:

### 1. `export_state(self) -> dict` 
Emits a lightweight snapshot of UI parameters and small string allocations. Since raw FCS dataframe data is hundreds of megabytes, we do NOT serialize pandas dataframes into the Undo/Redo stack. 

### 2. `load_state(self, state_dict: dict)`
Triggered when the user hits CTRL+Z. Pushes historical parameters back into `FlowState` and forces all graphs and tables to instantly repaint. 

### 3. `export_workflow(self) -> dict`
Used for writing to the disk. Here, we actually serialize paths to the FCS files. 

```python
def to_workflow_dict(self):
    sample_paths = {}
    for sid, sample in self.experiment.samples.items():
        sample_paths[sid] = str(sample.fcs_data.file_path)
    # ...
```

### 4. `load_workflow(self, payload: dict)`
Used for resuming sessions across days. The payload triggers a sequence of `flowkit` parsing calls to reload all physical files recorded in the payload before reconstructing the GUI layout.
## 5. Sub-system Deep Dives

To keep this overview concise, detailed technical documentation for specific sub-systems has been split into dedicated guides:

*   **[API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**: Detailed signatures for the Gating, Transforms, and Scaling modules.
*   **[UI Engine & FSM](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/02_UI_ENGINE.md)**: Explanation of the `FlowCanvas` state machine, layered rendering, and the asynchronous `RenderTask` pipeline.
*   **[Testing & QA](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**: Guidelines for running the unit, integration, and functional test suites.

---

## 🔬 Core References
- **Parks, D.R., et al. (2006)**. A new "Logicle" display method. *Cytometry Part A*.
- **FlowKit Documentation**: https://github.com/whitews/FlowKit
