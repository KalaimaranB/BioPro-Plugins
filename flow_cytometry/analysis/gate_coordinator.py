"""Gate Coordinator — facade for gating operations.

Orchestrates the GateController (analysis logic) and GatePropagator 
(background synchronization) to provide a unified API for the UI.
"""

from biopro.sdk.utils.logging import get_logger
from typing import Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from .state import FlowState
from .gating import Gate, GateNode
from .gate_controller import GateController
from .gate_propagator import GatePropagator

logger = get_logger(__name__, "flow_cytometry")

class GateCoordinator(QObject):
    """Facade for all gating operations in the flow module."""
    
    # Forwarded signals from Controller
    gate_added = pyqtSignal(str, str)        # sample_id, node_id
    gate_removed = pyqtSignal(str, str)      # sample_id, node_id
    gate_renamed = pyqtSignal(str, str)      # sample_id, node_id
    gate_selected = pyqtSignal(str, str)     # sample_id, node_id (can be empty)
    gate_geometry_changed = pyqtSignal(str, str)  # sample_id, gate_id
    gate_stats_updated = pyqtSignal(str, str)  # sample_id, node_id
    all_stats_updated = pyqtSignal(str)      # sample_id
    
    # Forwarded signals from Propagator
    sample_updated = pyqtSignal(str, dict, object)
    propagation_complete = pyqtSignal()
    
    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        self._controller = GateController(state, parent=self)
        self._propagator = GatePropagator(state, parent=self)
        
        # Wire internal signals
        self._controller.propagation_requested.connect(self._propagator.request_propagation)
        
        # Forward signals to facade
        self._controller.gate_added.connect(self.gate_added)
        self._controller.gate_removed.connect(self.gate_removed)
        self._controller.gate_renamed.connect(self.gate_renamed)
        self._controller.gate_selected.connect(self.gate_selected)
        self._controller.gate_geometry_changed.connect(self.gate_geometry_changed)
        self._controller.gate_stats_updated.connect(self.gate_stats_updated)
        self._controller.all_stats_updated.connect(self.all_stats_updated)
        
        self._propagator.sample_updated.connect(self.sample_updated)
        self._propagator.propagation_complete.connect(self.propagation_complete)
        
    @property
    def controller(self) -> GateController:
        return self._controller
        
    @property
    def propagator(self) -> GatePropagator:
        return self._propagator

    # ── Facade API (Mapping to Controller) ────────────────────────────

    def add_gate(self, gate: Gate, sample_id: str, name: Optional[str] = None, parent_node_id: Optional[str] = None) -> Optional[str]:
        return self._controller.add_gate(gate, sample_id, name, parent_node_id)

    def remove_population(self, sample_id: str, node_id: str) -> bool:
        return self._controller.remove_population(sample_id, node_id)

    def rename_population(self, sample_id: str, node_id: str, new_name: str) -> bool:
        return self._controller.rename_population(sample_id, node_id, new_name)

    def modify_gate(self, gate_id: str, sample_id: str, **kwargs) -> bool:
        return self._controller.modify_gate(gate_id, sample_id, **kwargs)

    def split_population(self, sample_id: str, node_id: str) -> Optional[str]:
        return self._controller.split_population(sample_id, node_id)

    def copy_gates_to_group(self, source_sample_id: str) -> int:
        return self._controller.copy_gates_to_group(source_sample_id)

    def get_gates_for_display(self, sample_id: str, parent_node_id: Optional[str] = None) -> Tuple[List[Gate], List[GateNode]]:
        return self._controller.get_gates_for_display(sample_id, parent_node_id)

    def recompute_all_stats(self, sample_id: str):
        self._controller.recompute_all_stats(sample_id)

    def cleanup(self):
        self._propagator.cleanup()
        logger.info("GateCoordinator cleaned up")
