"""Unit tests for GateCoordinator facade.

Tests the facade API and signal forwarding.
"""

import pytest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from flow_cytometry.analysis.experiment import Sample
from flow_cytometry.analysis.fcs_io import FCSData
from flow_cytometry.analysis.gating.rectangle import RectangleGate
from flow_cytometry.analysis.gate_coordinator import GateCoordinator
from flow_cytometry.analysis.state import FlowState


class TestGateCoordinatorFacade:
    """Test facade methods delegate to controller."""
    
    @pytest.mark.unit
    def test_add_gate_delegates_to_controller(self):
        """Test add_gate forwards to controller."""
        state = FlowState()
        sample = Sample(sample_id="s1", display_name="Sample 1", fcs_data=FCSData(Path("a.fcs"), channels=["FSC-A"], markers=[""], events=pd.DataFrame({"FSC-A": [1.0]})))
        state.experiment.add_sample(sample)

        coordinator = GateCoordinator(state)
        gate = RectangleGate("FSC-A", None, x_min=0.0, x_max=1.0)
        
        # Mock controller method
        called_with = None
        def mock_add(gate_arg, sample_id_arg, name_arg, parent_node_id_arg):
            nonlocal called_with
            called_with = (gate_arg, sample_id_arg, name_arg, parent_node_id_arg)
            return "node_123"

        original = coordinator._controller.add_gate
        coordinator._controller.add_gate = mock_add

        try:
            result = coordinator.add_gate(gate, "s1", name="rect", parent_node_id="parent")
            assert result == "node_123"
            assert called_with == (gate, "s1", "rect", "parent")
        finally:
            coordinator._controller.add_gate = original
    
    @pytest.mark.unit
    def test_remove_population_delegates_to_controller(self):
        """Test remove_population forwards to controller."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        called_with = None
        def mock_remove(sample_id_arg, node_id_arg):
            nonlocal called_with
            called_with = (sample_id_arg, node_id_arg)
            return True

        original = coordinator._controller.remove_population
        coordinator._controller.remove_population = mock_remove

        try:
            result = coordinator.remove_population("s1", "node_123")
            assert result is True
            assert called_with == ("s1", "node_123")
        finally:
            coordinator._controller.remove_population = original
    
    @pytest.mark.unit
    def test_get_gates_for_display_delegates_to_controller(self):
        """Test get_gates_for_display forwards to controller."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        called_with = None
        def mock_get(sample_id_arg, parent_node_id_arg):
            nonlocal called_with
            called_with = (sample_id_arg, parent_node_id_arg)
            return ([], [])

        original = coordinator._controller.get_gates_for_display
        coordinator._controller.get_gates_for_display = mock_get

        try:
            result = coordinator.get_gates_for_display("s1", "parent")
            assert result == ([], [])
            assert called_with == ("s1", "parent")
        finally:
            coordinator._controller.get_gates_for_display = original


class TestGateCoordinatorSignals:
    """Test signal forwarding from controller to facade."""
    
    @pytest.mark.unit
    def test_gate_added_signal_forwarded(self):
        """Test gate_added signal is forwarded."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        signal_received = None
        def on_gate_added(sample_id, node_id):
            nonlocal signal_received
            signal_received = (sample_id, node_id)
        
        coordinator.gate_added.connect(on_gate_added)
        coordinator._controller.gate_added.emit("s1", "node_123")
        
        assert signal_received == ("s1", "node_123")
    
    @pytest.mark.unit
    def test_gate_removed_signal_forwarded(self):
        """Test gate_removed signal is forwarded."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        signal_received = None
        def on_gate_removed(sample_id, node_id):
            nonlocal signal_received
            signal_received = (sample_id, node_id)
        
        coordinator.gate_removed.connect(on_gate_removed)
        coordinator._controller.gate_removed.emit("s1", "node_123")
        
        assert signal_received == ("s1", "node_123")
    
    @pytest.mark.unit
    def test_propagation_complete_signal_forwarded(self):
        """Test propagation_complete signal is forwarded."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        signal_received = False
        def on_propagation_complete():
            nonlocal signal_received
            signal_received = True
        
        coordinator.propagation_complete.connect(on_propagation_complete)
        coordinator._propagator.propagation_complete.emit()
        
        assert signal_received is True


class TestGateCoordinatorProperties:
    """Test property access."""
    
    @pytest.mark.unit
    def test_controller_property_returns_controller(self):
        """Test controller property returns the controller instance."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        assert coordinator.controller is coordinator._controller
    
    @pytest.mark.unit
    def test_propagator_property_returns_propagator(self):
        """Test propagator property returns the propagator instance."""
        state = FlowState()
        coordinator = GateCoordinator(state)
        
        assert coordinator.propagator is coordinator._propagator