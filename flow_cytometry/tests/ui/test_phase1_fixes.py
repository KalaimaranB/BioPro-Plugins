import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch, call
from PyQt6.QtWidgets import QTreeWidgetItem, QApplication
from PyQt6.QtCore import Qt

from flow_cytometry.ui.widgets.sample_list import SampleList
from flow_cytometry.ui.widgets.gate_hierarchy import GateHierarchy
from flow_cytometry.ui.graph.flow_canvas import FlowCanvas
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Experiment, Sample, Group

class TestSampleListNoneTypeFix:
    """Test fix for NoneType crash in sample_list._on_selection_changed."""

    @pytest.fixture
    def sample_list_widget(self, empty_state, qtbot):
        """Create a SampleList widget for testing."""
        widget = SampleList(state=empty_state)
        qtbot.addWidget(widget)
        return widget

    def test_selection_changed_with_none_current(self, sample_list_widget):
        """_on_selection_changed should handle current=None without crashing."""
        signal_emitted = []
        sample_list_widget.selection_changed.connect(
            lambda sample_id: signal_emitted.append(sample_id)
        )

        try:
            sample_list_widget._on_selection_changed(current=None, previous=None)
            assert True
        except AttributeError as e:
            pytest.fail(f"NoneType crash should be fixed: {e}")

        assert len(signal_emitted) == 0

    def test_selection_changed_with_valid_item(self, sample_list_widget, empty_state):
        """_on_selection_changed should emit signal when current is valid."""
        sample = Sample(
            sample_id="S1",
            display_name="Sample 1",
            role="tube",
            group_ids=["G1"],
        )
        empty_state.experiment.samples["S1"] = sample

        signal_emitted = []
        sample_list_widget.selection_changed.connect(
            lambda sample_id: signal_emitted.append(sample_id)
        )

        mock_item = MagicMock(spec=QTreeWidgetItem)
        mock_item.data.return_value = "S1"

        sample_list_widget._on_selection_changed(current=mock_item, previous=None)
        assert signal_emitted == ["S1"]

class TestGateHierarchyGlobalStrategyDefault:
    """Test that Global Strategy is now the default gating mode."""

    @pytest.fixture
    def gate_hierarchy_widget(self, empty_state, qtbot):
        """Create a GateHierarchy widget for testing."""
        widget = GateHierarchy(state=empty_state)
        qtbot.addWidget(widget)
        return widget

    def test_is_global_mode_default_true(self, gate_hierarchy_widget):
        """_is_global_mode should default to True (Global Strategy)."""
        assert gate_hierarchy_widget._is_global_mode is True

class TestFlowCanvasContextMenuDownload:
    """Test right-click context menu with copy/download options."""

    @pytest.fixture
    def canvas(self, empty_state, qtbot):
        """Create a FlowCanvas for testing."""
        c = FlowCanvas(state=empty_state)
        qtbot.addWidget(c)
        return c

    def test_copy_to_clipboard_method_exists(self, canvas):
        """Canvas should have _copy_to_clipboard method."""
        assert hasattr(canvas, '_copy_to_clipboard')
        assert callable(getattr(canvas, '_copy_to_clipboard'))
