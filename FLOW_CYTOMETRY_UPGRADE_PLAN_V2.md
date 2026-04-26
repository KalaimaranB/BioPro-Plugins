# Flow Cytometry Module - Comprehensive Upgrade Plan

**Date:** April 25, 2026  
**Version:** 2.0  
**Scope:** Full architectural overhaul, bug fixes, SDK alignment, and documentation

---

## Executive Summary

The current flow_cytometry module suffers from architectural debt that manifests as hidden bugs, code duplication, SOLID violations, and unclear data flow. This plan provides a comprehensive roadmap to transform the module into a maintainable, scalable, and well-documented system aligned with the BioPro SDK patterns.

### Key Problems Identified

| Problem | Impact | Root Cause |
|---------|--------|------------|
| Multiple sources of truth | State desync, hidden bugs | FlowState + EventBus + direct sample manipulation |
| SOLID violations | Hard to extend, test, debug | GateController does too much; UI touches data directly |
| Custom EventBus | Redundant with SDK | Parallel implementation to CentralEventBus |
| No clear service layer | Tight coupling | Analysis logic mixed with UI |
| Hidden bugs | Crashes, data corruption | Missing null guards, race conditions |
| Poor documentation | Onboarding difficulty | Architecture decisions not recorded |

---

## Part 1: Current Architecture Analysis

### 1.1 Existing Documentation

- **[FLOW_CYTOMETRY_ARCHITECTURE.md](FLOW_CYTOMETRY_ARCHITECTURE.md)** — Documents UI components, gating architecture, rendering system
- **[FLOW_CYTOMETRY_IMPLEMENTATION_PLAN.md](FLOW_CYTOMETRY_IMPLEMENTATION_PLAN.md)** — Contains 8 UX improvements + 1 critical bug fix

### 1.2 Current Code Structure

```
flow_cytometry/
├── analysis/           # Analysis logic (SHOULD be SDK-aligned)
│   ├── state.py        # FlowState (extends PluginState) ✓
│   ├── event_bus.py    # Custom EventBus ⚠️ (should use CentralEventBus)
│   ├── gate_controller.py  # Does too much ⚠️
│   ├── gate_propagator.py  # Cross-sample logic
│   ├── population_service.py
│   ├── gating.py       # Gate definitions
│   ├── statistics.py
│   ├── compensation.py
│   ├── transforms.py
│   ├── scaling.py
│   ├── axis_manager.py
│   ├── experiment.py   # Data model
│   └── fcs_io.py       # File I/O
├── ui/
│   ├── main_panel.py   # Root widget (extends PluginBase) ✓
│   ├── graph/          # Canvas rendering
│   ├── widgets/        # Sidebar components
│   └── ribbons/        # Toolbar tabs
└── tests/
```

### 1.3 SDK Alignment Status

| SDK Component | Current Usage | Status |
|---------------|---------------|--------|
| `PluginBase` | Used in main_panel.py | ✓ Good |
| `PluginState` | FlowState extends it | ✓ Good |
| `CentralEventBus` | NOT USED — custom EventBus | ⚠️ Migrate |
| `AnalysisBase` | NOT USED — ad-hoc classes | ⚠️ Adopt |
| `AnalysisWorker` | NOT USED — manual threading | ⚠️ Adopt |
| `PluginConfig` | NOT USED — ad-hoc config | ⚠️ Adopt |

---

## Part 2: Target Architecture

### 2.1 Principles

1. **Single Source of Truth**: FlowState is the only mutable state container
2. **Event-Driven**: All state changes flow through CentralEventBus
3. **Service Layer**: Analysis logic isolated in services, not UI
4. **SDK Alignment**: Use BioPro SDK components where available
5. **Dependency Inversion**: UI depends on abstractions, not concretions

### 2.2 Proposed Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      UI Layer (PyQt6)                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ MainPanel   │ │ GraphCanvas │ │ Widgets (Tree, List)    ││
│  └──────┬──────┘ └──────┬──────┘ └───────────┬─────────────┘│
│         │               │                     │              │
│         └───────────────┼─────────────────────┘              │
│                         ▼                                    │
│              ┌────────────────────┐                          │
│              │   UI Controllers   │  ← Thin, event-forwarding│
│              │ (Presenter pattern)│                          │
│              └──────────┬─────────┘                          │
└─────────────────────────┼────────────────────────────────────┘
                          │ events only
┌─────────────────────────┼────────────────────────────────────┐
│              Service Layer (Pure Python)                     │
│              ┌──────────┴─────────┐                          │
│              │  GateCoordinator   │  ← Single entry point    │
│              │  (Facade pattern)  │    for gating operations │
│              └──────────┬─────────┘                          │
│    ┌────────────────────┼────────────────────┐               │
│    ▼                    ▼                    ▼               │
│ ┌──────────┐    ┌──────────────┐    ┌─────────────┐         │
│ │GatingSvc │    │PopulationSvc │    │StatsService │         │
│ └──────────┘    └──────────────┘    └─────────────┘         │
└─────────────────────────┬────────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────────┐
│                   Data Layer                                  │
│              ┌──────────┴─────────┐                          │
│              │     FlowState      │  ← Single source of truth│
│              │   (PluginState)    │    + CentralEventBus     │
│              └────────────────────┘                          │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Key Architectural Changes

#### Change 1: Replace Custom EventBus with CentralEventBus

**Current:**
```python
# flow_cytometry/analysis/event_bus.py
from .event_bus import EventBus, EventType
self._state.event_bus.publish(Event(type=EventType.GATE_CREATED, ...))
```

**Target:**
```python
# Use SDK's CentralEventBus
from biopro.sdk.core.events import CentralEventBus
CentralEventBus.publish("flow.gate_created", {"sample_id": "...", ...})
```

**Migration Strategy:**
1. Create adapter layer that bridges old EventType → CentralEventBus topics
2. Gradually migrate publishers one at a time
3. Remove custom EventBus after full migration

#### Change 2: Consolidate GateController → GateCoordinator

**Current (violates SRP):**
- GateController: add/delete/rename gates + compute stats + trigger propagation

**Target:**
```
GateCoordinator (Facade)
├── GatingService     # Gate CRUD operations
├── PopulationService # Already exists, keep
├── StatisticsService # Compute stats (moved from controller)
└── PropagationService # Cross-sample (from GatePropagator)
```

#### Change 3: Add UI Controllers (Presenter Pattern)

**Current:**
- UI widgets directly manipulate FlowState
- Example: `sample_list.py` calls `state.experiment.samples.pop()`

**Target:**
- UI emits signals only
- Controllers handle state mutations
- Example: `sample_list.selection_changed → Controller → FlowState`

#### Change 4: Adopt AnalysisBase for Heavy Computation

**Current:**
- Rendering runs on main thread or ad-hoc workers
- Statistics computed synchronously in GateController

**Target:**
```python
from biopro.sdk.core import AnalysisBase

class StatisticsAnalysis(AnalysisBase):
    """Background computation of gate statistics."""
    
    def run(self, state: FlowState, gate_ids: list[str]) -> dict:
        # Heavy computation runs in worker thread
        return {gate_id: stats for gate_id in gate_ids}
```

---

## Part 3: Bug Fixes (Critical Path)

### 3.1 Critical Bugs to Fix Immediately

| # | Bug | File | Fix |
|---|-----|------|-----|
| B1 | NoneType crash in sample list selection | `ui/widgets/sample_list.py:182` | Add null guard: `if current is None: return` |
| B2 | Gate stats not updating after rename | `gate_controller.py` | Emit `gate_stats_updated` after rename |
| B3 | Render cache not invalidated on transform change | `ui/graph/flow_canvas.py` | Clear cache in `_on_transform_changed` |
| B4 | EventBus not thread-safe | `analysis/event_bus.py` | Add locks or migrate to CentralEventBus |
| B5 | Memory leak on sample unload | `main_panel.py` | Call cleanup on sample data |

### 3.2 Fix Implementation

```python
# B1: sample_list.py - Add null guard
def _on_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
    if current is None:  # ← ADD THIS GUARD
        return
    sample_id = current.data(0, Qt.ItemDataRole.UserRole)
    if sample_id:
        self.selection_changed.emit(sample_id)
```

---

## Part 4: Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal:** Fix critical bugs, establish event bridge to SDK

| Task | Description | Files |
|------|-------------|-------|
| P1.1 | Fix NoneType crash in sample_list | `ui/widgets/sample_list.py` |
| P1.2 | Create CentralEventBus adapter | `analysis/event_bus_adapter.py` |
| P1.3 | Add null guards throughout UI | Multiple files |
| P1.4 | Verify PluginBase cleanup() works | `ui/main_panel.py` |

### Phase 2: Architecture Refactor (Week 3-5)

**Goal:** Implement service layer, remove SOLID violations

| Task | Description | Files |
|------|-------------|-------|
| P2.1 | Create GateCoordinator facade | `analysis/gate_coordinator.py` |
| P2.2 | Extract StatisticsService | `analysis/services/statistics.py` |
| P2.3 | Add UI Controllers | `ui/controllers/` |
| P2.4 | Migrate EventBus → CentralEventBus | All analysis files |
| P2.5 | Add type hints throughout | All Python files |

### Phase 3: SDK Alignment (Week 6-7)

**Goal:** Full SDK adoption

| Task | Description | Files |
|------|-------------|-------|
| P3.1 | Replace custom EventBus | Remove `analysis/event_bus.py` |
| P3.2 | Adopt AnalysisBase for stats | `analysis/services/statistics.py` |
| P3.3 | Use PluginConfig for settings | `analysis/config.py` |
| P3.4 | Implement proper undo/redo | `ui/main_panel.py` |

### Phase 4: Quality & Documentation (Week 8-10)

**Goal:** Tests, docs, polish

| Task | Description | Files |
|------|-------------|-------|
| P4.1 | Add unit tests for services | `tests/unit/analysis/` |
| P4.2 | Add integration tests | `tests/integration/` |
| P4.3 | Update architecture docs | `docs/ARCHITECTURE.md` |
| P4.4 | Add API documentation | `docs/API.md` |
| P4.5 | Performance profiling | `tests/performance/` |

---

## Part 5: Technical Debt Items

### 5.1 Code Duplication

| Location | Duplicate | Fix |
|----------|-----------|-----|
| `gating.py` + `gate_controller.py` | Gate creation logic | Move to GatingService |
| `statistics.py` + `gate_controller.py` | Stats computation | Move to StatisticsService |
| Multiple `to_dict()` methods | Serialization | Use dataclasses.asdict with custom encoder |

### 5.2 Missing Abstractions

| Current | Should Be |
|---------|-----------|
| Direct dict access for config | PluginConfig class |
| Hardcoded render quality | Configurable via settings |
| Magic numbers in canvas | Constants file |

### 5.3 Testing Gaps

- No tests for GateController
- No tests for EventBus
- No performance benchmarks
- No memory leak tests

---

## Part 6: Code Standards

### 6.1 SOLID Compliance Checklist

- [ ] **S**ingle Responsibility: Each class has one reason to change
- [ ] **O**pen/Closed: Open for extension, closed for modification
- [ ] **L**iskov Substitution: Subtypes are substitutable
- [ ] **I**nterface Segregation: Small, focused interfaces
- [ ] **D**ependency Inversion: Depend on abstractions, not concretions

### 6.2 Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `GateController` |
| Functions | snake_case | `add_gate()` |
| Constants | UPPER_SNAKE | `MAX_EVENTS` |
| Private methods | _snake_case | `_compute_stats()` |
| Signals | snake_case | `gate_added` |

### 6.3 Import Order

```python
# 1. Standard library
import logging
from typing import Optional

# 2. Third-party
import numpy as np
from PyQt6.QtCore import pyqtSignal

# 3. BioPro SDK
from biopro.sdk.core import PluginBase

# 4. Local (relative)
from ..analysis.state import FlowState
from .widgets import SampleList
```

---

## Part 7: Migration Checklist

Use this checklist when implementing each phase:

### Pre-Migration
- [ ] Backup current code
- [ ] Document all public APIs
- [ ] Identify all consumers of each class

### During Migration
- [ ] Keep old code until replacement is tested
- [ ] Run tests after each change
- [ ] Update imports incrementally

### Post-Migration
- [ ] Remove old code
- [ ] Update documentation
- [ ] Verify all tests pass
- [ ] Check for memory leaks

---

## Appendix A: File Impact Map

| Current File | Target File | Change Type |
|--------------|-------------|-------------|
| `analysis/event_bus.py` | `analysis/event_bus_adapter.py` | Replace with SDK |
| `analysis/gate_controller.py` | `analysis/gate_coordinator.py` | Refactor |
| `analysis/gate_propagator.py` | `analysis/services/propagation.py` | Extract service |
| `analysis/statistics.py` | `analysis/services/statistics.py` | Extract service |
| `ui/widgets/*` | `ui/controllers/*` | Add presenter layer |
| N/A | `analysis/services/__init__.py` | New service package |

---

## Appendix B: Reference Materials

- **BioPro SDK Docs:** `/Users/kalaimaranbalasothy/GitHub Projects/BioPro/docs/09_SDK_Summary.md`
- **Existing Architecture:** `FLOW_CYTOMETRY_ARCHITECTURE.md`
- **Implementation Plan:** `FLOW_CYTOMETRY_IMPLEMENTATION_PLAN.md`
- **Module Author Guide:** `/Users/kalaimaranbalasothy/GitHub Projects/BioPro/docs/07_Module_Author_Guide.md`

---

*End of Plan*