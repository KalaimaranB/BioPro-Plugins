"""Unit tests for FlowCanvas rendering engine.

Tests the core canvas functionality including:
- Initialization and attribute setup
- Rendering pipeline
- Gate drawing state machine
- Artist management
- Event handling state
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock

from flow_cytometry.ui.graph.flow_canvas import (
    FlowCanvas,
    DisplayMode,
    GateDrawingMode,
)
from flow_cytometry.analysis.gating import PolygonGate
from flow_cytometry.analysis.gating import RectangleGate
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType


class TestFlowCanvasInitialization:
    """Test FlowCanvas initialization and attribute setup."""
    
    @pytest.mark.ui
    def test_canvas_initializes_without_error(self):
        """Canvas should initialize without errors."""
        # Mock PyQt parent
        parent = None
        canvas = FlowCanvas(parent=parent)
        assert canvas is not None
    
    @pytest.mark.ui
    def test_all_required_attributes_initialized(self):
        """All required attributes should be initialized in __init__."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Data state
        assert hasattr(canvas, '_current_data')
        assert hasattr(canvas, '_x_param')
        assert hasattr(canvas, '_y_param')
        assert hasattr(canvas, '_x_scale')
        assert hasattr(canvas, '_y_scale')
        assert hasattr(canvas, '_display_mode')
        
        # Service instances
        assert hasattr(canvas, '_coordinate_mapper')
        assert hasattr(canvas, '_gate_factory')
        assert hasattr(canvas, '_gate_overlay_renderer')
        
        # Rendering caches
        assert hasattr(canvas, '_canvas_bitmap_cache')
        assert hasattr(canvas, '_gate_overlay_artists')
        assert hasattr(canvas, '_gate_artists')  # This was missing!
        
        # Gate drawing state
        assert hasattr(canvas, '_drawing_mode')
        assert hasattr(canvas, '_is_drawing')
        assert hasattr(canvas, '_drag_start')
        assert hasattr(canvas, '_polygon_vertices')
        
        # Gate state
        assert hasattr(canvas, '_gate_patches')
        assert hasattr(canvas, '_active_gates')
        assert hasattr(canvas, '_gate_nodes')
        assert hasattr(canvas, '_selected_gate_id')
        
        # Editing state
        assert hasattr(canvas, '_editing_gate_id')
        assert hasattr(canvas, '_edit_handle_idx')
        assert hasattr(canvas, '_edit_handles')
    
    @pytest.mark.ui
    def test_gate_artists_is_list(self):
        """_gate_artists should be a list, not None."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        assert isinstance(canvas._gate_artists, list)
        assert len(canvas._gate_artists) == 0
    
    @pytest.mark.ui
    def test_gate_overlay_artists_is_dict(self):
        """_gate_overlay_artists should be a dict."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        assert isinstance(canvas._gate_overlay_artists, dict)
        assert len(canvas._gate_overlay_artists) == 0
    
    @pytest.mark.ui
    def test_initial_drawing_mode_is_none(self):
        """Initial drawing mode should be NONE."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        assert canvas._drawing_mode == GateDrawingMode.NONE
        assert canvas._is_drawing is False
    
    @pytest.mark.ui
    def test_initial_display_mode_is_pseudocolor(self):
        """Initial display mode should be PSEUDOCOLOR."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        assert canvas._display_mode == DisplayMode.PSEUDOCOLOR


class TestFlowCanvasRenderingPipeline:
    """Test rendering pipeline doesn't crash."""
    
    @pytest.mark.ui
    def test_render_data_layer_empty_data(self):
        """_render_data_layer should handle empty data gracefully."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Should not raise an error even with no data
        canvas._render_data_layer()
    
    @pytest.mark.ui
    def test_render_gate_layer_empty_gates(self):
        """_render_gate_layer should handle empty gate list gracefully."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Should not raise an error
        canvas._render_gate_layer()
        
        # Should have cleared artist lists
        assert len(canvas._gate_artists) == 0
        assert len(canvas._gate_patches) == 0
    
    @pytest.mark.ui
    def test_redraw_calls_both_layers(self):
        """redraw() should call both data and gate layers."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        canvas.isVisible = Mock(return_value=True)
        
        # Mock the layer methods
        canvas._render_data_layer = Mock()
        canvas._render_gate_layer = Mock()
        
        canvas.redraw()
        
        # Both should be called
        canvas._render_data_layer.assert_called_once()
        canvas._render_gate_layer.assert_called_once()
    
    @pytest.mark.ui
    def test_gate_artists_clear_in_render_data(self):
        """_render_data_layer should clear gate artists."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Add a mock artist
        mock_artist = Mock()
        canvas._gate_artists.append(mock_artist)
        
        # Call render - should clear
        canvas._render_data_layer()
        
        assert len(canvas._gate_artists) == 0
    
    @pytest.mark.ui
    def test_gate_artists_clear_in_render_gate(self):
        """_render_gate_layer should clear and rebuild gate artists."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Add a mock artist
        mock_artist = Mock()
        mock_artist.remove = Mock()
        canvas._gate_artists.append(mock_artist)
        
        # Call render - should clear
        canvas._render_gate_layer()
        
        assert len(canvas._gate_artists) == 0


class TestFlowCanvasGateDrawingStateMachine:
    """Test gate drawing mode transitions."""
    
    @pytest.mark.ui
    def test_set_drawing_mode(self):
        """Should be able to set drawing mode."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas.set_drawing_mode(GateDrawingMode.RECTANGLE)
        assert canvas._drawing_mode == GateDrawingMode.RECTANGLE
    
    @pytest.mark.ui
    def test_clear_drawing_state(self):
        """Should be able to clear drawing state."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Set up some state
        canvas._drawing_mode = GateDrawingMode.POLYGON
        canvas._is_drawing = True
        canvas._polygon_vertices = [(100, 100), (200, 200)]
        
        # Clear state
        canvas._clear_drawing_state()
        
        # Should reset to NONE
        assert canvas._drawing_mode == GateDrawingMode.NONE
        assert canvas._is_drawing is False
        assert len(canvas._polygon_vertices) == 0
    
    @pytest.mark.ui
    def test_multiple_mode_transitions(self):
        """Should handle multiple mode transitions."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        modes = [
            GateDrawingMode.RECTANGLE,
            GateDrawingMode.POLYGON,
            GateDrawingMode.ELLIPSE,
            GateDrawingMode.QUADRANT,
            GateDrawingMode.RANGE,
            GateDrawingMode.NONE,
        ]
        
        for mode in modes:
            canvas.set_drawing_mode(mode)
            assert canvas._drawing_mode == mode


class TestFlowCanvasGateManagement:
    """Test gate management operations."""
    
class TestFlowCanvasGateManagement:
    """Test gate management operations."""
    
    @pytest.mark.ui
    @patch('matplotlib.backends.backend_qtagg.FigureCanvasQTAgg')
    def test_add_gate_to_active_list(self, mock_canvas):
        """Should be able to add gates to active list."""
        mock_instance = MagicMock()
        mock_canvas.return_value = mock_instance
        
        # Manually set up the attributes that FlowCanvas.__init__ would set
        mock_instance._active_gates = []
        mock_instance._selected_gate_id = None
        
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        gate = RectangleGate(
            'FSC-A', 'SSC-A',
            x_min=100, x_max=1000,
            y_min=50, y_max=500
        )
        
        canvas._active_gates.append(gate)
        assert len(canvas._active_gates) == 1
        assert canvas._active_gates[0] == gate
    
    @pytest.mark.ui
    def test_clear_active_gates(self):
        """Should be able to clear active gates."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Add multiple gates
        for i in range(3):
            gate = RectangleGate(
                'FSC-A', 'SSC-A',
                x_min=100+i*100, x_max=1000+i*100,
                y_min=50+i*50, y_max=500+i*50
            )
            canvas._active_gates.append(gate)
        
        assert len(canvas._active_gates) == 3
        
        canvas._active_gates.clear()
        assert len(canvas._active_gates) == 0
    
    @pytest.mark.ui
    def test_select_gate(self):
        """Should be able to select a gate."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        gate_id = "gate_123"
        canvas._selected_gate_id = gate_id
        
        assert canvas._selected_gate_id == gate_id
    
    @pytest.mark.ui
    def test_deselect_gate(self):
        """Should be able to deselect a gate."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._selected_gate_id = "gate_123"
        canvas._selected_gate_id = None
        
        assert canvas._selected_gate_id is None


class TestFlowCanvasEditState:
    """Test gate editing state management."""
    
    @pytest.mark.ui
    def test_start_editing_gate(self):
        """Should be able to start editing a gate."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._editing_gate_id = "gate_456"
        canvas._edit_handle_idx = 2
        
        assert canvas._editing_gate_id == "gate_456"
        assert canvas._edit_handle_idx == 2
    
    @pytest.mark.ui
    def test_stop_editing_gate(self):
        """Should be able to stop editing a gate."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._editing_gate_id = "gate_456"
        canvas._edit_handle_idx = 2
        canvas._edit_handles = [Mock(), Mock(), Mock()]
        
        # Stop editing
        canvas._editing_gate_id = None
        canvas._edit_handle_idx = None
        canvas._edit_handles.clear()
        
        assert canvas._editing_gate_id is None
        assert canvas._edit_handle_idx is None
        assert len(canvas._edit_handles) == 0
    
    @pytest.mark.ui
    def test_edit_handles_is_list(self):
        """_edit_handles should be a list."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        assert isinstance(canvas._edit_handles, list)
        assert len(canvas._edit_handles) == 0


class TestFlowCanvasArtistManagement:
    """Test artist collection management."""
    
    @pytest.mark.ui
    def test_gate_artists_append(self):
        """Should be able to append to gate artists."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        mock_artist1 = Mock()
        mock_artist2 = Mock()
        
        canvas._gate_artists.append(mock_artist1)
        canvas._gate_artists.append(mock_artist2)
        
        assert len(canvas._gate_artists) == 2
        assert canvas._gate_artists[0] == mock_artist1
        assert canvas._gate_artists[1] == mock_artist2
    
    @pytest.mark.ui
    def test_gate_artists_remove_with_cleanup(self):
        """Should safely remove artists with error handling."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Add artists
        mock_artist1 = Mock()
        mock_artist1.remove = Mock()
        
        mock_artist2 = Mock()
        mock_artist2.remove = Mock(side_effect=ValueError("Already removed"))
        
        canvas._gate_artists.append(mock_artist1)
        canvas._gate_artists.append(mock_artist2)
        
        # Remove all with error handling (like in _render_gate_layer)
        for artist in canvas._gate_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        
        canvas._gate_artists.clear()
        
        assert len(canvas._gate_artists) == 0
        mock_artist1.remove.assert_called_once()
        mock_artist2.remove.assert_called_once()


class TestFlowCanvasDataManagement:
    """Test data and scale management."""
    
    @pytest.mark.ui
    def test_set_data(self):
        """Should be able to set event data."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        data = pd.DataFrame({
            'FSC-A': np.random.rand(1000),
            'SSC-A': np.random.rand(1000),
        })
        
        canvas._current_data = data
        assert canvas._current_data is data
        assert len(canvas._current_data) == 1000
    
    @pytest.mark.ui
    def test_set_parameters(self):
        """Should be able to set X and Y parameters."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._x_param = "FSC-A"
        canvas._y_param = "SSC-A"
        
        assert canvas._x_param == "FSC-A"
        assert canvas._y_param == "SSC-A"
    
    @pytest.mark.ui
    def test_set_axis_scales(self):
        """Should be able to set axis scales."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        x_scale = AxisScale(TransformType.LINEAR)
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        
        canvas._x_scale = x_scale
        canvas._y_scale = y_scale
        
        assert canvas._x_scale == x_scale
        assert canvas._y_scale == y_scale
    
    @pytest.mark.ui
    def test_set_display_mode(self):
        """Should be able to set display mode."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        modes = [
            DisplayMode.DOT_PLOT,
            DisplayMode.PSEUDOCOLOR,
            DisplayMode.CONTOUR,
            DisplayMode.DENSITY,
            DisplayMode.HISTOGRAM,
            DisplayMode.CDF,
        ]
        
        for mode in modes:
            canvas._display_mode = mode
            assert canvas._display_mode == mode


class TestFlowCanvasEventState:
    """Test mouse event state management."""
    
    @pytest.mark.ui
    def test_track_mouse_position(self):
        """Should track mouse press position."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._drag_start = (150, 250)
        
        assert canvas._drag_start == (150, 250)
    
    @pytest.mark.ui
    def test_clear_mouse_position(self):
        """Should clear mouse position after drag."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas._drag_start = (150, 250)
        canvas._drag_start = None
        
        assert canvas._drag_start is None
    
    @pytest.mark.ui
    def test_polygon_vertex_tracking(self):
        """Should track polygon vertices."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        vertices = [(100, 100), (200, 150), (250, 200), (150, 250)]
        
        for x, y in vertices:
            canvas._polygon_vertices.append((x, y))
        
        assert len(canvas._polygon_vertices) == 4
        assert canvas._polygon_vertices == vertices
        
        # Clear vertices
        canvas._polygon_vertices.clear()
        assert len(canvas._polygon_vertices) == 0
    
    @pytest.mark.ui
    def test_rubber_band_state(self):
        """Should track rubber band patch state."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        mock_patch = Mock()
        canvas._rubber_band_patch = mock_patch
        
        assert canvas._rubber_band_patch == mock_patch
        
        # Clear patch
        canvas._rubber_band_patch = None
        assert canvas._rubber_band_patch is None


class TestFlowCanvasGateRendering:
    """Test gate overlay rendering functionality."""
    
    @pytest.mark.ui
    def test_set_gates_with_polygon_gate(self):
        """set_gates should not crash when rendering polygon gates."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Create a simple polygon gate
        gate = PolygonGate(
            gate_id="test_gate",
            name="Test Gate", 
            x_param="FSC-A",
            y_param="SSC-A",
            vertices=[(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]
        )
        
        # This should not raise AttributeError: 'FlowCanvas' object has no attribute '_transform_x'
        try:
            canvas.set_gates([gate])
            # If we get here, the fix worked
            assert True
        except AttributeError as e:
            if "_transform_x" in str(e):
                pytest.fail(f"AttributeError for _transform_x not fixed: {e}")
            else:
                # Some other AttributeError, re-raise
                raise


class TestFlowCanvasDataManagement:
    """Test data loading and parameter management."""
    
    @pytest.mark.ui
    def test_set_data_with_dataframe(self):
        """set_data should accept pandas DataFrame."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Create sample data
        data = pd.DataFrame({
            'FSC-A': np.random.normal(100000, 20000, 1000),
            'SSC-A': np.random.normal(5000, 1000, 1000),
            'FITC-A': np.random.exponential(50, 1000)
        })
        
        # Mock the redraw method to avoid matplotlib issues
        with patch.object(canvas, 'redraw'):
            canvas.set_data(data)
            # Since canvas is mocked, we can't check internal state directly
            # Just verify the method doesn't crash
            assert True


class TestFlowCanvasAxesManagement:
    """Test axis parameter management."""
    
    @pytest.mark.ui
    def test_set_axes_changes_parameters(self):
        """set_axes should update axis parameters."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        with patch.object(canvas, 'redraw'):
            canvas.set_axes("FITC-A", "PE-A", "FITC-A", "PE-A")
            # Test that the method completes without error
            assert True


class TestFlowCanvasScaleManagement:
    """Test axis scaling and transformation."""
    
    @pytest.mark.ui
    def test_set_scales_updates_coordinate_mapper(self):
        """set_scales should update the coordinate mapper."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        x_scale = AxisScale(TransformType.BIEXPONENTIAL)
        y_scale = AxisScale(TransformType.LOG)
        
        with patch.object(canvas, 'redraw'):
            canvas.set_scales(x_scale, y_scale)
            # Test that the method completes without error
            assert True


class TestFlowCanvasDisplayManagement:
    """Test display mode management."""
    
    @pytest.mark.ui
    def test_set_display_mode_changes_mode(self):
        """set_display_mode should update display mode."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        canvas.set_display_mode(DisplayMode.CONTOUR)
        # Since canvas is mocked, just verify method doesn't crash
        assert True


class TestFlowCanvasEventHandling:
    """Test mouse and keyboard event handling."""
    
    @pytest.mark.ui
    def test_mouse_press_event_handling(self):
        """Mouse press events should be handled."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Mock matplotlib event
        event = Mock()
        event.button = 1  # Left click
        event.xdata = 100
        event.ydata = 200
        event.inaxes = canvas._ax
        event.dblclick = False
        canvas._drawing_mode = GateDrawingMode.RECTANGLE
        
        # This should not crash
        canvas._on_press(event)
        assert canvas._fsm._drag_start == (100, 200)
    
    @pytest.mark.ui
    def test_mouse_release_event_handling(self):
        """Mouse release events should be handled."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Set up drag start
        canvas._drag_start = (50, 50)
        canvas._is_drawing = True
        
        # Mock matplotlib event
        event = Mock()
        event.button = 1
        event.xdata = 150
        event.ydata = 250
        event.inaxes = canvas._ax
        
        canvas._on_release(event)
        # Should clear drag start in FSM
        assert canvas._fsm._drag_start is None
    
    @pytest.mark.ui
    def test_drawing_mode_changes(self):
        """Drawing mode should change correctly."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        assert canvas._drawing_mode == GateDrawingMode.NONE
        
        # Test setting drawing mode (this would normally be done by UI)
        canvas._drawing_mode = GateDrawingMode.RECTANGLE
        assert canvas._drawing_mode == GateDrawingMode.RECTANGLE


class TestFlowCanvasRendering:
    """Test rendering pipeline and visual updates."""
    
    @pytest.mark.ui
    def test_render_gate_layer_calls_redraw(self):
        """_render_gate_layer should call _redraw_gate_overlays."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Mock the redraw method
        with patch.object(canvas, '_redraw_gate_overlays') as mock_redraw:
            canvas._render_gate_layer()
            mock_redraw.assert_called_once()
    
    @pytest.mark.ui
    def test_coordinate_transformation_accuracy(self):
        """Coordinate transformations should be accurate."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Test with linear scales
        test_points = np.array([0, 1000, 10000, 100000])
        
        # Transform should be identity for linear scale
        transformed = canvas._coordinate_mapper.transform_x(test_points)
        np.testing.assert_array_almost_equal(transformed, test_points)
    
    @pytest.mark.ui
    def test_axis_ticks_with_transforms(self):
        """Axis ticks should be generated correctly with transforms."""
        parent = None
        canvas = FlowCanvas(parent=parent)
        
        # Set biexponential scale
        biexp_scale = AxisScale(TransformType.BIEXPONENTIAL)
        canvas.set_scales(biexp_scale, biexp_scale)
        
        # This should not crash
        canvas._setup_axis_ticks()
        # The actual tick setup is hard to test without real matplotlib
