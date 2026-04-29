import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Experiment, Sample
from flow_cytometry.analysis.gate_controller import GateController
from flow_cytometry.analysis.population_service import PopulationService
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate
from flow_cytometry.analysis.statistics_analysis import StatisticsAnalysis

@pytest.fixture
def pipeline_state(synthetic_events_medium):
    """Setup a state ready for a full pipeline test."""
    state = FlowState()
    sample = Sample(sample_id="sample_pipeline", display_name="Pipeline Sample")
    
    # Mock FCS data with the medium dataset
    from ..fixtures import MockFcsData
    sample.fcs_data = MockFcsData(synthetic_events_medium)
    state.experiment.samples[sample.sample_id] = sample
    
    state.population_service = PopulationService(state)
    return state

@pytest.fixture
def pipeline_controller(pipeline_state):
    controller = GateController(pipeline_state)
    controller.sync_stats = True # Immediate recomputation for tests
    return controller

def test_full_gating_pipeline(pipeline_controller, pipeline_state):
    """Verify Load -> Gate 1 -> Gate 2 -> Stats -> Hierarchical counts."""
    sample_id = "sample_pipeline"
    total_events = len(pipeline_state.experiment.samples[sample_id].fcs_data.events)
    assert total_events == 10000
    
    # 1. Create a Singlet Gate (Rectangle)
    singlet_gate = RectangleGate(
        x_param="FSC-A", y_param="SSC-A",
        x_min=100000, x_max=200000,
        y_min=50000, y_max=200000
    )
    singlet_node_id = pipeline_controller.add_gate(singlet_gate, sample_id, name="Singlets")
    assert singlet_node_id is not None
    
    # Verify singlet stats computed
    sample = pipeline_state.experiment.samples[sample_id]
    singlet_node = sample.gate_tree.find_node_by_id(singlet_node_id)
    assert singlet_node.statistics is not None
    singlet_count = singlet_node.statistics.get("count")
    assert 0 < singlet_count < total_events
    
    # 2. Create a child CD4+ gate (Polygon) inside Singlets
    cd4_gate = PolygonGate(
        x_param="CD4", y_param="CD8",
        vertices=[(5000, 0), (100000, 0), (100000, 5000), (5000, 5000)]
    )
    cd4_node_id = pipeline_controller.add_gate(cd4_gate, sample_id, name="CD4+", parent_node_id=singlet_node_id)
    assert cd4_node_id is not None
    
    # 3. Verify hierarchical filtering
    cd4_node = sample.gate_tree.find_node_by_id(cd4_node_id)
    assert cd4_node.statistics is not None
    cd4_count = cd4_node.statistics.get("count")
    
    # CD4 count must be less than or equal to singlet count
    assert cd4_count <= singlet_count
    
    # 4. Modify Gate 1 and verify automatic propagation to Gate 2 stats
    # Shrink singlet gate
    pipeline_controller.modify_gate(singlet_gate.gate_id, sample_id, x_min=150000)
    
    # Stats should have recomputed immediately due to sync_stats=True
    new_singlet_count = singlet_node.statistics.get("count")
    new_cd4_count = cd4_node.statistics.get("count")
    
    assert new_singlet_count < singlet_count
    assert new_cd4_count <= new_singlet_count
    
    # 5. Delete Parent and verify child is removed
    pipeline_controller.remove_population(sample_id, singlet_node_id)
    assert sample.gate_tree.find_node_by_id(singlet_node_id) is None
    assert sample.gate_tree.find_node_by_id(cd4_node_id) is None
