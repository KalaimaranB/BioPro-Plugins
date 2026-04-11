# Flow Cytometry Module Architecture

This document describes the orchestration, data flow, and rendering architecture of the BioPro Flow Cytometry plugin.

## 1. System Overview

The module follows a **Model-Controller-View (MCV)** pattern, optimized for high-throughput single-cell data analysis. It decouples expensive numerical operations (filtering, statistics, propagation) from the UI thread to ensure a fluid user experience even with datasets exceeding 1,000,000 events.

### Core Components

| Component | Responsibility |
| :--- | :--- |
| `FlowCytometryPanel` | Root UI container and BioPro API endpoint. |
| `GateController` | State manager for gate CRUD operations and statistics logic. |
| `GatePropagator` | Multi-threaded engine for cross-sample population synchronization. |
| `GraphManager` | Coordinator for multiple `GraphWindow` instances. |
| `FlowCanvas` | High-performance rendering engine using dual-layer bitmap caching. |

---

## 2. The Data Flow Pipeline

1.  **Ingestion**: `FCS` files are parsed using `fcs_io.py`. Data is stored in `pandas.DataFrame` format for vectorized processing.
2.  **Compensation**: A linear transformation is applied to correction spillover between fluorescent channels.
3.  **Gating**: Events are filtered through a hierarchical `GateNode` tree. Each node stores a boolean mask relative to its parent.
4.  **Transformation**: Raw data is mapped to display coordinates (Linear, Log, or Logicle) in `transforms.py`.
5.  **Rendering**: The `FlowCanvas` processes the filtered, transformed data into a visual density map.

---

## 3. Visual Rendering Engine

To achieve interactive gating (dragging/resizing gates on 500k+ points), the system uses a **Dual-Layer Rendering** strategy.

### Layer 1: The Data Layer (Raster)
The scatter plot or density map is rendered first. Because this is computationally expensive (KDE/Pseudocolor calculation), the resulting axes area is captured as a **bitmap cache**.
- **Update Frequency**: Only when the sample, parent gate, or axis channels change.
- **Optimization**: Uses `rasterized=True` in Matplotlib to prevent SVG overhead.

### Layer 2: The Gate Layer (Vector)
Gate outlines, handles, and labels are drawn as vector graphics on top of the cached bitmap.
- **Update Frequency**: On every mouse move (dragging, resizing).
- **Optimization**: Uses `canvas.copy_from_bbox` and `blit` to redraw only the dynamic overlays without re-rendering the scatter data.

---

## 4. Parallelization & Threading

The UI remains responsive during heavy analysis task by offloading work to background workers:

- **Propagation Workers**: When "Apply Gates to All" is clicked, a background thread builds the new gate hierarchy for every sample in the group.
- **Atomic Signal Swapping**: Workers communicate results via signals. The UI only updates (swaps state) when the entire batch computation is complete, preventing "flicker" or partial state corruption.
- **Lazy Statistics**: Statistics like `%-Parent` and `Event Count` are calculated only when a population is viewed or explicitly requested for a report.
