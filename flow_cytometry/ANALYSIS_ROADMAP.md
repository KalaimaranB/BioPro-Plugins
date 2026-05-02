# Flow Cytometry Analysis — Implementation Roadmap

This document outlines the phased implementation plan for turning the
scaffolded Flow Cytometry module into a fully working analysis tool.

> **Design Principles**
> - Use existing, validated libraries — don't reinvent algorithms.
> - `flowkit` (+ `flowutils`, `flowio`) for FCS I/O, transforms (Logicle), and compensation.
> - `matplotlib` embedded via `FigureCanvasQTAgg` for plotting + interactive gate drawing.
> - Cross-sample gate propagation is a **core requirement**, not a bonus.
> - Adaptive gating is a **future bonus** — deprioritised.

---

## Dependencies (added to BioPro Core)

| Package | Purpose |
|---------|---------|
| `flowkit` | FCS reading, Logicle/biex transforms, compensation, GatingML |
| `flowio` | Low-level FCS parsing (dependency of flowkit) |
| `flowutils` | C-extension transforms (dependency of flowkit) |
| `numpy` | Numerical ops |
| `pandas` | DataFrame handling |
| `matplotlib` | Embedded canvas + gate drawing |
| `scipy` | KDE for density plots, peak detection |

---

## Phase 1 — See Your Data ✅ DONE

**Goal**: Load real FCS files and render interactive plots.

### Steps

1. **Refactor `fcs_io.py`** — replace raw `fcsparser` with `flowkit.Sample`.
   FlowKit handles FCS 2.0/3.0/3.1, metadata parsing, and channel
   naming automatically.

2. **Refactor `transforms.py`** — replace the asinh stub biexponential
   with `flowkit.transforms.LogicleTransform` (the real Parks 2006
   algorithm with C extensions). Keep Linear and Log as lightweight
   wrappers.

3. **Build `FlowCanvas`** — a `FigureCanvasQTAgg` subclass in
   `ui/graph/flow_canvas.py` that:
   - Renders scatter (dot) plots, pseudocolor (hexbin), contour,
     density, and histogram views.
   - Receives axis selection from `GraphWindow` dropdowns.
   - Supports mouse events for future gate drawing (Phase 3).

4. **Wire `GraphWindow` → `FlowCanvas`** — connect axis combo changes
   and display mode changes to canvas redraws.

5. **Wire `WorkspaceRibbon` "Add Samples"** — file dialog → load FCS
   via `flowkit.Sample` → populate `Experiment.samples` → refresh tree.

6. **Wire `SampleTree` double-click → graph** — clicking a sample opens
   a graph tab showing FSC-A vs SSC-A.

### Deliverable
Load one or more FCS files, see them in the sample tree with correct
event counts, and interact with real scatter/pseudocolor plots using
axis dropdowns and transform toggles.

---

## Phase 2 — Compensation ✅ DONE

**Goal**: Compute and apply spillover matrices.

### Steps

1. **Implement `calculate_spillover_matrix()`** — use `flowkit.Matrix`
   or manual median-ratio algorithm from single-stain controls.
2. **Spillover matrix editor** — editable table widget showing the N×N
   matrix with fluorochrome labels.
3. **Apply compensation** — `flowkit.Sample.apply_compensation()` or
   our matrix inverse path. Mark samples as compensated.
4. **Auto-detect from FCS** — read `$SPILL` / `$SPILLOVER` keywords
   from FCS metadata and offer to apply.

### Deliverable
Import or compute a compensation matrix, view/edit it, apply to all
samples, see the effect on plots in real time.

---

## Phase 3 — Interactive Gating ✅ DONE

**Goal**: Draw gates directly on the matplotlib canvas.

### Steps

1. **Gate drawing tools** — implement mouse-event handlers on
   `FlowCanvas` for Rectangle, Polygon, Ellipse, Range gates.
   - Press → drag → release for Rectangle/Ellipse.
   - Click-click-click-double-click for Polygon.
   - Click-drag for Range (1-D histogram).
2. **Gate overlay rendering** — draw gate boundaries as matplotlib
   patches with alpha fills.
3. **Gate tree updates** — new gate → add `GateNode` child → refresh
   sample tree with event counts.
4. **QuadrantGate** — crosshair tool that divides the plot into 4
   quadrants with draggable midpoint.
5. **Gate editing** — click an existing gate patch to select it,
   drag handles to resize.

### Deliverable
Draw any gate type on a plot, see it appear in the sample tree with
correct event count and %parent, and navigate the gating hierarchy
via breadcrumbs.

---

## Phase 4 — Cross-Sample Gate Propagation (Required) ✅ DONE

**Goal**: When a gate is moved on one sample, all other samples update
their statistics in real time.

### Steps

1. **GatePropagator** — background worker (`QThread` or `QRunnable`)
   that re-applies the gate tree to all samples in a group when a gate
   changes.
2. **Debounced updates** — while the user is dragging a gate, batch
   re-computation calls with a ~200ms debounce timer.
3. **Statistics panel live update** — the properties panel and sample
   tree event counts refresh as propagation completes.
4. **Visual feedback** — mini-stat badges on each sample tree node
   update in real time (count, %parent).

### Deliverable
Move a gate on sample A, see samples B, C, D update their event
counts and %parent in the tree and properties panel within ~200ms.

---

## Phase 5 — Marker Awareness & Sample Tracking ← **CURRENT**

**Goal**: Solve the "which sample has which marker" problem.

### Steps

1. **Persistent marker badges** — colored tags on sample tree nodes.
2. **Missing-control warnings** — if the workflow expects an FMO but
   none is assigned, highlight the sample slot.
3. **Auto-label axes** — if a channel has a mapped marker, show
   "CD4 (FITC)" instead of "FL1-A".
4. **FMO auto-gating** — use FMO-minus sample's 99th percentile as
   the gate boundary for the missing marker. Not adaptive — just a
   one-shot threshold calculator.

### Deliverable
Clear marker identity throughout the UI, auto-axis labels, missing
control warnings, and one-click FMO gate boundaries.

---

## Phase 6 — Reports & Batch Export

**Goal**: Publication-ready output.

### Steps

1. **Table editor** — customizable columns (population, stat, parameter).
2. **CSV export** — all statistics for all populations.
3. **PDF/PNG export** — publication-quality figures with proper labels.
4. **Batch processing** — apply a gating strategy across all samples
   in a group and export results.

### Deliverable
Export a CSV with Mean, MFI, CV, %Parent for every population across
every sample. Generate a multi-panel figure for publication.

---

## Phase 7 (Bonus) — Adaptive Gating

**Goal**: Gates auto-adjust to new datasets.

### Steps

1. **KDE-based repositioning** — for each adaptive gate, compute KDE
   on the new sample's data, find the nearest density valley, and
   shift the gate boundary.
2. **Preserve topology** — gate shape and relative position are
   maintained, only the absolute coordinates shift.
3. **Confidence indicator** — show how much the gate moved and flag
   large shifts for manual review.

### Deliverable
Apply a saved workflow template to new data and have gates
automatically adjust with visual confirmation.

---

## Phase 8 — Advanced Features
- **Boolean Gate Combinations** — Implement logic for AND, OR, and NOT gate intersections.
- **Backgating Overlays** — Support visualizing a sub-population's distribution across the entire gating tree.
- **Dimensionality Reduction** — Integration with `tSNE` and `UMAP` for high-parameter discovery.
- **Clustering** — Automated population discovery via `Leiden` or `Louvain` (scanpy integration).
- **Workspace Interoperability** — Import/Export via FlowJo (`flowkit.Workspace`) and GatingML 2.0.

---

## Phase 9 — High-Performance Pipeline
**Goal**: Ensure zero-latency UI even with 10M+ event datasets.

1. **Multi-threaded Rendering** — Move all density/contour calculations to a background thread pool (TaskScheduler).
2. **Result Caching** — Cache computed density grids so changing visualization parameters (color/size) doesn't require a re-calculation.
3. **Hardware Acceleration** — Explore GPU-accelerated density estimation for real-time contour updates.

---

## Phase 10 — State Integrity & Refactoring
**Goal**: Finalize the SOLID architecture and remove technical debt.

1. **Remove Backward Compatibility** — Purge the `FlowState` proxy properties once the new nested dataclass pattern is stabilized.
2. **Unified Coordinate Mapping** — Enforce the `CoordinateMapper` as the single source of truth for all raw-to-display conversions across main plots and subplots.
3. **Systematic Testing** — Achieve 95% unit test coverage for `analysis/gating` and `analysis/transforms`.
