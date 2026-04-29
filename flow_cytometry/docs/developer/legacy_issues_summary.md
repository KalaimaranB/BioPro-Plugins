# Legacy Issues & Pending Refactoring Summary

**Date**: April 29, 2026

This document summarizes the pending work identified in the legacy planning documents (`BUG_FIXES.md`, `REPAIR_GUIDE.md`, `REFACTORING_PLAN.md`, etc.) after reviewing the current state of the codebase.

## Completed Work (Do NOT Repeat)

The following items from the legacy plans have already been successfully implemented:
1. **Gating Decomposition**: `gating.py` was successfully split into the `analysis/gating/` subpackage (`rectangle.py`, `polygon.py`, etc.).
2. **Service Extraction**: `GateController` responsibilities have been successfully delegated to `analysis/services/` (`gating_service.py`, `stats_service.py`, etc.).
3. **Magic Numbers / Constants**: All constants and logicle defaults were extracted into `analysis/constants.py`.
4. **Pseudocolor Rendering Bugs**: The incorrect colormaps and thresholding issues in pseudocolor subplots have been fixed.
5. **Coordinate Mapping Inconsistencies**: The `CoordinateMapper` service was created and biexponential parameters have been deduplicated.
6. **DIP Violations**: UI-dependent analysis files (like `render_task.py`) were moved to the `ui/` package.

## Pending Work (Actionable)

### 1. Decompose `flow_canvas.py` (Critical)
**Status**: Not Started
**Issue**: `ui/graph/flow_canvas.py` remains a monolithic file (~1000+ lines, 36KB). It handles rendering, drawing state machines, event handling, and context menus.
**Action Required**:
Split `flow_canvas.py` into smaller, focused components:
- `canvas_data_layer.py`: For plotting the data points (scatter, density).
- `canvas_gate_layer.py`: For rendering the gate overlays and labels.
- `canvas_event_handler.py`: For handling mouse/keyboard input.

### 2. Comprehensive Test Suite (High Priority)
**Status**: Partially Completed
**Issue**: While unit tests exist for `transforms.py`, `gating.py`, and `rendering.py`, the overall test layout was fragmented, and end-to-end integration tests are missing.
**Action Required**:
- Build a Golden JSON-backed integration pipeline to verify the statistical outputs of the entire gating tree against a known truth.
- Improve test coverage for the new services in `analysis/services/`.

### 3. State Management Cleanup (Medium Priority)
**Status**: In Progress
**Issue**: `FlowState` still has some backward-compatibility properties that proxy to nested layers.
**Action Required**: Remove these properties after the migration period is complete and ensure all callers use explicit paths (e.g., `state.experiment`).

---
*Note: This document replaces all legacy planning markdown files, which have been archived in `docs/archive/`.*
