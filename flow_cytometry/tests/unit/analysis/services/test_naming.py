import pytest
from flow_cytometry.analysis.experiment import Experiment, Sample
from flow_cytometry.analysis.gating import RectangleGate, GateNode
from flow_cytometry.analysis.services.naming import NamingService

@pytest.fixture
def experiment_with_sample():
    exp = Experiment()
    sample = Sample(sample_id="test_sample", display_name="Test Sample")
    exp.samples["test_sample"] = sample
    return exp, sample

def test_generate_unique_name_empty_tree(experiment_with_sample):
    exp, sample = experiment_with_sample
    name = NamingService.generate_unique_name(exp, "test_sample", prefix="Gate")
    assert name == "Gate 1"

def test_generate_unique_name_with_collisions(experiment_with_sample):
    exp, sample = experiment_with_sample
    
    # Add a gate named "Gate 1"
    gate1 = RectangleGate("FSC-A", "SSC-A", x_min=0, x_max=10)
    sample.gate_tree.add_child(gate1, name="Gate 1")
    
    name = NamingService.generate_unique_name(exp, "test_sample", prefix="Gate")
    assert name == "Gate 2"

def test_generate_unique_name_gap_in_sequence(experiment_with_sample):
    exp, sample = experiment_with_sample
    
    # Add "Gate 1" and "Gate 3"
    gate1 = RectangleGate("FSC-A", "SSC-A", x_min=0, x_max=10)
    sample.gate_tree.add_child(gate1, name="Gate 1")
    
    gate2 = RectangleGate("FSC-A", "SSC-A", x_min=0, x_max=10)
    sample.gate_tree.add_child(gate2, name="Gate 3")
    
    # Should fill the gap "Gate 2"
    name = NamingService.generate_unique_name(exp, "test_sample", prefix="Gate")
    assert name == "Gate 2"

def test_generate_unique_name_different_prefix(experiment_with_sample):
    exp, sample = experiment_with_sample
    
    gate1 = RectangleGate("FSC-A", "SSC-A", x_min=0, x_max=10)
    sample.gate_tree.add_child(gate1, name="Gate 1")
    
    name = NamingService.generate_unique_name(exp, "test_sample", prefix="Lymphocytes")
    assert name == "Lymphocytes 1"

def test_generate_unique_name_invalid_sample():
    exp = Experiment()
    name = NamingService.generate_unique_name(exp, "invalid_sample", prefix="Gate")
    assert name == "Gate 1"
