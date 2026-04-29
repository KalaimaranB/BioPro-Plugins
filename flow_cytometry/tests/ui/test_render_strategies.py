import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from flow_cytometry.ui.graph.renderers.factory import RenderStrategyFactory
from flow_cytometry.ui.graph.renderers.pseudocolor import PseudocolorStrategy
from flow_cytometry.ui.graph.renderers.dotplot import DotPlotStrategy
from flow_cytometry.ui.graph.renderers.histogram import HistogramStrategy
from flow_cytometry.ui.graph.renderers.contour import ContourStrategy
from flow_cytometry.ui.graph.renderers.cdf import CdfStrategy

@pytest.fixture
def mock_ax():
    ax = MagicMock()
    return ax

@pytest.fixture
def dummy_data():
    x = np.random.normal(100000, 20000, 1000)
    y = np.random.normal(50000, 10000, 1000)
    return x, y

def test_strategy_factory():
    """Verify the factory returns the correct strategies and falls back gracefully."""
    pseudo = RenderStrategyFactory.get_strategy("Pseudocolor")
    assert isinstance(pseudo, PseudocolorStrategy)
    
    # Unknown strategy falls back to Dot Plot
    fallback = RenderStrategyFactory.get_strategy("UnknownStrategyName")
    assert isinstance(fallback, DotPlotStrategy)

def test_pseudocolor_strategy_render(mock_ax, dummy_data):
    x, y = dummy_data
    strategy = PseudocolorStrategy()
    
    strategy.render(
        ax=mock_ax,
        x=x,
        y=y,
        x_param="FSC-A",
        y_param="SSC-A",
        config={}
    )
    # Pseudocolor uses ax.scatter
    mock_ax.scatter.assert_called_once()

def test_dotplot_strategy_render(mock_ax, dummy_data):
    x, y = dummy_data
    strategy = DotPlotStrategy()
    
    strategy.render(
        ax=mock_ax,
        x=x,
        y=y,
        x_param="FSC-A",
        y_param="SSC-A",
        config={}
    )
    mock_ax.scatter.assert_called_once()
    
    # Check that performance optimization configs are passed
    call_kwargs = mock_ax.scatter.call_args[1]
    assert call_kwargs.get("rasterized") is True

def test_histogram_strategy_render(mock_ax, dummy_data):
    x, _ = dummy_data
    strategy = HistogramStrategy()
    
    # Histogram only uses x data, but API takes y=None or ignores it
    strategy.render(
        ax=mock_ax,
        x=x,
        y=None,
        x_param="FSC-A",
        y_param=None,
        config={"bins": 128}
    )
    # Histogram uses ax.fill_between or similar depending on implementation
    assert mock_ax.fill_between.called or mock_ax.plot.called or mock_ax.bar.called

def test_contour_strategy_render(mock_ax, dummy_data):
    x, y = dummy_data
    strategy = ContourStrategy()
    
    strategy.render(
        ax=mock_ax,
        x=x,
        y=y,
        x_param="FSC-A",
        y_param="SSC-A",
        config={"levels": 10}
    )
    # Contour uses ax.contour or ax.contourf
    assert mock_ax.contour.called or mock_ax.contourf.called

def test_cdf_strategy_render(mock_ax, dummy_data):
    x, _ = dummy_data
    strategy = CdfStrategy()
    
    strategy.render(
        ax=mock_ax,
        x=x,
        y=None,
        x_param="FSC-A",
        y_param=None,
        config={}
    )
    # CDF usually uses ax.plot
    assert mock_ax.plot.called
