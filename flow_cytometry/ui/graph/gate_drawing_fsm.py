"""Gate Drawing State Machine (FSM).

Encapsulates the logic for interactive gate creation (mouse press, motion, release).
This extracts the complex state management from FlowCanvas, making it 
easier to add new interactive gate types.
"""

from __future__ import annotations
import logging
from enum import Enum, auto
from typing import Optional, List, Tuple, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .flow_canvas import FlowCanvas
    from ...analysis.gating import Gate

class DrawingState(Enum):
    IDLE = auto()
    DRAWING = auto()  # Dragging for Rect/Ellipse/Range
    POLYGON = auto()  # Adding points one by one

class GateDrawingFSM:
    """Manages the interactive drawing process for different gate types."""
    
    def __init__(self, canvas: FlowCanvas):
        self.canvas = canvas
        self.state = DrawingState.IDLE
        self._drag_start: Optional[Tuple[float, float]] = None

    def handle_press(self, x: float, y: float, mode: str):
        """Handle mouse press event."""
        logger.info(f"FSM press: mode={mode}, x={x:.2f}, y={y:.2f}, state={self.state}")
        if mode == "none":
            self.canvas._try_select_gate(x, y)
            return

        if mode == "polygon":
            self.state = DrawingState.POLYGON
            self.canvas._polygon_vertices.append((x, y))
            self.canvas._draw_polygon_progress()
            return

        if mode == "quadrant":
            # Quadrant is a single click
            self.canvas._finalize_quadrant(x, y)
            return

        # For drag-based gates
        self.state = DrawingState.DRAWING
        self._drag_start = (x, y)

    def handle_motion(self, x: float, y: float, mode: str):
        """Handle mouse motion (rubber-banding or polygon preview)."""
        # Excessive logging, but helpful for this debug
        # logger.debug(f"FSM motion: mode={mode}, x={x:.2f}, y={y:.2f}, state={self.state}")
        if self.state == DrawingState.DRAWING and self._drag_start is not None:
            x0, y0 = self._drag_start
            self.canvas._draw_rubber_band(x0, y0, x, y, mode)
        elif self.state == DrawingState.POLYGON and self.canvas._polygon_vertices:
            # Live preview for polygon
            logger.debug(f"FSM polygon preview: vertices={len(self.canvas._polygon_vertices)}, current=({x:.2f}, {y:.2f})")
            self.canvas._draw_polygon_progress(current_mouse=(x, y))

    def handle_release(self, x: float, y: float, mode: str):
        """Handle mouse release (finalization)."""
        if self.state != DrawingState.DRAWING or self._drag_start is None:
            return

        x0, y0 = self._drag_start
        self.state = DrawingState.IDLE
        self._drag_start = None
        self.canvas._clear_rubber_band()

        # Check if drag was significant
        if abs(x - x0) < 1e-6 and abs(y - y0) < 1e-6:
            return

        self.canvas._finalize_drag_gate(x0, y0, x, y, mode)

    def handle_dblclick(self, x: float, y: float, mode: str):
        """Handle double click (polygon completion)."""
        if mode == "polygon" and len(self.canvas._polygon_vertices) >= 3:
            # Finalize polygon
            self.canvas._finalize_polygon(self.canvas._polygon_vertices)
            self.canvas._polygon_vertices.clear()
            self.state = DrawingState.IDLE

    def cancel(self):
        """Cancel current drawing operation."""
        self.state = DrawingState.IDLE
        self._drag_start = None
        self.canvas._polygon_vertices.clear()
        self.canvas._clear_rubber_band()
        self.canvas._clear_polygon_progress()
