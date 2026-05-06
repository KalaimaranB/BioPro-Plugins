"""Workflow service for managing serialization and hydration of flow experiments.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional, Any
from pathlib import Path

if TYPE_CHECKING:
    from ...analysis.state import FlowState

class WorkflowService:
    """Handles saving and loading of flow cytometry workflows."""
    
    def __init__(self, state: FlowState):
        self._state = state
        from biopro.sdk.utils.logging import get_logger
        self.logger = get_logger("flow.workflow_service", "flow_cytometry")

    def export_workflow(self) -> dict:
        """Serialize the current state to a workflow dictionary."""
        return self._state.to_workflow_dict()

    def load_workflow(self, payload: dict) -> bool:
        """Restore the state from a workflow dictionary."""
        if not payload:
            self.logger.warning("Empty workflow payload.")
            return False

        self.logger.info("Restoring FlowState from workflow payload...")
        try:
            # Unwrap if the full BioPro envelope (metadata + payload) is passed
            actual_data = payload.get("payload", payload)
            
            # Defer to state for the actual data restoration
            self._state.from_workflow_dict(actual_data)
            
            self.logger.info("Workflow loaded successfully.")
            return True
        except Exception as exc:
            self.logger.exception(f"Failed to load workflow: {exc}")
            return False

    def reload_fcs_data(self, sample_paths: dict[str, str]) -> None:
        """Reload FCS event data from disk for saved samples.
        
        This logic was moved from FlowState to satisfy SRP.
        """
        from ...analysis.fcs_io import load_fcs
        from ...analysis.compensation import apply_compensation

        for sid, path_str in sample_paths.items():
            sample = self._state.experiment.samples.get(sid)
            if sample is None:
                continue

            path = Path(path_str)
            if not path.exists():
                self.logger.warning(
                    f"FCS file no longer exists: {path} (sample: {sample.display_name})"
                )
                continue

            try:
                fcs_data = load_fcs(path)
                
                # Re-apply compensation if it was active when saved
                if sample.is_compensated and self._state.compensation:
                    if not fcs_data.is_compensated:
                        fcs_data.events = apply_compensation(fcs_data, self._state.compensation)
                        fcs_data.is_compensated = True
                        self.logger.info(f"Re-applied BioPro compensation matrix to reloaded sample '{sample.display_name}'")
                
                sample.fcs_data = fcs_data
                self.logger.info(
                    f"Reloaded FCS data for '{sample.display_name}': {fcs_data.num_events} events"
                )
            except Exception as exc:
                self.logger.warning(
                    f"Failed to reload FCS for '{sample.display_name}': {exc}"
                )
