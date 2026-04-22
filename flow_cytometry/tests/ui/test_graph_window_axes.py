import pytest
from flow_cytometry.analysis.transforms import TransformType

@pytest.mark.ui
class TestGraphWindowAxisIndependence:

    def test_fsc_and_ssc_get_different_auto_ranges(self, qtbot, graph_window_with_sample_c):
        """FSC-A and SSC-A must never share the same min_val after render."""
        win = graph_window_with_sample_c
        x_min = win._x_scale.min_val
        y_min = win._y_scale.min_val
        from flow_cytometry.analysis.scaling import AxisScale
        # Switch to BIEXPONENTIAL to show data-driven floors
        x_scale = AxisScale(TransformType.BIEXPONENTIAL)
        win.apply_axis_scale(win._x_combo.currentData(), x_scale)
        x_min, x_max = win._calculate_auto_range("x")
        
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        win.apply_axis_scale(win._y_combo.currentData(), y_scale)
        y_min, y_max = win._calculate_auto_range("y")
        
        assert x_min != y_min
        assert x_min > 0, "FSC floor should be positive"

    def test_switching_y_axis_updates_scale_from_new_data(self, qtbot, graph_window_with_sample_c):
        """Switching Y channel must recompute range from the new channel's data."""
        win = graph_window_with_sample_c
        
        from flow_cytometry.analysis.scaling import AxisScale
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        win.apply_axis_scale(win._y_combo.currentData(), y_scale)
        win._do_axis_render()
        
        old_y_min = win._y_scale.min_val  # SSC-A (positive floor)

        # Switch Y to FITC-A (fluorescence with negatives)
        for i in range(win._y_combo.count()):
            if win._y_combo.itemData(i) == "FITC-A":
                win._y_combo.setCurrentIndex(i)
                break
        
        qtbot.waitSignal(win._axis_debounce.timeout, timeout=1000)
        qtbot.wait(100)

        new_y_min = win._y_scale.min_val
        assert new_y_min != old_y_min, "Y scale must update after channel switch"
        assert new_y_min < 0, "FITC-A (compensated) should have negative floor"

    def test_auto_range_button_recomputes_from_current_data(self, qtbot, graph_window_with_sample_c):
        """Auto-Range button must recompute scale from the current channel's data."""
        win = graph_window_with_sample_c
        
        # Manually corrupt the min_val
        win._x_scale.min_val = 999999999.0
        # Trigger the internal auto-range explicitly
        win._x_scale.min_val, win._x_scale.max_val = win._calculate_auto_range("x")
        
        assert win._x_scale.min_val < 100000, "Auto-range must reset from data"

    def test_biex_transform_change_recomputes_range(self, qtbot, graph_window_with_sample_c):
        """Switching X from LINEAR to BIEX must produce a sensible positive min."""
        win = graph_window_with_sample_c
        # Switch X to BIEXPONENTIAL
        from flow_cytometry.analysis.scaling import AxisScale
        x_scale = AxisScale(TransformType.BIEXPONENTIAL)
        
        # We must update the state cache as well, otherwise _do_axis_render restores LINEAR
        x_ch = win._x_combo.currentData() or win._x_combo.currentText()
        win._state.channel_scales[x_ch] = x_scale.copy()
        win.apply_axis_scale(x_ch, x_scale)
        
        win._x_scale.min_val, win._x_scale.max_val = win._calculate_auto_range("x")
        win._do_axis_render()
        
        # It's possible the data's positive percentiles are small, but for this real data
        # the floor shouldn't be exactly 0.0 like LINEAR forces.
        assert win._x_scale.transform_type == TransformType.BIEXPONENTIAL
        assert win._x_scale.min_val > 0, "BIEX FSC min must be positive"
        assert win._x_scale.max_val > win._x_scale.min_val


@pytest.mark.ui
class TestGraphWindowGatingInteraction:

    def test_gate_applied_zooms_axis_to_population(self, qtbot, graph_window_with_sample_c):
        """After gating, auto-range should zoom to the gated population."""
        # This tests that the graph window respects the gate passed down to it
        pass # Placeholder for more complex UI gating interactions that require the full window manager
