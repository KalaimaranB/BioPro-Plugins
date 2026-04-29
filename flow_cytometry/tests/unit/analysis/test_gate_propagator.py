import pytest
from unittest.mock import MagicMock, patch
from flow_cytometry.analysis.experiment import Sample

def test_gate_propagator_debounce(state_with_sample, qtbot):
    with patch("flow_cytometry.analysis.gate_propagator.task_scheduler") as mock_scheduler:
        from flow_cytometry.analysis.gate_propagator import GatePropagator
        # Add a second sample so there is a target for propagation
        s2 = Sample(sample_id="s2", display_name="Sample 2")
        s2.fcs_data = MagicMock()
        state_with_sample.experiment.samples["s2"] = s2
        
        propagator = GatePropagator(state_with_sample)
        
        propagator.request_propagation("gate1", "s1")
        propagator.request_propagation("gate1", "s1")
        
        # Should only call submit once after debounce
        qtbot.wait(300)
        assert mock_scheduler.submit.call_count == 1

def test_gate_propagator_handler_cleanup(state_with_sample, qtbot):
    """Verify that handlers disconnect themselves to prevent leaks."""
    with patch("flow_cytometry.analysis.gate_propagator.task_scheduler") as mock_scheduler:
        from flow_cytometry.analysis.gate_propagator import GatePropagator
        # Add a second sample so there is a target for propagation
        s2 = Sample(sample_id="s2", display_name="Sample 2")
        s2.fcs_data = MagicMock()
        state_with_sample.experiment.samples["s2"] = s2

        propagator = GatePropagator(state_with_sample)
        mock_scheduler.submit.return_value = "task_1"
        
        propagator.request_propagation("gate1", "s1")
        qtbot.wait(300)
        
        # Check that connect was called for the handler
        assert mock_scheduler.task_finished.connect.call_count == 1
        
        # Extract the handler method
        handler_method = mock_scheduler.task_finished.connect.call_args[0][0]
        # For a function/method, __self__ works if it's a bound method
        handler_obj = handler_method.__self__
        
        # Simulate task completion
        handler_obj.on_finished("task_1", {"propagation_results": {}})
        
        # Check that disconnect was called (by the handler itself)
        assert mock_scheduler.task_finished.disconnect.call_count == 1
