# Comprehensive UI Test Suite Plan for Flow Cytometry Module

## Overview

This document outlines a comprehensive testing strategy for the flow cytometry UI components. The current test suite has basic unit tests but lacks integration and functional testing that actually exercises UI workflows.

**Current Status**: 13 basic UI tests (mostly initialization)
**Target**: 50+ comprehensive UI tests covering full workflows

## Test Organization

### Directory Structure
```
flow_cytometry/tests/ui/
├── conftest.py                              # UI test configuration & fixtures
├── test_flow_canvas.py                     # FlowCanvas unit tests (expanded)
├── test_graph_window.py                    # GraphWindow integration tests
├── test_main_panel.py                      # MainPanel workflow tests
├── test_gate_drawing.py                    # Interactive gate drawing tests
├── test_ui_workflows.py                    # End-to-end UI workflow tests
└── fixtures/
    └── ui_fixtures.py                      # UI-specific test fixtures
```

## Test Levels

### Level 1: Unit Tests (20-30 tests)
**Purpose**: Test individual UI components in isolation

#### FlowCanvas Tests (test_flow_canvas.py)
- **Initialization & Setup** (5 tests)
  - Canvas creation with different parents
  - Attribute initialization
  - Service instantiation
  - Scale/transform setup

- **Data Management** (5 tests)
  - set_data() with various DataFrames
  - set_axes() parameter changes
  - set_scales() transform updates
  - set_display_mode() changes

- **Gate Management** (5 tests)
  - set_gates() with all gate types
  - select_gate() functionality
  - Gate overlay rendering
  - Gate coordinate transformation

- **Event Handling** (5 tests)
  - Mouse press/release events
  - Drawing mode state changes
  - Coordinate mapping accuracy
  - Event signal emission

#### GraphWindow Tests (test_graph_window.py)
- **Window Management** (5 tests)
  - Window creation and layout
  - Parameter selection UI
  - Transform controls
  - Gate list management

### Level 2: Integration Tests (15-20 tests)
**Purpose**: Test component interactions

#### Gate Drawing Integration (test_gate_drawing.py)
- **Rectangle Drawing** (3 tests)
  - Mouse drag rectangle creation
  - Coordinate transformation accuracy
  - Gate signal emission

- **Polygon Drawing** (3 tests)
  - Multi-point polygon creation
  - Vertex coordinate mapping
  - Closed polygon completion

- **Ellipse Drawing** (2 tests)
  - Ellipse parameter calculation
  - Transform-aware rendering

- **Quadrant/Range Drawing** (2 tests)
  - Multi-region gate creation
  - Interactive threshold setting

#### UI Workflow Integration (test_ui_workflows.py)
- **Data Loading Workflow** (3 tests)
  - FCS file loading → graph display
  - Parameter selection → plot updates
  - Transform application → visual changes

- **Gating Workflow** (4 tests)
  - Gate creation → overlay display
  - Gate editing → coordinate updates
  - Gate deletion → UI cleanup
  - Multi-gate interactions

### Level 3: Functional Tests (10-15 tests)
**Purpose**: Test complete user workflows

#### Main Panel Workflows (test_main_panel.py)
- **Sample Management** (3 tests)
  - Load multiple FCS files
  - Sample selection and display
  - Project asset management

- **Analysis Pipeline** (4 tests)
  - Load → Gate → Statistics workflow
  - Sequential gating operations
  - Population hierarchy building
  - Results export/saving

- **Error Handling** (3 tests)
  - Invalid file loading
  - Gate creation on empty data
  - Transform application errors

## Key Testing Challenges & Solutions

### Challenge 1: PyQt6 GUI Testing
**Problem**: PyQt6 requires GUI environment, hard to test in CI
**Solution**:
- Use QTest for widget testing where possible
- Mock PyQt6 components for unit tests
- Use xvfb-run for headless GUI tests in CI
- Separate logic from UI rendering

### Challenge 2: Matplotlib Integration
**Problem**: Matplotlib FigureCanvasQTAgg hard to mock completely
**Solution**:
- Test coordinate mapping logic separately
- Mock matplotlib artists and patches
- Use real matplotlib for integration tests
- Test rendering pipeline components

### Challenge 3: Event-Driven Testing
**Problem**: UI interactions are event-driven and asynchronous
**Solution**:
- Use QTest.qWaitForWindowExposed() for async operations
- Mock event signals and slots
- Test state changes rather than visual output
- Use signal spies for event verification

## Test Fixtures

### UI Test Fixtures (fixtures/ui_fixtures.py)
```python
@pytest.fixture
def mock_qt_app():
    """Mock QApplication for testing."""
    pass

@pytest.fixture
def flow_canvas_with_data(sample_a_events):
    """FlowCanvas with real FCS data loaded."""
    pass

@pytest.fixture
def graph_window_with_sample():
    """GraphWindow with sample loaded and displayed."""
    pass

@pytest.fixture
def main_panel_with_project():
    """MainPanel with project and samples loaded."""
    pass
```

### Mock Strategy
- **Light Mocking**: Mock only PyQt6/matplotlib internals
- **Real Components**: Use real FlowCanvas, GraphWindow where possible
- **Signal Testing**: Use QSignalSpy for signal verification
- **State Verification**: Test internal state changes

## Implementation Plan

### Phase 1: Enhanced Unit Tests (Week 1)
1. Expand test_flow_canvas.py with comprehensive tests
2. Add test_graph_window.py with window management tests
3. Create ui_fixtures.py with reusable fixtures
4. Implement coordinate mapping and transform tests

### Phase 2: Integration Tests (Week 2)
1. Create test_gate_drawing.py for interactive drawing
2. Add test_ui_workflows.py for component interactions
3. Test data loading and display pipelines
4. Implement gate creation and editing workflows

### Phase 3: Functional Tests (Week 3)
1. Create test_main_panel.py for end-to-end workflows
2. Add error handling and edge case tests
3. Implement CI-compatible headless testing
4. Add performance and memory leak tests

### Phase 4: CI Integration (Week 4)
1. Set up xvfb-run for headless GUI testing
2. Configure test parallelization
3. Add test coverage reporting
4. Implement test result analysis

## Success Metrics

- **Test Coverage**: 80%+ for UI components
- **Test Execution**: All tests pass in < 5 minutes
- **CI Compatibility**: Tests run in headless environment
- **Bug Prevention**: Catch UI regressions before release
- **Maintainability**: Tests are easy to update with UI changes

## Risk Mitigation

- **Mock Complexity**: Keep mocks minimal and focused
- **Test Fragility**: Test behavior, not implementation details
- **Performance**: Use fixtures to avoid expensive setup
- **Dependencies**: Isolate UI tests from analysis logic changes