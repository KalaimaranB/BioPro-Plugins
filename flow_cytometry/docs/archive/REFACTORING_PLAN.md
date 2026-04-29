# Flow Cytometry Module Refactoring Plan

**Date**: April 28, 2026  
**Status**: Phase 0 - Assessment Complete  
**Goal**: Transform the flow cytometry module into a professional, maintainable, well-tested repository

---

## Executive Summary

The flow cytometry module has significant potential but suffers from:
- **Architecture**: SOLID violations, tight coupling, unclear separation of concerns
- **Code Quality**: Inconsistent patterns, some files too large, technical debt
- **Testing**: Patchwork of tests without systematic coverage strategy
- **Bugs**: Known issues with pseudocolor rendering, coordinate transformations, gate overlays

This document outlines a multi-phase refactoring plan to address these issues systematically.

---

## Phase 1: Architecture Assessment (Current State)

### 1.1 Module Structure

```
flow_cytometry/
├── analysis/           # Pure computation (no PyQt)
│   ├── transforms.py   # ✅ Well-structured
│   ├── scaling.py      # ✅ Good
│   ├── gating.py       # ⚠️ Large (800+ lines)
│   ├── gate_controller.py  # ⚠️ SOLID violations
│   ├── gate_propagator.py  # ⚠️ Complex
│   ├── rendering.py    # ✅ Good separation
│   ├── state.py        # ⚠️ Backward compat complexity
│   ├── services/       # ✅ Good pattern
│   │   ├── naming.py
│   │   ├── splitter.py
│   │   └── modifier.py
│   └── ...
├── ui/
│   ├── graph/
│   │   ├── flow_canvas.py  # ⚠️ HUGE (1000+ lines)
│   │   ├── flow_services.py
│   │   ├── gate_drawing_fsm.py
│   │   └── renderers/
│   └── ...
└── tests/
    ├── unit/           # Some coverage
    ├── integration/    # Patchwork
    └── ...
```

### 1.2 Identified Issues

#### SOLID Violations

| Class | Issue | Severity |
|-------|-------|----------|
| `GateController` | God class - manages gates, stats, selection, propagation | High |
| `FlowCanvas` | 1000+ lines - does rendering, drawing, selection, events | High |
| `GateCoordinator` | Facade that hides too much complexity | Medium |
| `AxisManager` | Couples UI concerns to analysis | Medium |

#### Code Organization Issues

1. **flow_canvas.py**: 1000+ lines - needs decomposition
2. **gating.py**: 800+ lines - multiple gate types in one file
3. **Services scattered**: Some logic in controller, some in services
4. **State management**: Backward compatibility properties add complexity

#### Testing Gaps

| Area | Current State | Needed |
|------|---------------|--------|
| Transform functions | Partial | Full coverage |
| Gate containment | Some | Edge cases |
| Coordinate mapping | Minimal | Comprehensive |
| Rendering | None | Unit tests |
| UI interactions | None | Integration tests |
| End-to-end | Some | Systematic |

#### Known Bugs (from memory and code review)

1. **Pseudocolor subplot colors**: Wrong colormap applied to subplots
2. **AttributeError**: `self._transform_x` not defined in FlowCanvas
3. **Coordinate mapping**: Inconsistent transform application between main canvas and subplots
4. **Gate overlay**: Selection state not properly synced
5. **Auto-range**: Calculation uses wrong data space (raw vs transformed)

---

## Phase 2: Code Quality Improvements

### 2.1 Decompose Large Files

#### flow_canvas.py (Target: <400 lines)

**Current**: 1000+ lines handling:
- Canvas setup
- Data rendering (multiple modes)
- Gate rendering
- Mouse event handling
- Drawing state machine
- Selection handling
- Context menus

**Proposed Split**:
```
ui/graph/
├── flow_canvas.py           # Main widget (300 lines)
├── canvas_data_layer.py     # Data rendering logic
├── canvas_gate_layer.py     # Gate overlay rendering  
├── canvas_event_handler.py  # Mouse/keyboard handling
├── canvas_state_machine.py  # Drawing FSM
└── canvas_context_menu.py   # Menu handling
```

#### gating.py (Target: <500 lines)

**Current**: Gate base class + 5 gate types + GateNode + factory

**Proposed Split**:
```
analysis/gating/
├── gates/
│   ├── __init__.py
│   ├── base.py           # Gate ABC
│   ├── rectangle.py
│   ├── polygon.py
│   ├── ellipse.py
│   ├── quadrant.py
│   └── range.py
├── gate_node.py          # Tree structure
└── gate_factory.py       # Deserialization
```

### 2.2 Apply SOLID Principles

#### GateController Refactoring

**Current Problems**:
- Manages gate lifecycle
- Computes statistics
- Handles selection
- Triggers propagation
- Generates names

**Proposed Split**:
```
services/
├── gate_service.py       # CRUD operations
├── stats_service.py      # Statistics computation
├── selection_service.py  # Gate selection
└── naming_service.py     # Already exists ✅
```

**New Architecture**:
```python
class GateController:
    """Orchestrator - coordinates, doesn't implement"""
    
    def __init__(self):
        self._gate_service = GateService(...)
        self._stats_service = StatsService(...)
        self._selection_service = SelectionService(...)
```

### 2.3 State Management Cleanup

**Current**: FlowState has backward compatibility properties that proxy to nested layers

**Proposed**: 
- Remove backward compat after migration period
- Use explicit `data.experiment` instead of `experiment`
- Document the layer pattern clearly

---

## Phase 3: Testing Infrastructure

### 3.1 Test Organization

```
tests/
├── unit/
│   ├── analysis/
│   │   ├── transforms/
│   │   │   ├── test_linear.py
│   │   │   ├── test_log.py
│   │   │   ├── test_biexponential.py
│   │   │   └── test_inverse.py
│   │   ├── gating/
│   │   │   ├── test_rectangle.py
│   │   │   ├── test_polygon.py
│   │   │   ├── test_ellipse.py
│   │   │   ├── test_quadrant.py
│   │   │   ├── test_range.py
│   │   │   └── test_gate_node.py
│   │   ├── scaling/
│   │   │   ├── test_axis_scale.py
│   │   │   └── test_auto_range.py
│   │   ├── rendering/
│   │   │   ├── test_pseudocolor.py
│   │   │   ├── test_histogram.py
│   │   │   └── test_contour.py
│   │   └── state/
│   │       ├── test_serialization.py
│   │       └── test_layers.py
│   └── ui/
│       ├── test_coordinate_mapper.py
│       ├── test_gate_factory.py
│       └── test_canvas_integration.py
├── integration/
│   ├── test_gate_propagation.py
│   ├── test_statistics_pipeline.py
│   └── test_full_workflow.py
└── fixtures/
    ├── fcs_samples/
    └── gate_trees/
```

### 3.2 Test Coverage Goals

| Module | Current | Target |
|--------|---------|--------|
| transforms | 60% | 95% |
| gating | 70% | 95% |
| scaling | 50% | 90% |
| rendering | 20% | 80% |
| state | 40% | 90% |
| UI components | 10% | 60% |

### 3.3 Testing Patterns

#### Unit Test Template
```python
# tests/unit/analysis/transforms/test_biexponential.py
import pytest
import numpy as np
from flow_cytometry.analysis.transforms import (
    biexponential_transform,
    invert_biexponential_transform,
    TransformType
)

class TestBiexponentialTransform:
    """Tests for biexponential (logicle) transform."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate test data spanning negative and positive ranges."""
        return np.array([-100, 0, 100, 1000, 10000, 100000])
    
    def test_identity_at_zero(self, sample_data):
        """Zero should map to zero."""
        result = biexponential_transform(np.array([0.0]))
        assert result[0] == pytest.approx(0.0, abs=1e-6)
    
    def test_inverse_is_accurate(self, sample_data):
        """Transform should be invertible."""
        original = sample_data
        transformed = biexponential_transform(original)
        recovered = invert_biexponential_transform(transformed)
        np.testing.assert_allclose(original, recovered, rtol=0.01)
    
    @pytest.mark.parametrize("params", [
        {"top": 262144, "width": 1.0, "positive": 4.5, "negative": 0.0},
        {"top": 262144, "width": 0.5, "positive": 4.5, "negative": 1.0},
    ])
    def test_parameter_variations(self, sample_data, params):
        """Test different logicle parameter combinations."""
        result = biexponential_transform(sample_data, **params)
        assert len(result) == len(sample_data)
        assert np.all(np.isfinite(result))
```

#### Integration Test Template
```python
# tests/integration/test_gate_propagation.py
import pytest
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Experiment, Sample
from flow_cytometry.analysis.gating import RectangleGate
from flow_cytometry.analysis.fcs_io import load_fcs

class TestGatePropagation:
    """Integration tests for cross-sample gate propagation."""
    
    @pytest.fixture
    def two_sample_experiment(self, fcs_file_a, fcs_file_b):
        """Create experiment with two samples in same group."""
        exp = Experiment(name="Test")
        sample_a = Sample(sample_id="A", display_name="Sample A")
        sample_a.fcs_data = load_fcs(fcs_file_a)
        sample_b = Sample(sample_id="B", display_name="Sample B") 
        sample_b.fcs_data = load_fcs(fcs_file_b)
        
        exp.add_sample(sample_a)
        exp.add_sample(sample_b)
        
        group = Group(group_id="g1", name="Test Group", sample_ids=["A", "B"])
        exp.add_group(group)
        
        return exp
    
    def test_gate_propagation_updates_counts(self, two_sample_experiment):
        """When gate is added to sample A, sample B should update."""
        # Add gate to sample A
        # Trigger propagation
        # Verify sample B has same gate geometry
        # Verify statistics are computed
        pass
```

---

## Phase 4: Bug Fixes

### 4.1 Pseudocolor Subplot Bug

**Issue**: Subplots render wrong colors for pseudocolor mode

**Root Cause**: 
- Main canvas uses `colormaps['jet']` 
- Subplots may use different colormap or incorrect normalization

**Fix Location**: `render_task.py` and `rendering.py`

**Proposed Fix**:
```python
# In render_task.py - ensure consistent colormap
cmap = colormaps['jet']  # Explicitly use jet for pseudocolor
ax.scatter(
    x_plot, y_plot,
    c=c_plot,
    cmap=cmap,  # Explicit
    vmin=0.0, vmax=1.0,  # Explicit normalization
    s=0.8, alpha=0.8, edgecolors='none'
)
```

### 4.2 AttributeError: _transform_x

**Issue**: `self._transform_x` not defined in FlowCanvas

**Root Cause**: Code uses old attribute name instead of coordinate mapper

**Fix**: Already addressed in memory - use `self._coordinate_mapper.transform_x`

### 4.3 Coordinate Transformation Inconsistency

**Issue**: Main canvas and subplots apply transforms differently

**Root Cause**: 
- Some code transforms data, some transforms limits
- Inconsistent use of raw vs display space

**Fix**: Create unified coordinate mapping service
```python
class CoordinateMapper:
    """Single source of truth for all coordinate transformations."""
    
    def data_to_display(self, values, channel):
        """Transform raw data to display coordinates."""
        ...
    
    def display_to_data(self, values, channel):
        """Transform display coordinates back to raw."""
        ...
    
    def transform_limits(self, limits, channel):
        """Transform axis limits."""
        ...
```

---

## Phase 5: Implementation Roadmap

### 5.1 Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Assessment | 1 week | ✅ Complete |
| Phase 2: Code Quality | 3-4 weeks | Phase 1 |
| Phase 3: Testing | 4-6 weeks | Phase 2 (partial) |
| Phase 4: Bug Fixes | 2-3 weeks | Phase 2 & 3 |
| Phase 5: Polish | 2 weeks | All above |

**Total Estimate**: 12-16 weeks

### 5.2 Priority Order

1. **Week 1-2**: Fix critical bugs (pseudocolor, AttributeError)
2. **Week 3-5**: Decompose flow_canvas.py
3. **Week 6-8**: Refactor GateController, add services
4. **Week 9-14**: Build comprehensive test suite
5. **Week 15-16**: Polish, documentation, review

### 5.3 Risk Mitigation

- **Risk**: Breaking existing functionality
  - **Mitigation**: Extensive test coverage before refactoring
  
- **Risk**: Scope creep**
  - **Mitigation**: Strict phase boundaries, feature freeze during refactoring

- **Risk**: Testing takes too long
  - **Mitigation**: Prioritize critical paths, defer UI tests

---

## Appendix A: File Inventory

### Analysis Module (18 files)

| File | Lines | Status | Priority |
|------|-------|--------|----------|
| transforms.py | 250 | ✅ Good | - |
| scaling.py | 200 | ✅ Good | - |
| gating.py | 800 | ⚠️ Large | High |
| gate_controller.py | 450 | ⚠️ SOLID | High |
| gate_propagator.py | 350 | ⚠️ Complex | Medium |
| gate_coordinator.py | 100 | ✅ OK | Low |
| rendering.py | 150 | ✅ Good | - |
| render_task.py | 200 | ✅ Good | - |
| state.py | 250 | ⚠️ Compat | Medium |
| experiment.py | 400 | ✅ Good | - |
| fcs_io.py | 300 | ✅ Good | - |
| compensation.py | 250 | ✅ Good | - |
| statistics.py | 150 | ✅ Good | - |
| statistics_analysis.py | 100 | ✅ Good | - |
| axis_manager.py | 80 | ✅ Good | - |
| population_service.py | 120 | ✅ Good | - |
| config.py | 50 | ✅ Good | - |
| events.py | 40 | ✅ Good | - |
| _utils.py | 200 | ✅ Good | - |

### UI Module (key files)

| File | Lines | Status | Priority |
|------|-------|--------|----------|
| flow_canvas.py | 1000+ | ⚠️ Huge | Critical |
| flow_services.py | 200 | ✅ Good | - |
| gate_drawing_fsm.py | 250 | ✅ Good | - |
| graph_window.py | 300 | ⚠️ Complex | Medium |

---

## Appendix B: Dependencies

### External
- `flowkit` - FCS file handling
- `flowutils` - Logicle transform
- `numpy` - Numerical operations
- `pandas` - DataFrames
- `scipy` - Density estimation
- `fast_histogram` - High-performance histograms
- `matplotlib` - Rendering

### Internal (BioPro SDK)
- `biopro.sdk.core` - Base classes, events
- `biopro.sdk.core.task_scheduler` - Background tasks
- `biopro.ui.theme` - Styling

---

## Appendix C: Naming Conventions

### Current Inconsistencies
- `gate_id` vs `GateID` 
- `sample_id` vs `SampleID`
- Mixed camelCase and snake_case

### Proposed Standard
- Use snake_case for all Python identifiers
- Use camelCase only for external APIs (JSON, FCS)
- Prefix internal IDs with type: `gate_id`, `sample_id`, `node_id`

---

*Document Version: 1.0*  
*Next Review: After Phase 2 completion*