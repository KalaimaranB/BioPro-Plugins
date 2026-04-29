import pytest
from unittest.mock import MagicMock
from flow_cytometry.analysis.experiment import Experiment, Sample
from flow_cytometry.analysis.gating import GateNode, RectangleGate
from flow_cytometry.analysis.services.modifier import GateModifier

@pytest.fixture
def experiment_with_sample():
    exp = Experiment()
    sample = Sample(sample_id="test_sample", display_name="Test Sample")
    exp.samples["test_sample"] = sample
    
    # Add a gate to the tree
    gate = RectangleGate("FSC-A", "SSC-A", x_min=10, x_max=100, gate_id="gate_123")
    node = sample.gate_tree.add_child(gate, name="Population A")
    return exp, sample, node, gate

def test_modify_gate_geometry(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    
    # Modify the gate geometry
    success = GateModifier.modify_gate(
        exp, 
        gate_id="gate_123", 
        sample_id="test_sample", 
        x_min=20, 
        x_max=200
    )
    
    assert success is True
    assert gate.x_min == 20
    assert gate.x_max == 200
    # Unchanged parameters should remain intact
    assert getattr(gate, "y_min", None) is None or gate.y_min == float("-inf")

def test_modify_gate_identity_negated(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    
    assert node.negated is False
    
    # Modify the gate node identity
    success = GateModifier.modify_gate(
        exp, 
        gate_id="gate_123", 
        sample_id="test_sample", 
        negated=True
    )
    
    assert success is True
    assert node.negated is True

def test_modify_gate_invalid_sample():
    exp = Experiment()
    success = GateModifier.modify_gate(exp, "gate_123", "invalid_sample", x_min=0)
    assert success is False

def test_modify_gate_invalid_gate(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    success = GateModifier.modify_gate(exp, "invalid_gate", "test_sample", x_min=0)
    assert success is False

def test_modify_gate_multiple_linked_nodes(experiment_with_sample):
    exp, sample, node1, gate = experiment_with_sample
    
    # Add a sibling node linked to the exact same gate instance
    node2 = sample.gate_tree.add_child(gate, name="Population B")
    
    # Modify both geometry and negated state
    success = GateModifier.modify_gate(
        exp, 
        gate_id="gate_123", 
        sample_id="test_sample", 
        x_max=500,
        negated=True
    )
    
    assert success is True
    assert gate.x_max == 500
    
    # BOTH nodes should have the identity change applied if passed
    assert node1.negated is True
    assert node2.negated is True
