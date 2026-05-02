# Developer Guide — UI Engine & FSM

This document explains the internal mechanics of the `FlowCanvas`, its Finite State Machine (FSM) for mouse interaction, and the asynchronous rendering pipeline.

## 1. The `FlowCanvas` State Machine

To handle complex mouse interactions (drawing polygons, moving gates, zooming) without nested conditional logic, `FlowCanvas` utilizes an internal state machine defined by the `CanvasState` enum.

### Interaction States
- `IDLE`: Default state. Mouse movement highlights nearby gates.
- `DRAW_RECT` / `DRAW_ELLIPSE`: Active click-and-drag for region definition.
- `DRAW_POLY`: Sequential point placement for arbitrary shapes.
- `MOVE_GATE`: Dragging an existing gate boundary or center.
- `ZOOM`: Rubber-band zoom region selection.

### Event Handling
Each state transition is managed by the `_on_mouse_press`, `_on_mouse_move`, and `_on_mouse_release` handlers. State-specific drawing (like the red dashed outline of a polygon-in-progress) is performed in the `_render_overlay_layer` method.

---

## 2. Rendering Pipeline

BioPro Flow Cytometry uses a multi-layered rendering approach to maintain 60 FPS interactivity even with large datasets.

### Layered Rendering (SOLID)
Since the refactor, the `FlowCanvas` no longer manages rendering logic directly. Instead, it delegates to specialized layer classes:
1.  **Data Layer (`DataLayerRenderer`)**: Handles heavy-duty event rendering and coordinates with the background `RenderTask`.
2.  **Gate Layer (`GateLayerRenderer`)**: Manages the life-cycle of gate artists and labels.
3.  **Event Handler (`CanvasEventHandler`)**: Orchestrates the interaction logic and drives the state machine.

---

## 3. Visualization Settings System

The module features a non-modal **Render Settings** system that allows real-time visual tweaking.

### Context-Sensitive Panels
The `RenderSettingsDialog` dynamically switches its interface based on the active `DisplayMode`. Each plot type has a dedicated configuration panel:
- `PseudocolorSettingsPanel`: Controls for rank-percentile density, point size, and smoothing.
- `HistogramSettingsPanel`: Controls for binning and KDE smoothing.
- `DotPlotSettingsPanel`: Simple scatter size and color controls.

### Preset Integration
Settings panels include high-level presets (**Standard**, **Publication**, **Fast Preview**) that bundle multiple parameters (smoothing, detail, point size) to achieve professional aesthetics in one click.

---

## 🔗 Internal Links
- **[Architecture & SOLID Design](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/00_ARCHITECTURE_OVERVIEW.md)**
- **[API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**
- **[Testing & QA Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**
