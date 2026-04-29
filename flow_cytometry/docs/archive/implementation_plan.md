# Left Panel UI Split & FlowJo Auto-Transforms

This plan covers completely restructuring the left sidebar to separate Samples from the Gating Strategy, and implementing FlowJo-style intelligence when double-clicking gates to view sub-populations.

## User Review Required

> [!IMPORTANT]
> **Global vs Current Gating**: Currently, gates are physically attached to specific samples in our data structure. When you toggle to "Global" in the new Gates tab, we will display a unified tree (likely mirroring the first sample's tree). Modifying a gate in "Global" mode will automatically trigger the propagator to push that change to all samples instantly.

## Proposed Changes

### 1. UI Restructure: Separating Samples and Gates
We will replace the unified `SampleTree` with a `QTabWidget` containing two separate panels:

#### [NEW] [sample_list.py](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/ui/widgets/sample_list.py)
A flat list view displaying only the samples and their total event counts. 
- Double-clicking opens the raw (ungated) sample graph.
- Clicking once selects the sample (driving the properties panel and the "Current Sample" view of the Gates tab).

#### [NEW] [gate_hierarchy.py](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/ui/widgets/gate_hierarchy.py)
A dedicated tree view displaying only the gating hierarchy.
- **Top Toggle**: A segment button to switch between `[ Current Sample | Global Strategy ]`.
  - **Current**: Shows gates for the sample selected in the Samples tab.
  - **Global**: Shows the layout as a template. Changes made here instantly automatically propagate to the entire group.
- **Bottom Action**: An "Apply to All" button to forcefully sync the current sample's gates across the group.

#### [DELETE] [sample_tree.py](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/ui/widgets/sample_tree.py)
Will be completely removed and replaced by the two new widgets. 
`main_panel.py` will be updated to orchestrate the signals between these two new tabs and the graph manager.

---

### 2. FlowJo "Smarts": Auto-Zoom and Smart Channels
When double-clicking a gate in the new Gates Tab, we will open a new `GraphWindow` with intelligent defaults.

#### [MODIFY] [graph_window.py](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/ui/graph/graph_window.py)
- **Smart Channel Guessing**: In `_populate_axis_combos`, if we detect that the newly opened graph restricts data to a gate, we will check the gate's defined channels. If the gate was drawn on Scatter (`FSC` / `SSC`), we will intelligently default the new plot to the *first two fluorescent markers* (e.g., FITC, PE) instead of showing FSC/SSC again.
- **Auto-Scale (Zoom)**: In `_render_initial`, if a gate is applied, we will calculate the 1st and 99th percentiles of the data *inside the gate*. We will then temporarily override the `AxisScale.min_val` and `max_val` for this specific graph. This provides the FlowJo "zoom" effect without irreparably messing up the globally-synced axis transformation limits.

## Open Questions

None at this time. The plan covers both your requests exactly.

## Verification Plan

### Manual Verification
1. **Layout**: Confirm the left sidebar has two distinct tabs: "Samples" and "Gates".
2. **Global Syncing**: Switch to the "Global" toggle, draw a gate, and verify it populates down to all samples without having to click "Copy".
3. **Smart Channels**: Draw a gate on FSC-A vs SSC-A, double click it. Verify the new tab defaults to fluorescent channels (e.g., FITC/PE).
4. **Auto-Zoom**: Verify the new tab's plot is zoomed tightly around the gated population (limits dynamically adjusted).
