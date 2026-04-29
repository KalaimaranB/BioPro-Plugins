"""Service for managing background statistics computation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ..statistics_analysis import StatisticsAnalysis
from biopro.core.task_scheduler import task_scheduler

if TYPE_CHECKING:
    from ..state import FlowState

logger = logging.getLogger(__name__)

class StatsService:
    """Handles submission and application of population statistics.
    """

    @staticmethod
    def recompute_all_stats(state: FlowState, sample_id: str, callback=None) -> Optional[str]:
        """Submit a background task to recompute all gate statistics for a sample."""
        sample = state.experiment.samples.get(sample_id)
        if sample is None or sample.fcs_data is None:
            return None

        analyzer = StatisticsAnalysis()
        analyzer.target_sample_id = sample_id
        
        worker = task_scheduler.submit(analyzer, state)
        if callback:
            worker.finished.connect(callback)
            
        return worker.task_id
