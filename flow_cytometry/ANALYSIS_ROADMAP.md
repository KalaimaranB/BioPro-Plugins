# Flow Cytometry Analysis — Implementation Roadmap

This document outlines the phased implementation plan for turning the Flow Cytometry module into a fully working, premium analysis tool.

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

## 🏁 Phase Progress Overview

- [x] **Phase 1: See Your Data** — *Complete*
- [x] **Phase 2: Compensation** — *Complete*
- [x] **Phase 3: Interactive Gating** — *Complete*
- [x] **Phase 4: Cross-Sample Gate Propagation** — *Complete*
- [x] **Phase 5: State Integrity & Premium SDK Alignment** — *Complete* (New!)
- [/] **Phase 6: Marker Awareness & Sample Tracking** — *In Progress*
- [ ] **Phase 7: Reports & Batch Export** — *Planned*
- [ ] **Phase 8: Advanced Features** — *Planned*
- [ ] **Phase 9: High-Performance Pipeline** — *Planned*

---

## Phase 1 — See Your Data ✅ DONE

**Goal**: Load real FCS files and render interactive plots.

1. **Refactor `fcs_io.py`** — replaced raw `fcsparser` with `flowkit.Sample`.
2. **Refactor `transforms.py`** — implemented Parks 2006 Logicle algorithm via `flowkit.transforms`.
3. **Build `FlowCanvas`** — a custom Matplotlib canvas for dot plots, pseudocolor, histograms, etc.
4. **Wire UI Controls** — connected axis dropdowns and display mode changes to canvas redraws.
5. **Sample List Integration** — wired file imports and double-clicking to open plots.

---

## Phase 2 — Compensation ✅ DONE

**Goal**: Compute and apply spillover matrices.

1. **Calculate Spillover** — added single-stain control calculation algorithms.
2. **Spillover Table Editor** — created an interactive matrix editor with fluorochrome labels.
3. **Apply Compensation** — integrated matrix application with real-time plot updates.
4. **Embedded Keywords** — auto-detects and loads `$SPILL` / `$SPILLOVER` metadata.

---

## Phase 3 — Interactive Gating ✅ DONE

**Goal**: Draw and edit gates directly on the Matplotlib canvas.

1. **Interactive Tools** — implemented mouse-handlers for Rectangle, Polygon, Ellipse, and Range gates.
2. **Visual Patches** — rendered real-time preview boundaries with alpha fills.
3. **Gate Tree Propagation** — new gates update the `GateNode` tree hierarchy.
4. **QuadrantGating** — added draggable 4-quadrant gating crosshairs.
5. **Instant Canvas Abort** — escape keys immediately abort drawing and clear preview states across subplots.

---

## Phase 4 — Cross-Sample Gate Propagation ✅ DONE

**Goal**: Re-apply gate modifications across all group samples seamlessly.

1. **GatePropagator** — background processing worker for real-time propagation.
2. **Debounced Updates** — added a ~200ms debounce during dragging to prevent UI lag.
3. **Live Statistics** — automatic properties and tree stat badges update instantly.

---

## Phase 5 — State Integrity & Premium SDK Alignment ✅ DONE (New!)

**Goal**: Align fully with BioPro core architectural guidelines and ensure reliable Undo/Redo and diagnostics.

1. **Premium Logging** — Migrated 100% of standard Python loggers across all 35 source files to the context-aware SDK `get_logger`.
2. **Time Machine Compatibility** — Added a complex `from_dict()` classmethod to `FlowState` to re-establish strong domain-object nesting during history pops, resolving critical `AttributeError` crashes in the Undo/Redo stack.
3. **Smart Transform Defaulting** — Implemented axis scale inheritance, ensuring that switching channels inherits the previous scale type instead of resetting to `linear`, while fully preserving customized memory.
4. **Synchronized Preview Clearing** — Wired cancellation events to immediately dispatch `GATE_PREVIEW = None` across the `CentralEventBus` to clear remnants on subplots instantly.

---

## Phase 6 — Marker Awareness & Sample Tracking  IN PROGRESS

**Goal**: Solve the "which sample has which marker" problem.

1. **Persistent Marker Badges** — colored tags on sample tree nodes indicating channel configurations.
2. **Missing-Control Warnings** — highlight missing FMO slots expected by the current workflow template.
3. **Smart Axis Labels** — display mapped markers (e.g., `"CD4 (FITC)"`) instead of generic laser channels (e.g., `"FL1-A"`).
4. **FMO Auto-Gating** — one-shot boundary thresholding utilizing the 99th percentile of FMO-minus controls.

---

## Phase 7 — Reports & Batch Export

**Goal**: Support high-quality figures and batch exports.

1. **Custom Statistics Table** — column customization for populations, statistics, and markers.
2. **CSV Export** — batch export of event counts, MFI, CV, and %parent values across all samples.
3. **Publication Figures** — export high-DPI PDF/PNG plots with perfect vector annotations.
4. **Group Gating Strategy** — one-click strategy batching across group templates.

---

## Phase 8 — Advanced Features

**Goal**: High-parameter discovery.

1. **Boolean Gates** — logical operations (AND, OR, NOT) on existing populations.
2. **Backgating Overlays** — visualize sub-population profiles across parent gates.
3. **Dimensionality Reduction** — integrate `tSNE` and `UMAP` projection pipelines.
4. **Automated Clustering** — population discovery via Leiden/Louvain algorithms.
5. **Third-Party Interoperability** — support GatingML 2.0 import/export.

---

## Phase 9 — High-Performance Pipeline

**Goal**: Smooth, latency-free rendering for large-scale datasets (10M+ events).

1. **Multi-threaded Density Estimation** — offload hexbin/KDE calculations to `TaskScheduler`.
2. **Subplot Grid Caching** — cache grid calculations to optimize redraw performance.
3. **GPU-Accelerated KDE** — investigate hardware acceleration for real-time contours.
