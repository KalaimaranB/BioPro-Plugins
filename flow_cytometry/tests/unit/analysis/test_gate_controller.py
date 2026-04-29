import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThreadPool
import sys

# Ensure QApplication exists for signal processing
app = QApplication.instance() or QApplication(sys.argv)

from flow_cytometry.analysis.gate_controller import GateController
from flow_cytometry.analysis.experiment import Sample
from flow_cytometry.analysis.gating import RectangleGate, QuadrantGate, GateNode
from flow_cytometry.analysis.population_service import PopulationService

@pytest.fixture
def gate_controller(flow_state):
    controller = GateController(flow_state)
    controller.sync_stats = True
    return controller

def test_add_rectangle_gate(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    
    # Add a gate
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    assert node_id is not None
    sample = flow_state.experiment.samples[sample_id]
    
    # Check tree
    node = sample.gate_tree.find_node_by_id(node_id)
    assert node is not None
    assert node.name == "Singlets"
    assert node.gate == gate_rectangle_singlet
    
    # Wait for background task to complete
    print("Waiting for thread pool...")
    QThreadPool.globalInstance().waitForDone()
    print("Processing events...")
    for _ in range(10): # Process multiple times to be sure
        QApplication.processEvents()
    
    # Check stats were computed
    print(f"Node stats: {node.statistics}")
    assert "count" in node.statistics
    assert node.statistics["count"] > 0
    assert node.statistics["pct_parent"] <= 100.0

def test_add_quadrant_gate(gate_controller, flow_state, gate_quadrant_cd4_cd8):
    sample_id = "test_sample_1"
    
    node_id = gate_controller.add_gate(gate_quadrant_cd4_cd8, sample_id)
    
    sample = flow_state.experiment.samples[sample_id]
    quad_node = sample.gate_tree.find_node_by_id(node_id)
    
    assert quad_node is not None
    assert len(quad_node.children) == 4
    
    labels = [n.name for n in quad_node.children]
    assert labels == ["Q1 ++", "Q2 −+", "Q3 −−", "Q4 +−"]

def test_modify_gate(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    sample = flow_state.experiment.samples[sample_id]
    node = sample.gate_tree.find_node_by_id(node_id)
    
    # Wait for initial stats
    QThreadPool.globalInstance().waitForDone()
    for _ in range(10): QApplication.processEvents()
    
    if "count" not in node.statistics:
        print(f"DEBUG: node.statistics is empty: {node.statistics}")
        # Try one more time?
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()
        
    orig_count = node.statistics["count"]
    
    # Modify gate to be much smaller
    success = gate_controller.modify_gate(
        gate_rectangle_singlet.gate_id, 
        sample_id, 
        x_min=100_000, 
        x_max=110_000,
        y_min=80_000,
        y_max=90_000
    )
    
    assert success is True
    assert gate_rectangle_singlet.x_min == 100_000
    
    # Wait for background task
    QThreadPool.globalInstance().waitForDone()
    for _ in range(10): QApplication.processEvents()
    
    # Check stats updated
    new_count = node.statistics["count"]
    assert new_count < orig_count

def test_remove_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    success = gate_controller.remove_population(sample_id, node_id)
    assert success is True
    
    sample = flow_state.experiment.samples[sample_id]
    assert sample.gate_tree.find_node_by_id(node_id) is None

def test_rename_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    success = gate_controller.rename_population(sample_id, node_id, "New Name")
    assert success is True
    
    sample = flow_state.experiment.samples[sample_id]
    node = sample.gate_tree.find_node_by_id(node_id)
    assert node.name == "New Name"

def test_split_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    sibling_id = gate_controller.split_population(sample_id, node_id)
    assert sibling_id is not None
    
    # Wait for background task
    QThreadPool.globalInstance().waitForDone()
    for _ in range(10): QApplication.processEvents()
    
    sample = flow_state.experiment.samples[sample_id]
    sibling = sample.gate_tree.find_node_by_id(sibling_id)
    
    assert sibling is not None
    assert sibling.negated is True
    assert sibling.name == "Singlets (Outside)"
