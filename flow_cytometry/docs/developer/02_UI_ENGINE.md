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

### Layered Rendering
1.  **Data Layer**: The hexbin density plot or scatter dots. Re-rendered only when axes, transforms, or gates change.
2.  **Gate Layer**: The boundaries and labels of all active gates. Re-rendered when a gate is created, deleted, or moved.
3.  **Overlay Layer**: Real-time feedback (mouse crosshairs, tooltips, drag previews). Re-rendered on every mouse movement.

### Asynchronous `RenderTask`
For operations that take longer than 16ms (like rendering a full 1024x1024 density grid or generating thumbnails for 50 samples), the module uses the `RenderTask` API.
- **Off-thread Processing**: Histogram calculation and image generation are performed in a background worker.
- **Signal-based Completion**: Once the image buffer is ready, a signal updates the UI, preventing main-thread "freezing".

---

## 3. Axis Synchronization & Debouncing

The `GraphWindow` coordinates scaling across multiple tabs.

### Immediate Sync
When a user changes an axis parameter (e.g., FITC-A → PE-A), the `GraphWindow` immediately synchronizes the `AxisScale` object for that channel. This ensures that switching between tabs showing the same channel results in identical visual ranges.

### Render Debouncing
To prevent "flicker" during rapid changes (like typing a scale limit or dragging a slider), the rendering engine uses a 100ms debounce timer. This aggregates multiple update requests into a single high-quality render.

---

## 🔗 Internal Links
- **[API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**
- **[Testing & QA Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**
