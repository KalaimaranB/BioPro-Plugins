import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock

from biopro.sdk.core import PluginState
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Experiment, Sample
from .fixtures import *

@pytest.fixture
def empty_state():
    """Returns a fresh FlowState with an empty experiment."""
    state = FlowState()
    state.experiment = Experiment()
    return state

@pytest.fixture
def sample_data():
    """Returns a dummy FCS DataFrame."""
    return pd.DataFrame({
        "FSC-A": np.random.rand(1000) * 1024,
        "SSC-A": np.random.rand(1000) * 1024,
        "FL1-A": np.random.rand(1000) * 100
    })

@pytest.fixture
def sample_with_data(sample_data):
    """Returns a Sample object populated with dummy data."""
    sample = Sample(sample_id="s1", display_name="Sample 1")
    sample.fcs_data = MagicMock()
    sample.fcs_data.events = sample_data
    return sample

@pytest.fixture
def state_with_sample(empty_state, sample_with_data):
    """Returns a FlowState with one sample loaded."""
    empty_state.experiment.samples[sample_with_data.sample_id] = sample_with_data
    return empty_state
