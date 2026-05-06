"""Mouse and keyboard event handlers for FlowCanvas.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from typing import TYPE_CHECKING, List, Tuple, Optional

if TYPE_CHECKING:
    from ..flow_canvas import FlowCanvas

logger = get_logger(__name__, "flow_cytometry")

class CanvasEventHandler:
    """Handles interaction events (mouse, keyboard) for FlowCanvas.
    """

    def __init__(self, canvas: FlowCanvas) -> None:
        self.canvas = canvas

    def handle_press(self, event) -> None:
        """Handle mouse press."""
        canvas = self.canvas
        if event.inaxes != canvas._ax or event.dblclick:
            return
        
        logger.info(f"CanvasEventHandler.handle_press: x={event.xdata:.2f}, y={event.ydata:.2f}")
        canvas._fsm.handle_press(event.xdata, event.ydata, canvas._drawing_mode.value)

    def handle_motion(self, event) -> None:
        """Handle mouse movement."""
        canvas = self.canvas
        if event.inaxes != canvas._ax:
            return
        canvas._fsm.handle_motion(event.xdata, event.ydata, canvas._drawing_mode.value)

    def handle_release(self, event) -> None:
        """Handle mouse release."""
        canvas = self.canvas
        if event.inaxes != canvas._ax:
            canvas._fsm.cancel()
            return
        canvas._fsm.handle_release(event.xdata, event.ydata, canvas._drawing_mode.value)

    def handle_dblclick(self, event) -> None:
        """Handle double-click."""
        canvas = self.canvas
        if not event.dblclick or event.inaxes != canvas._ax:
            return
        canvas._fsm.handle_dblclick(event.xdata, event.ydata, canvas._drawing_mode.value)

    def handle_key_press(self, event) -> None:
        """Handle keyboard press."""
        canvas = self.canvas
        from PyQt6.QtCore import Qt as _Qt
        from ..flow_canvas import GateDrawingMode
        
        if event.key() == _Qt.Key.Key_Escape:
            if canvas._drawing_mode != GateDrawingMode.NONE:
                canvas._cancel_drawing()
                canvas._render_gate_layer()

    # ── Finalization methods (called by FSM) ──────────────────────────

    def finalize_drag_gate(self, x0: float, y0: float, x1: float, y1: float, mode: str) -> None:
        """Finalize a gate drawn by dragging."""
        canvas = self.canvas
        if mode == "rectangle":
            gate = canvas._gate_factory.create_rectangle(x0, y0, x1, y1)
            canvas.gate_created.emit(gate)
        elif mode == "ellipse":
            gate = canvas._gate_factory.create_ellipse(x0, y0, x1, y1)
            canvas.gate_created.emit(gate)
        elif mode == "range":
            gate = canvas._gate_factory.create_range(x0, x1)
            canvas.gate_created.emit(gate)
        canvas._clear_previews()

    def finalize_polygon(self, vertices: List[Tuple[float, float]]) -> None:
        """Finalize a polygon gate."""
        canvas = self.canvas
        gate = canvas._gate_factory.create_polygon(vertices)
        canvas.gate_created.emit(gate)
        canvas._clear_previews()

    def finalize_quadrant(self, x: float, y: float) -> None:
        """Finalize a quadrant gate."""
        canvas = self.canvas
        gate = canvas._gate_factory.create_quadrant(x, y)
        canvas.gate_created.emit(gate)

    def try_select_gate(self, x: float, y: float) -> bool:
        """Check if a click hits any gate overlay and select it."""
        canvas = self.canvas
        hit_id = None
        for gate_id, info in canvas._gate_overlay_artists.items():
            patch = info["patch"]
            if patch.contains_point(canvas._ax.transData.transform((x, y))):
                hit_id = gate_id
                break

        node_id = canvas._find_node_id_for_gate(hit_id) if hit_id else None
        
        if canvas._controller:
            canvas._controller.select_gate(canvas._sample_id, node_id)
        else:
            old_selected = canvas._selected_gate_id
            canvas._selected_gate_id = node_id
            if node_id != old_selected:
                canvas._render_gate_layer()
                canvas.gate_selected.emit(node_id)
        
        return hit_id is not None
