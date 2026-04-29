# Flow Cytometry Module — Implementation Plan V3
## (Architectural Refactoring & SOLID Hardening)

This plan synthesizes the remaining architectural requirements from the original SDK alignment strategy and the Phase 2 SOLID improvement analysis. 

## Executive Summary
Having stabilized the core logic and fixed the "Critical 10" functional bugs, we now focus on the long-term maintainability of the module. The primary goal is to decompose the current God Classes (`FlowCanvas`, `GateController`, `FlowState`) into a decoupled service-based architecture that utilizes standard design patterns (Strategy, Factory, FSM).

---

## Part 1: Phase-Based Roadmap

### Phase 5: Core Architectural Decoupling (The "Service" Phase)
**Goal**: Eliminate monolithic logic in the analysis layer.

*   **[NEW] `analysis/services/naming.py`**: Extract unique population name generation.
*   **[NEW] `analysis/services/splitter.py`**: Extract population splitting (Boolean logic).
*   **[MODIFY] `analysis/gate_controller.py`**: Refactor to delegate to the new services.
*   **[MODIFY] `analysis/state.py`**: Layer the `FlowState` into:
    *   `ExperimentState`: Data models, compensation, and gate trees.
    *   `ViewState`: UI selections, axis parameters, and display preferences.

### Phase 6: UI Engine Decomposition (The "Canvas" Phase)
**Goal**: Reduce `FlowCanvas` complexity and improve rendering extensibility.

*   **[NEW] `ui/graph/renderers/strategies.py`**: Implement Strategy pattern for display modes (Pseudocolor, Dot Plot, Contour).
*   **[NEW] `ui/graph/gate_drawing_fsm.py`**: Externalize the mouse interaction state machine.
*   **[MODIFY] `ui/graph/flow_canvas.py`**: Refactor as a lightweight coordinator of strategies and the FSM.

### Phase 7: Interface & Signal Hardening
**Goal**: Standardize communication and ensure type safety.

*   **[MODIFY] `analysis/gating.py`**: Standardize `Gate.contains()` return types (LSP compliance).
*   **[MODIFY] `analysis/gate_coordinator.py`**: Split "Fat" signals into `GateEventSource` and `PropagationEventSource` (ISP compliance).
*   **[NEW] `analysis/di.py`**: Implement a simple Dependency Injection container to manage service lifecycles.

### Phase 8: Quality & Performance
**Goal**: Hardening for production and large-scale data.

*   **[MODIFY] `tests/conftest.py`**: Centralize fixtures and remove redundant mocks.
*   **[NEW] `tests/integration/test_gate_flow.py`**: Add end-to-end workflow validation.
*   **[NEW] `tests/performance/test_stress.py`**: Implement profiling for 10M+ event datasets.

---

## Part 2: Success Metrics

- [ ] **SRP**: No class exceeds 300 lines or 20 methods.
- [ ] **OCP**: New display modes or gate types can be added without modifying existing logic classes.
- [ ] **LSP**: All `Gate` subclasses share a strictly compatible `contains()` signature.
- [ ] **ISP**: No single object emits more than 10 unrelated signals.
- [ ] **DIP**: UI components interact with services via interfaces/abstractions, not concrete state attributes.

---

## Part 3: References
- **Parks, D.R., et al. (2006)**: Logicle Transform.
- **BioPro Plugin SDK**: `PluginBase`, `AnalysisBase`, `CentralEventBus`.

*End of V3 Plan*
