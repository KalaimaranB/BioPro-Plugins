"""Service for generating unique population names within a sample."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..experiment import Experiment
    from ..gating import GateNode


class NamingService:
    """Service for generating unique population names within a sample."""

    @staticmethod
    def generate_unique_name(experiment: Experiment, sample_id: str, prefix: str = "Gate") -> str:
        """Generate a name that doesn't collide with existing gates in this sample.
        
        Args:
            experiment: The active experiment model.
            sample_id:  ID of the sample to check.
            prefix:     Base name for the new gate.
            
        Returns:
            A unique name (e.g., 'Gate 3').
        """
        sample = experiment.samples.get(sample_id)
        if sample is None:
            return f"{prefix} 1"

        existing_names: set[str] = set()

        def _collect(node: GateNode) -> None:
            if not node.is_root:
                existing_names.add(node.name)
            for child in node.children:
                _collect(child)

        _collect(sample.gate_tree)

        counter = 1
        while True:
            candidate = f"{prefix} {counter}"
            if candidate not in existing_names:
                return candidate
            counter += 1
