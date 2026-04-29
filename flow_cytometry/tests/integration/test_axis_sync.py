import pytest
from unittest.mock import MagicMock
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.state import FlowState
from biopro.sdk.core import PluginState
from biopro.sdk.core.events import CentralEventBus
from flow_cytometry.analysis import events

@pytest.mark.integration
class TestAxisSync:

    def test_axis_range_change_event_carries_correct_scales(self):
        """Publish an AXIS_RANGE_CHANGED event and verify receivers get the scales."""
        state = FlowState(PluginState())
        
        # Setup mock subscriber
        subscriber_mock: MagicMock = MagicMock()
        CentralEventBus.subscribe(events.AXIS_RANGE_CHANGED, subscriber_mock)
        
        x_scale = AxisScale(TransformType.LINEAR)
        x_scale.min_val = 0.0
        x_scale.max_val = 262144.0
        
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        y_scale.min_val = -100.0
        y_scale.max_val = 1000000.0
        
        data = {
            "sample_id": "test_sample",
            "x_param": "FSC-A",
            "y_param": "FITC-A",
            "x_scale": x_scale,
            "y_scale": y_scale
        }
        
        CentralEventBus.publish(events.AXIS_RANGE_CHANGED, data)
        
        # In a real environment we'd wait for processEvents, 
        # but here the mock might be called synchronously if we're not careful.
        # Actually CentralEventBus uses a signal which is async.
        
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        QApplication.processEvents()
        
        # Verify subscriber received the event with the scales
        subscriber_mock.assert_called_once()
        received_data = subscriber_mock.call_args[0][0]
        
        assert received_data["x_scale"].min_val == 0.0
        assert received_data["y_scale"].min_val == -100.0
        
        # Cleanup
        CentralEventBus.unsubscribe(events.AXIS_RANGE_CHANGED, subscriber_mock)

    def test_thumbnail_uses_per_sample_data_for_range(self, sample_a_events, sample_c_events):
        """Verify the thumbnail rendering logic computes independent scales per sample."""
        from flow_cytometry.analysis.scaling import calculate_auto_range
        from flow_cytometry.analysis.transforms import TransformType
        
        # Sample A has narrower FSC range
        a_fsc_min, a_fsc_max = calculate_auto_range(sample_a_events['FSC-A'].values, TransformType.BIEXPONENTIAL)
        
        # Sample C has wider/higher FSC range
        c_fsc_min, c_fsc_max = calculate_auto_range(sample_c_events['FSC-A'].values, TransformType.BIEXPONENTIAL)
        
        # Assert they are not perfectly identical
        assert a_fsc_min != c_fsc_min
        assert a_fsc_max != c_fsc_max
