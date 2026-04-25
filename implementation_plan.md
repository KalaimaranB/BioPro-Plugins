# Flow Cytometry Module — Refactor & SDK Alignment Plan
## (Updated from Real SDK Source)

## SDK Reality Check

After reading the actual source in `biopro/sdk/core/` and `biopro/core/`, several previous assumptions are corrected:

| Topic | Previous Assumption | Reality |
|-------|-------------------|---------|
| EventBus | Flow module's own `EventBus` class → replace with SDK bus | **Two buses exist**: `biopro.core.event_bus.EventManager` (system-wide, `BioProEvent` enum) and `biopro.sdk.core.events.CentralEventBus` (string-topic, for inter-plugin). Flow's **own** `EventBus` is a third, *internal* bus — keep it for intra-module events, bridge to `CentralEventBus` for cross-plugin |
| TaskScheduler | Inject via constructor for testability | `TaskScheduler` is a **true singleton** (`__new__` pattern). Use `from biopro.core.task_scheduler import task_scheduler`. The right fix is wrapping calls — not injecting |
| FunctionalTask signature | `FunctionalTask(func, name=...)` | Real signature: `FunctionalTask(func, plugin_id, name)` — flow module is calling it wrong |
| PluginState serialization | `asdict()` handles everything | `PluginState.to_dict()` calls `asdict()` — **this breaks on `EventBus`, `AxisScale`, `pd.DataFrame`** fields; these must be excluded |
| PluginBase | Parent class for `MainPanel` | `PluginBase.__init__(plugin_id, parent)` — `MainPanel` currently extends `QWidget` directly, skipping `push_state()`, `undo()`, `cleanup()`, and `CentralEventBus` helpers |
| `AnalysisBase.run(state)` | Generic dict return | Mandatory return type is `dict[str, Any]` — propagation workers must conform |

---

## Critical Bugs (10 found)

| # | File | Bug | Severity |
|---|------|-----|----------|
| 1 | `gate_propagator.py` | `worker.finished.connect(lambda ...)` inside `_execute_propagation` — **new lambda connected on every propagation, never disconnected** | 🔴 Crash |
| 2 | `gate_propagator.py` | Stale closure: outer `task_id` captured by reference across loop iterations — wrong stats applied to wrong sample | 🔴 Data corruption |
| 3 | `group_preview.py` | `FunctionalTask(task_func, name=...)` — **missing `plugin_id` positional arg**; this means `func` is passed as `plugin_id` and `name` as `func`, causing silent `TypeError` in `run()` | 🔴 All thumbnails silently fail |
| 4 | `main_panel.py` | `remove_population(node_id, sample_id)` — **transposed args**; signature is `(sample_id, node_id)` | 🔴 Gate deletion broken |
| 5 | `flow_services.py` `_create_label()` | Accesses `gate.name` then `gate.gate_type.value` — `Gate` base has **neither attribute** | 🔴 All gate labels crash, silently swallowed |
| 6 | `event_bus.py` | `_paused` mode **drops events permanently** — no queue, no flush on `resume()` | 🟠 Silent data loss |
| 7 | `state.py` | `FlowState` inherits `PluginState` which calls `asdict()` in `to_dict()` — **`event_bus`, `experiment` (contains DataFrames), `channel_scales` all fail `asdict()`** | 🟠 Save/undo crash |
| 8 | `graph_window.py` `_open_transform_dialog` | `x_ch`/`y_ch` referenced in inner closure `on_change` after combos can change — **stale capture** | 🟡 Wrong channel persisted |
| 9 | `group_preview.py` | `task_scheduler.task_finished.connect(self._on_task_finished)` — global subscription, **never unsubscribed**, `_on_task_finished` is a no-op | 🟡 Memory leak |
| 10 | `gating.py` `GateNode.to_dict()` | Serializes runtime `statistics` cache — **stale counts persist to disk** | 🟡 Data integrity |

---

## SOLID Violations (SDK-Aligned Fixes)

### SRP — God Objects
- **`flow_canvas.py` (~1,729 lines)**: Rendering, mouse FSM, gate drawing, axis formatting, loading overlay, context menu, parent traversal. Extract `GateDrawingFSM` and display-mode `Renderer` strategies.
- **`graph_window.py` (745 lines)**: Axis population, scale sync, auto-range, breadcrumb, render quality, navigation, transform dialog. Most of this belongs in `AxisManager`.
- **`state.py`**: Domain model (`experiment`) + view state (`channel_scales`, `render_quality`) + infrastructure (`event_bus`) in one dataclass.

### OCP — Hard-coded type chains
- `gating.py:gate_from_dict()` — `if gate_type == "RectangleGate" ... elif ...`. New gate types require modifying this function. Fix: `_GATE_REGISTRY` dict already exists — make `gate_from_dict` use only that.
- `group_preview.py:_draw_gate()` and `flow_services.py:GateOverlayRenderer` — parallel `isinstance` chains for rendering. Fix: add `render_on(ax, mapper)` protocol method to `Gate`.
- `flow_canvas.py` display mode switch — add `DisplayModeRenderer` protocol.

### DIP — Concrete dependencies
- `gate_propagator.py` directly calls `task_scheduler.submit(...)`. Since `TaskScheduler` is a singleton, the fix is wrapping the call in a named method so it can be monkeypatched in tests.
- `flow_canvas.py._auto_range_axes()` walks `parent()` chain to reach `GraphWindow._calculate_auto_range()` — depends on concrete widget hierarchy.
- `group_preview.py` resolves axis scale via local `_resolve_scale()` heuristic instead of using `state.channel_scales` — duplicates `graph_window.py` logic.

### ISP — Fat `FlowState` dependency
Every service, widget, and renderer imports the entire `FlowState`. Narrow the dependency:
- Canvas only needs: `event_bus`, `channel_scales`
- Propagator only needs: `experiment`, `event_bus`
- Thumbnails only need: `experiment`, `channel_scales`, `active_x_param`, `active_y_param`

---

## Proposed Changes — 5 Phases

### Phase 1 — Critical Bug Fixes
*Ship as a hotfix. No architecture changes.*

#### [MODIFY] `analysis/gate_propagator.py`
- Bug #1/#2: Replace inline `lambda` signal connections with a `_PropagationHandler(QObject)` inner class that holds a `task_id` and has a named `on_finished`/`on_error` slot. Connect to the specific worker, not the global scheduler.
```python
class _PropagationHandler(QObject):
    def __init__(self, task_id, callback, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self._callback = callback
    def on_finished(self, results: dict):
        self._callback(self._task_id, results)
```

#### [MODIFY] `ui/widgets/group_preview.py`
- Bug #3: Fix `FunctionalTask` call signature — add `plugin_id`:
```python
# BEFORE (broken):
worker = task_scheduler.submit(FunctionalTask(task_func, name=f"Thumb-{...}"), None)
# AFTER:
task = FunctionalTask(task_func, "flow_cytometry", name=f"Thumb-{...}")
worker = task_scheduler.submit(task, None)
```
- Bug #9: Store subscription reference; call `task_scheduler.task_finished.disconnect(...)` in `closeEvent` / `cleanup`.

#### [MODIFY] `ui/main_panel.py`
- Bug #4: Fix `remove_population(sample_id, node_id)` arg order.

#### [MODIFY] `ui/graph/flow_services.py`
- Bug #5: Fix `_create_label`:
```python
label = getattr(gate, 'name', None) or type(gate).__name__
```

#### [MODIFY] `analysis/event_bus.py`
- Bug #6: Add replay queue for paused mode:
```python
def pause(self): self._paused = True; self._queue = []
def resume(self):
    self._paused = False
    for e in self._queue: self.publish(e)
    self._queue.clear()
```

#### [MODIFY] `analysis/state.py`
- Bug #7: Override `to_dict()` / `from_dict()` to exclude non-serializable fields (`event_bus`, raw DataFrames). Use `to_workflow_dict()` / `from_workflow_dict()` for project persistence.

#### [MODIFY] `analysis/gating.py`
- Bug #10: Remove `statistics` from `GateNode.to_dict()`.

---

### Phase 2 — `MainPanel` → `PluginBase`
*Migrate the plugin entry point to the real SDK contract.*

#### [MODIFY] `ui/main_panel.py`
```python
from biopro.sdk.core import PluginBase, PluginState

class FlowCytometryPanel(PluginBase):
    def __init__(self, plugin_id: str, parent=None):
        super().__init__(plugin_id, parent)   # gets push_state, undo, cleanup, CentralEventBus helpers
        self._state = FlowState()
        ...

    def get_state(self) -> PluginState:
        return self._state   # FlowState.to_dict() must be safe (Phase 1 fix)

    def set_state(self, state: PluginState) -> None:
        self._state = state
        self._refresh_ui_from_state()

    def cleanup(self) -> None:
        super().cleanup()   # ResourceInspector auto-cleans heavy arrays
        self._state.event_bus.unsubscribe_all()  # drain flow's internal bus
```

**Bridge flow's internal `EventBus` to `CentralEventBus`** for cross-plugin notifications (e.g., let BioPro AI know when a gate changes):
```python
# In MainPanel.__init__:
self.subscribe_event("flow.gate_created", ...)   # Uses PluginBase helper → CentralEventBus
```

#### [MODIFY] `analysis/state.py`
- `FlowState` already inherits `PluginState` — validate that after Phase 1 `to_dict()` fix, `push_state()` in `PluginBase` can snapshot it cleanly. Add a test.

---

### Phase 3 — Extract `AxisManager` + `PopulationService`
*Single source of truth for the two most-duplicated logic blocks.*

#### [NEW] `analysis/axis_manager.py`
```python
class AxisManager:
    """Single owner of channel_scales, auto-range, and logicle param estimation."""
    def __init__(self, channel_scales: dict): ...
    def get_scale(self, channel: str) -> AxisScale: ...
    def set_scale(self, channel: str, scale: AxisScale) -> None: ...
    def compute_auto_range(self, channel: str, data: np.ndarray, scale: AxisScale) -> tuple[float, float]: ...
    def apply_logicle_estimation(self, channel: str, data: np.ndarray) -> AxisScale: ...
```
Used by: `GraphWindow`, `GroupPreviewPanel` (replace `_resolve_scale`), `FlowCanvas` (replace parent-chain traversal).

#### [NEW] `analysis/population_service.py`
```python
class PopulationService:
    """Stats computation — single implementation used by controller and propagator."""
    def compute_node_stats(self, node: GateNode, events: pd.DataFrame, total_count: int) -> dict: ...
    def recompute_tree(self, root: GateNode, all_events: pd.DataFrame) -> None: ...
```
`GateController._walk_and_compute` and `GatePropagator._PropagationWorker._walk_tree` both deleted and replaced with delegation to `PopulationService`.

---

### Phase 4 — Shared `RenderPipeline` + `AnalysisBase` propagator
*Eliminate the two biggest code duplications.*

#### [NEW] `analysis/render_pipeline.py`
Single pseudocolor/histogram renderer implementing `AnalysisBase`:
```python
class FlowRenderTask(AnalysisBase):
    """AnalysisBase subclass — runs off-thread via task_scheduler.submit()."""
    def run(self, state: FlowRenderState) -> dict:
        # density histogram → gaussian smooth → rankdata → rgba buffer
        return {"buffer": rgba_bytes, "width": w, "height": h}
```
- `FlowCanvas` main render path calls `task_scheduler.submit(FlowRenderTask(...), render_state)` and shows spinner.
- `render_preview_to_buffer()` in `group_preview.py` **replaced** by `FlowRenderTask`.
- Eliminates the duplicated pseudocolor pipeline between canvas and thumbnails.

#### [MODIFY] `analysis/gate_propagator.py`
Replace `_PropagationWorker` manual `QThread` with `AnalysisBase` + `task_scheduler`:
```python
class GatePropagationAnalyzer(AnalysisBase):
    def run(self, state: PropagationState) -> dict:
        population_service = PopulationService()
        results = {}
        for sample_id, sample in state.experiment.samples.items():
            try:
                population_service.recompute_tree(sample.gate_tree, sample.fcs_data.events)
                results[sample_id] = "ok"
            except Exception as e:
                results[sample_id] = str(e)   # granular per-sample error
        return results
```
`GatePropagator._execute_propagation` becomes:
```python
task = GatePropagationAnalyzer("flow_cytometry")
worker = task_scheduler.submit(task, prop_state)
handler = _PropagationHandler(worker, self._on_propagation_done)  # named slot, no leak
```

---

### Phase 5 — OCP Gate Registry + FSM Extraction
*Extensibility and `FlowCanvas` decomposition.*

#### [MODIFY] `analysis/gating.py`
Make `_GATE_REGISTRY` the **only** deserialization path; remove the `if/elif` chain in `gate_from_dict`:
```python
def gate_from_dict(data: dict) -> Gate:
    cls = _GATE_REGISTRY.get(data.get("type"))
    if not cls: raise ValueError(f"Unknown gate type: {data['type']!r}")
    return cls.from_dict(data)   # each Gate subclass implements from_dict()
```

#### [NEW] `ui/graph/gate_drawing_fsm.py`
Extract the mouse-event state machine from `FlowCanvas` (~400 lines):
```python
class GateDrawingFSM:
    """Finite state machine: IDLE → DRAWING → COMPLETE."""
    def on_press(self, x, y): ...
    def on_move(self, x, y): ...
    def on_release(self, x, y): ...
    def on_double_click(self, x, y): ...
    gate_committed: Signal  # emitted with completed Gate object
```
`FlowCanvas` becomes a thin coordinator holding `GateDrawingFSM` + `GateOverlayRenderer`.

#### [MODIFY] `ui/graph/flow_services.py`
Fix Bug #5, then add a `render_overlay(ax, mapper)` dispatch method that replaces all `isinstance` chains using `_OVERLAY_RENDERERS` dict (OCP fix).

---

## New Files Summary

| File | Phase | Purpose |
|------|-------|---------|
| `analysis/axis_manager.py` | 3 | Single axis scale registry |
| `analysis/population_service.py` | 3 | Deduplicated stats computation |
| `analysis/render_pipeline.py` | 4 | Shared `AnalysisBase` renderer |
| `ui/graph/gate_drawing_fsm.py` | 5 | Mouse FSM extracted from FlowCanvas |

---

## Open Questions

> [!IMPORTANT]
> **Q1: `MainPanel` currently receives no `plugin_id` from the host loader.**  
> `PluginBase.__init__(plugin_id, parent)` requires a `plugin_id`. The host calls `get_panel_class()()` with no args. Do we add a default `plugin_id="flow_cytometry"` or update the host's loader call?

> [!IMPORTANT]
> **Q2: Phase 4 makes `FlowCanvas` rendering async (off-thread).**  
> Currently canvas rendering blocks the UI with a spinner. Moving to `task_scheduler.submit()` means we need to handle cancellation when the user changes axes before the render completes. Acceptable complexity or keep canvas synchronous?

> [!NOTE]
> **Q3: Phase ordering preference.**  
> Phase 1 (10 bug fixes) can ship immediately. Should Phases 2–5 be a single PR or sequential?

---

## Verification Plan

| Phase | Test |
|-------|------|
| 1 | Existing test suite passes; new regression tests for each of the 10 bugs |
| 2 | `push_state()` round-trips `FlowState` without exception; undo/redo moves state correctly |
| 3 | `PopulationService` unit tests with synthetic gate trees; `AxisManager` unit tests for each transform type |
| 4 | Pixel diff between `FlowRenderTask` output and current canvas render < 2% for same data |
| 5 | Draw/rename/delete 50 gates across 5 samples without listener count growth (check via `_listeners` dict) |
