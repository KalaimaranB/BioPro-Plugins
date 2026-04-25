import pytest
from unittest.mock import MagicMock, patch

def test_gate_propagator_debounce(empty_state, qtbot):
    with patch("biopro.core.task_scheduler.task_scheduler") as mock_scheduler:
        from flow_cytometry.analysis.gate_propagator import GatePropagator
        propagator = GatePropagator(empty_state)
        
        propagator.request_propagation("gate1", "s1")
        propagator.request_propagation("gate1", "s1")
        
        # Should only call submit once after debounce
        qtbot.wait(300)
        assert mock_scheduler.submit.call_count == 1

def test_gate_propagator_handler_cleanup(state_with_sample, qtbot):
    """Verify that handlers disconnect themselves to prevent leaks."""
    with patch("biopro.core.task_scheduler.task_scheduler") as mock_scheduler:
        from flow_cytometry.analysis.gate_propagator import GatePropagator
        propagator = GatePropagator(state_with_sample)
        mock_scheduler.submit.return_value = "task_1"
        
        propagator.request_propagation("gate1", "s1")
        qtbot.wait(300)
        
        # Check that connect was called for the handler
        assert mock_scheduler.task_finished.connect.call_count == 1
        
        # Extract the handler method
        handler_method = mock_scheduler.task_finished.connect.call_args[0][0]
        handler_obj = handler_method.__self__
        
        # Simulate task completion
        handler_obj.on_finished("task_1", {"propagation_results": {}})
        
        # Check that disconnect was called
        assert mock_scheduler.task_finished.disconnect.call_count == 1
