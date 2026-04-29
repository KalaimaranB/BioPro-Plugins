import pytest
from unittest.mock import MagicMock
from flow_cytometry.analysis.experiment import Experiment, Sample
from flow_cytometry.analysis.gating import GateNode, RectangleGate
from flow_cytometry.analysis.services.splitter import PopulationSplitter

@pytest.fixture
def experiment_with_sample():
    exp = Experiment()
    sample = Sample(sample_id="test_sample", display_name="Test Sample")
    exp.samples["test_sample"] = sample
    
    gate = RectangleGate("FSC-A", "SSC-A", x_min=10, x_max=100, gate_id="gate_123")
    node = sample.gate_tree.add_child(gate, name="Lymphocytes")
    return exp, sample, node, gate

def test_split_population(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    
    assert len(sample.gate_tree.children) == 1
    assert sample.gate_tree.children[0] == node
    
    result = PopulationSplitter.split_population(exp, "test_sample", node.node_id)
    
    assert result is not None
    new_node_id, new_name, gate_id = result
    
    assert gate_id == gate.gate_id
    assert new_name == "Lymphocytes (Outside)"
    
    # Check tree structure
    assert len(sample.gate_tree.children) == 2
    sibling = sample.gate_tree.find_node_by_id(new_node_id)
    
    assert sibling is not None
    assert sibling != node
    assert sibling.gate is gate  # Exact same instance
    assert sibling.negated is True  # Sibling is inverted
    assert node.negated is False

def test_split_population_already_negated(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    node.negated = True
    node.name = "Debris (Outside)"
    
    result = PopulationSplitter.split_population(exp, "test_sample", node.node_id)
    
    assert result is not None
    new_node_id, new_name, gate_id = result
    
    assert new_name == "Debris (Outside) (Inside)"
    
    sibling = sample.gate_tree.find_node_by_id(new_node_id)
    assert sibling.negated is False  # Flipped from True to False

def test_split_population_invalid_sample(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    result = PopulationSplitter.split_population(exp, "invalid_sample", node.node_id)
    assert result is None

def test_split_population_invalid_node(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    result = PopulationSplitter.split_population(exp, "test_sample", "invalid_node_id")
    assert result is None

def test_split_population_root_node(experiment_with_sample):
    exp, sample, node, gate = experiment_with_sample
    # Cannot split the root node (it has no parent to attach the sibling to)
    result = PopulationSplitter.split_population(exp, "test_sample", sample.gate_tree.node_id)
    assert result is None
