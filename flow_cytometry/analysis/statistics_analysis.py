"""Statistics Analysis — SDK-aligned background worker for population stats.
"""

from __future__ import annotations
from biopro.sdk.utils.logging import get_logger
from typing import Any, Optional

from biopro.sdk.core.analysis import AnalysisBase
from biopro.sdk.core.events import CentralEventBus
from .statistics import compute_statistic, StatType
from . import events as flow_events

logger = get_logger(__name__, "flow_cytometry")

class StatisticsAnalysis(AnalysisBase):
    """Background analyzer for computing population statistics."""

    def __init__(self, plugin_id: str = "flow_cytometry"):
        super().__init__(plugin_id)

    def run(self, state: Any) -> dict[str, Any]:
        """Compute statistics for a sample.
        
        The 'state' here is the FlowState.
        """
        sample_id = getattr(self, "target_sample_id", state.current_sample_id)
        if not sample_id:
            return {"error": "No sample ID specified"}

        sample = state.experiment.samples.get(sample_id)
        if not sample or sample.fcs_data is None:
            return {"error": f"Sample {sample_id} not found or has no data"}

        self.logger.info(f"StatisticsAnalysis: Starting compute for sample {sample_id}")
        
        events = sample.fcs_data.events
        if events is None:
            return {"error": "No events found"}

        total_count = len(events)
        results = {}
        
        # Walk the tree and compute stats
        self._walk_and_compute(sample.gate_tree, events, total_count, total_count, results)
        
        return {
            "sample_id": sample_id,
            "stats": results
        }

    def _walk_and_compute(self, node, parent_events, parent_count, total_count, results):
        """Recursively compute stats for all nodes under ``node``."""
        if self.is_cancelled():
            return

        for child in node.children:
            if child.gate is None:
                continue

            try:
                # Use node-level logic which respects negation
                mask = child.gate.contains(parent_events)
                if child.negated:
                    mask = ~mask
                gated_events = parent_events.loc[mask].copy()
            except Exception as exc:
                self.logger.warning(f"Background Stat computation failed for {child.name}: {exc}")
                self.signals.analysis_error.emit(f"Stat computation failed for {child.name}: {exc}")
                results[child.node_id] = {"count": 0, "pct_parent": 0.0, "pct_total": 0.0}
                continue

            count = len(gated_events)
            node_stats = {
                "count": count,
                "pct_parent": (count / parent_count * 100.0) if parent_count > 0 else 0.0,
                "pct_total": (count / total_count * 100.0) if total_count > 0 else 0.0
            }
            results[child.node_id] = node_stats
            
            # Recurse
            self._walk_and_compute(child, gated_events, count, total_count, results)
