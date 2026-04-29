# Flow Canvas Bug Fixes

**Date**: April 28, 2026  
**Status**: In Progress

---

## Bug 1: Pseudocolor Subplot Colors Wrong

### Symptom
Subplots render with wrong colors compared to main canvas for pseudocolor mode.

### Root Cause Analysis

After code review, the pseudocolor rendering has these components:

1. **rendering.py** - `compute_pseudocolor_points()`:
   - Returns normalized density values in range [0, 1]
   - Uses rank-based normalization with log transform
   - Does NOT specify colormap (expects caller to provide)

2. **render_task.py** - `RenderTask.run()` (lines 115-125):
   ```python
   ax.scatter(
       x_plot, y_plot,
       c=c_plot,
       cmap=colormaps['jet'],  # ✅ Explicit jet colormap
       vmin=0.0, vmax=1.0,     # ✅ Explicit normalization
       s=0.8, alpha=0.8, edgecolors='none'
   )
   ```

3. **flow_canvas.py** - Uses `RenderStrategyFactory` which delegates to strategies

### Likely Issue
The subplot rendering might be using a different strategy or the strategy doesn't explicitly set colormap. Need to verify `RenderStrategyFactory` and strategy implementations.

### Fix Plan
1. Verify all render strategies explicitly set `cmap=colormaps['jet']`
2. Ensure `vmin=0.0, vmax=1.0` is always set for pseudocolor
3. Add integration test for subplot color consistency

---

## Bug 2: AttributeError: _transform_x

### Symptom
`AttributeError: 'FlowCanvas' object has no attribute '_transform_x'`

### Root Cause
Code references old attribute name instead of using `self._coordinate_mapper`

### Fix
Use `self._coordinate_mapper.transform_x()` instead of `self._transform_x()`

---

## Bug 3: Coordinate Transformation Inconsistency

### Symptom
Main canvas and subplots show different data for same parameters

### Root Cause
- Some code transforms data, then transforms limits again
- Raw vs display space confusion
- Auto-range calculation uses wrong data space

### Fix
Create unified `CoordinateMapper` service as single source of truth:
- `data_to_display()` - raw → display
- `display_to_data()` - display → raw  
- `transform_limits()` - handle axis limits consistently

---

## Bug 4: Gate Overlay Selection Not Synced

### Symptom
Gate selection highlight doesn't update when changed programmatically

### Root Cause
`_render_gate_layer()` not called after selection change

### Fix
Ensure `gate_selected` signal triggers re-render

---

## Testing Checklist

- [ ] test_pseudocolor_main_vs_subplot_colors
- [ ] test_coordinate_mapper_consistency
- [ ] test_gate_selection_updates_overlay
- [ ] test_auto_range_raw_vs_transformed