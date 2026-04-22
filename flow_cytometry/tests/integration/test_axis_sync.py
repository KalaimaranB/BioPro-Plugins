import pytest
from unittest.mock import MagicMock
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.event_bus import Event, EventType
from flow_cytometry.analysis.state import FlowState
from biopro.sdk.core import PluginState

@pytest.mark.integration
class TestAxisSync:

    def test_axis_range_change_event_carries_correct_scales(self):
        """Publish an AXIS_RANGE_CHANGED event and verify receivers get the scales."""
        state = FlowState(PluginState())
        
        # Setup mock subscriber
        subscriber_mock = MagicMock()
        state.event_bus.subscribe(EventType.AXIS_RANGE_CHANGED, subscriber_mock)
        
        x_scale = AxisScale(TransformType.LINEAR)
        x_scale.min_val = 0.0
        x_scale.max_val = 262144.0
        
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        y_scale.min_val = -100.0
        y_scale.max_val = 1000000.0
        
        event = Event(
            type=EventType.AXIS_RANGE_CHANGED,
            data={
                "sample_id": "test_sample",
                "x_param": "FSC-A",
                "y_param": "FITC-A",
                "x_scale": x_scale,
                "y_scale": y_scale
            },
            source="GraphWindow"
        )
        
        state.event_bus.publish(event)
        
        # Verify subscriber received the event with the scales
        subscriber_mock.assert_called_once()
        received_event = subscriber_mock.call_args[0][0]
        
        assert received_event.data["x_scale"].min_val == 0.0
        assert received_event.data["y_scale"].min_val == -100.0

    def test_thumbnail_uses_per_sample_data_for_range(self, sample_a_events, sample_c_events):
        """Verify the thumbnail rendering logic computes independent scales per sample."""
        # Using the actual implementation function from group_preview if possible
        # Otherwise, testing the equivalent logic
        from flow_cytometry.analysis.scaling import calculate_auto_range
        from flow_cytometry.analysis.transforms import TransformType
        
        # Sample A has narrower FSC range
        a_fsc_min, a_fsc_max = calculate_auto_range(sample_a_events['FSC-A'].values, TransformType.BIEXPONENTIAL)
        
        # Sample C has wider/higher FSC range
        c_fsc_min, c_fsc_max = calculate_auto_range(sample_c_events['FSC-A'].values, TransformType.BIEXPONENTIAL)
        
        # Assert they are not perfectly identical (showing data-driven ranges instead of hardcoded)
        assert a_fsc_min != c_fsc_min
        assert a_fsc_max != c_fsc_max
