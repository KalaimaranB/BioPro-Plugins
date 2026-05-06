"""Gate registry — OCP-compliant extension system for gate types.

Allows registering new gate types and their corresponding drawing handlers
without modifying the core FlowCanvas or GateController logic.
"""

from __future__ import annotations
from typing import Dict, Type, Callable, Optional
from biopro.sdk.utils.logging import get_logger

from ...analysis.gating import Gate

logger = get_logger(__name__, "flow_cytometry")

class GateRegistry:
    """Central registry for gate models and their UI handlers."""
    
    _models: Dict[str, Type[Gate]] = {}
    _drawing_handlers: Dict[str, Callable] = {}
    _overlay_renderers: Dict[str, Callable] = {}

    @classmethod
    def register_gate_type(
        cls, 
        type_name: str, 
        model_class: Type[Gate],
        drawing_handler: Optional[Callable] = None,
        overlay_renderer: Optional[Callable] = None
    ):
        """Register a new gate type with its associated logic."""
        cls._models[type_name] = model_class
        if drawing_handler:
            cls._drawing_handlers[type_name] = drawing_handler
        if overlay_renderer:
            cls._overlay_renderers[type_name] = overlay_renderer
        logger.info(f"Registered gate type: {type_name}")

    @classmethod
    def get_model(cls, type_name: str) -> Optional[Type[Gate]]:
        return cls._models.get(type_name)

    @classmethod
    def get_drawing_handler(cls, type_name: str) -> Optional[Callable]:
        return cls._drawing_handlers.get(type_name)

    @classmethod
    def get_overlay_renderer(cls, type_name: str) -> Optional[Callable]:
        return cls._overlay_renderers.get(type_name)
