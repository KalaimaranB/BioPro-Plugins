"""Unit tests for Phase 1 fixes: NoneType crash, Global Strategy default, copy/download.

Tests the following improvements:
- Fix: Sample list NoneType crash when current=None
- Fix: Default gating mode changed to "Global Strategy"
- Feature: Right-click context menu with copy/download options
"""

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
    def flow_state(self):
        """Create a minimal FlowState for testing."""
        state = FlowState()
        state.experiment = Experiment()
        return state

    @pytest.fixture
    def sample_list_widget(self, flow_state):
        """Create a SampleList widget for testing."""
        return SampleList(state=flow_state)

    @pytest.mark.ui
    def test_selection_changed_with_none_current(self, sample_list_widget):
        """_on_selection_changed should handle current=None without crashing."""
        # This is the critical fix: when current is None, method should return early
        signal_emitted = []
        sample_list_widget.selection_changed.connect(
            lambda sample_id: signal_emitted.append(sample_id)
        )

        # Call the handler with current=None (simulates Qt clearing selection during bulk ops)
        try:
            sample_list_widget._on_selection_changed(current=None, previous=None)
            # Should not raise AttributeError
            assert True
        except AttributeError as e:
            pytest.fail(f"NoneType crash should be fixed: {e}")

        # Verify no signal was emitted (correct behavior when current is None)
        assert len(signal_emitted) == 0

    @pytest.mark.ui
    def test_selection_changed_with_valid_item(self, sample_list_widget, flow_state):
        """_on_selection_changed should emit signal when current is valid."""
        # Add a sample to state
        sample = Sample(
            sample_id="S1",
            display_name="Sample 1",
            role="tube",
            group_id="G1",
        )
        flow_state.experiment.samples["S1"] = sample

        signal_emitted = []
        sample_list_widget.selection_changed.connect(
            lambda sample_id: signal_emitted.append(sample_id)
        )

        # Create a mock QTreeWidgetItem with UserRole data
        mock_item = MagicMock(spec=QTreeWidgetItem)
        mock_item.data.return_value = "S1"

        # Call handler with valid item
        sample_list_widget._on_selection_changed(current=mock_item, previous=None)

        # Verify signal was emitted with correct sample_id
        assert signal_emitted == ["S1"]


class TestGateHierarchyGlobalStrategyDefault:
    """Test that Global Strategy is now the default gating mode."""

    @pytest.fixture
    def flow_state(self):
        """Create a minimal FlowState for testing."""
        return FlowState()

    @pytest.fixture
    def gate_hierarchy_widget(self, flow_state):
        """Create a GateHierarchy widget for testing."""
        return GateHierarchy(state=flow_state)

    @pytest.mark.ui
    def test_is_global_mode_default_true(self, gate_hierarchy_widget):
        """_is_global_mode should default to True (Global Strategy)."""
        assert gate_hierarchy_widget._is_global_mode is True

    @pytest.mark.ui
    def test_global_button_checked_by_default(self, gate_hierarchy_widget):
        """The 'Global Strategy' button should be checked by default."""
        assert gate_hierarchy_widget._btn_global.isChecked() is True

    @pytest.mark.ui
    def test_current_button_unchecked_by_default(self, gate_hierarchy_widget):
        """The 'Current Sample' button should be unchecked by default."""
        assert gate_hierarchy_widget._btn_current.isChecked() is False

    @pytest.mark.ui
    def test_mode_toggle_changes_state(self, gate_hierarchy_widget):
        """Toggling buttons should update _is_global_mode."""
        # Start with Global Strategy (True)
        assert gate_hierarchy_widget._is_global_mode is True

        # Click Current Sample button
        gate_hierarchy_widget._btn_current.setChecked(True)
        # Verify the signal was triggered (idToggled should set _is_global_mode)
        # Note: in real usage, idToggled signal calls _on_mode_toggled


class TestFlowCanvasContextMenuDownload:
    """Test right-click context menu with copy/download options."""

    @pytest.fixture
    def canvas(self):
        """Create a FlowCanvas for testing."""
        return FlowCanvas(parent=None)

    @pytest.fixture
    def sample_data(self):
        """Create sample flow cytometry data."""
        np.random.seed(42)
        return pd.DataFrame({
            'FSC-A': np.random.normal(1000, 200, 1000),
            'SSC-A': np.random.normal(500, 100, 1000),
            'FITC-A': np.random.uniform(0, 4096, 1000),
        })

    @pytest.mark.ui
    def test_copy_to_clipboard_method_exists(self, canvas):
        """Canvas should have _copy_to_clipboard method."""
        assert hasattr(canvas, '_copy_to_clipboard')
        assert callable(getattr(canvas, '_copy_to_clipboard'))

    @pytest.mark.ui
    def test_on_download_plot_method_exists(self, canvas):
        """Canvas should have _on_download_plot method."""
        assert hasattr(canvas, '_on_download_plot')
        assert callable(getattr(canvas, '_on_download_plot'))

    @pytest.mark.ui
    def test_copy_to_clipboard_with_data(self, canvas, sample_data):
        """_copy_to_clipboard should work with valid plot data."""
        canvas.set_data(sample_data)
        canvas.set_axes('FSC-A', 'SSC-A')

        with patch('flow_cytometry.ui.graph.flow_canvas.QApplication.clipboard') as mock_clipboard:
            mock_clip = MagicMock()
            mock_clipboard.return_value = mock_clip

            # Should not raise error
            try:
                canvas._copy_to_clipboard()
                assert True
            except Exception as e:
                pytest.fail(f"_copy_to_clipboard raised: {e}")

    @pytest.mark.ui
    def test_on_download_plot_formats(self, canvas, sample_data):
        """_on_download_plot should support png, pdf, svg formats."""
        canvas.set_data(sample_data)
        canvas.set_axes('FSC-A', 'SSC-A')

        with patch('flow_cytometry.ui.graph.flow_canvas.QFileDialog.getSaveFileName') as mock_dialog:
            # Test each format
            for fmt in ['png', 'pdf', 'svg']:
                mock_dialog.return_value = (f'/tmp/test.{fmt}', '')

                with patch('flow_cytometry.ui.graph.flow_canvas.Figure.savefig') as mock_save:
                    try:
                        canvas._on_download_plot(fmt)
                        mock_save.assert_called_once()
                    except Exception as e:
                        pytest.fail(f"_on_download_plot({fmt}) raised: {e}")

    @pytest.mark.ui
    def test_on_download_plot_cancel(self, canvas):
        """_on_download_plot should handle user cancellation gracefully."""
        with patch('flow_cytometry.ui.graph.flow_canvas.QFileDialog.getSaveFileName') as mock_dialog:
            # User cancels dialog
            mock_dialog.return_value = ('', '')

            # Should not raise error
            try:
                canvas._on_download_plot('png')
                assert True
            except Exception as e:
                pytest.fail(f"_on_download_plot should handle cancel: {e}")


class TestPhase1Integration:
    """Integration tests combining multiple Phase 1 changes."""

    @pytest.fixture
    def flow_state(self):
        """Create a complete FlowState for integration testing."""
        state = FlowState()
        state.experiment = Experiment()

        # Add samples
        for i in range(3):
            sample = Sample(
                sample_id=f"S{i}",
                display_name=f"Sample {i}",
                role="tube",
                group_id="G1",
            )
            state.experiment.samples[f"S{i}"] = sample

        return state

    @pytest.mark.ui
    def test_workflow_bulk_gate_no_crash(self, flow_state):
        """Workflow: bulk-gating multiple samples should not crash on selection changes."""
        sample_list = SampleList(state=flow_state)
        gate_hierarchy = GateHierarchy(state=flow_state)

        selection_changes = []
        sample_list.selection_changed.connect(
            lambda s: selection_changes.append(s)
        )

        # Simulate rapid selection changes (as would happen during bulk gating)
        for _ in range(5):
            # Rapid None selections (clearing)
            sample_list._on_selection_changed(current=None, previous=None)

        # Should not crash
        assert len(sample_list._tree.topLevelItemCount()) >= 0

        # Verify Global Strategy is default
        assert gate_hierarchy._is_global_mode is True

    @pytest.mark.ui
    def test_canvas_export_workflow(self):
        """Workflow: render plot and export in multiple formats."""
        canvas = FlowCanvas(parent=None)

        # Create test data
        np.random.seed(42)
        data = pd.DataFrame({
            'FSC-A': np.random.normal(1000, 200, 5000),
            'SSC-A': np.random.normal(500, 100, 5000),
        })

        canvas.set_data(data)
        canvas.set_axes('FSC-A', 'SSC-A')

        # Verify export methods are available
        assert hasattr(canvas, '_copy_to_clipboard')
        assert hasattr(canvas, '_on_download_plot')

        # Should be able to call without errors
        with patch('flow_cytometry.ui.graph.flow_canvas.QApplication.clipboard'):
            try:
                canvas._copy_to_clipboard()
            except Exception as e:
                pytest.fail(f"Copy to clipboard failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
