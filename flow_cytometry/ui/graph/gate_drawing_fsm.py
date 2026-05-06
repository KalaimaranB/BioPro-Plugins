"""Gate Drawing State Machine (FSM).

Encapsulates the logic for interactive gate creation (mouse press, motion, release).
This extracts the complex state management from FlowCanvas, making it 
easier to add new interactive gate types.
"""

from __future__ import annotations
from biopro.sdk.utils.logging import get_logger
from enum import Enum, auto
from typing import Optional, List, Tuple, TYPE_CHECKING

logger = get_logger(__name__, "flow_cytometry")

if TYPE_CHECKING:
    from .flow_canvas import FlowCanvas
    from ...analysis.gating import Gate

from matplotlib.patches import (
    Rectangle as MplRectangle,
    Polygon as MplPolygon,
    Ellipse as MplEllipse,
)
from matplotlib.lines import Line2D

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
        self._rubber_band: Optional[object] = None
        self._polygon_vertices: List[Tuple[float, float]] = []
        self._polygon_artists: List[object] = []
        self._instruction_text: Optional[object] = None

    def handle_press(self, x: float, y: float, mode: str):
        """Handle mouse press event."""
        logger.info(f"FSM press: mode={mode}, x={x:.2f}, y={y:.2f}, state={self.state}")
        if mode == "none":
            self.canvas._try_select_gate(x, y)
            return

        if mode == "polygon":
            self.state = DrawingState.POLYGON
            self._polygon_vertices.append((x, y))
            self._draw_polygon_progress()
            return

        if mode == "quadrant":
            self.canvas._finalize_quadrant(x, y)
            return

        # For drag-based gates
        self.state = DrawingState.DRAWING
        self._drag_start = (x, y)

    def handle_motion(self, x: float, y: float, mode: str):
        """Handle mouse motion (rubber-banding or polygon preview)."""
        if self.state == DrawingState.DRAWING and self._drag_start is not None:
            x0, y0 = self._drag_start
            self._draw_rubber_band(x0, y0, x, y, mode)
        elif self.state == DrawingState.POLYGON and self._polygon_vertices:
            self._draw_polygon_progress(current_mouse=(x, y))

    def handle_release(self, x: float, y: float, mode: str):
        """Handle mouse release (finalization)."""
        if self.state != DrawingState.DRAWING or self._drag_start is None:
            return

        x0, y0 = self._drag_start
        self.state = DrawingState.IDLE
        self._drag_start = None
        self._clear_rubber_band()

        # Check if drag was significant
        if abs(x - x0) < 1e-6 and abs(y - y0) < 1e-6:
            return

        self.canvas._finalize_drag_gate(x0, y0, x, y, mode)

    def handle_dblclick(self, x: float, y: float, mode: str):
        """Handle double click (polygon completion)."""
        if mode == "polygon" and len(self._polygon_vertices) >= 3:
            self.canvas._finalize_polygon(list(self._polygon_vertices))
            self._polygon_vertices.clear()
            self._clear_polygon_progress()
            self.state = DrawingState.IDLE

    def cancel(self):
        """Cancel current drawing operation."""
        self.state = DrawingState.IDLE
        self._drag_start = None
        self._polygon_vertices.clear()
        self._clear_rubber_band()
        self._clear_polygon_progress()

    # ── Internal Drawing Helpers ──────────────────────────────────────

    def _draw_rubber_band(self, x0: float, y0: float, x1: float, y1: float, mode: str):
        self._clear_rubber_band()
        ax = self.canvas._ax
        color = "#333333"
        
        if mode == "rectangle":
            self._rubber_band = MplRectangle(
                (min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                linewidth=1.0, edgecolor=color, facecolor=color, alpha=0.1, linestyle="--", zorder=100
            )
        elif mode == "ellipse":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            w, h = abs(x1 - x0), abs(y1 - y0)
            self._rubber_band = MplEllipse(
                (cx, cy), w, h,
                linewidth=1.0, edgecolor=color, facecolor=color, alpha=0.1, linestyle="--", zorder=100
            )
        elif mode == "range":
            ylim = ax.get_ylim()
            self._rubber_band = MplRectangle(
                (min(x0, x1), ylim[0]), abs(x1 - x0), ylim[1] - ylim[0],
                linewidth=1.0, edgecolor=color, facecolor=color, alpha=0.1, linestyle="--", zorder=100
            )

        if self._rubber_band:
            ax.add_patch(self._rubber_band)
            self.canvas.draw_idle()
            
            # Publish temporary gate for subplots
            try:
                from biopro.sdk.core.events import CentralEventBus
                from ...analysis import events
                temp_gate = None
                if mode == "rectangle":
                    temp_gate = self.canvas._gate_factory.create_rectangle(x0, y0, x1, y1)
                elif mode == "ellipse":
                    temp_gate = self.canvas._gate_factory.create_ellipse(x0, y0, x1, y1)
                elif mode == "range":
                    temp_gate = self.canvas._gate_factory.create_range(x0, x1)
                
                if temp_gate:
                    CentralEventBus.publish(events.GATE_PREVIEW, {"gate": temp_gate})
            except Exception as e:
                logger.debug(f"Failed to publish drag preview: {e}")

    def _clear_rubber_band(self):
        if self._rubber_band:
            try: self._rubber_band.remove()
            except: pass
            self._rubber_band = None
            self.canvas.draw_idle()

    def _draw_polygon_progress(self, current_mouse=None):
        self._clear_polygon_progress()
        ax = self.canvas._ax
        
        if not self._polygon_vertices:
            return

        # Draw existing edges
        pts = list(self._polygon_vertices)
        if current_mouse:
            pts.append(current_mouse)

        if len(pts) > 1:
            line = Line2D([p[0] for p in pts], [p[1] for p in pts], 
                          color="#333333", linestyle="--", alpha=0.5, zorder=100)
            ax.add_line(line)
            self._polygon_artists.append(line)

        # Draw vertices
        for x, y in self._polygon_vertices:
            dot = ax.plot(x, y, 'ko', markersize=3, alpha=0.5, zorder=101)[0]
            self._polygon_artists.append(dot)
            
        self.canvas.draw_idle()
        
        # Publish temporary polygon for subplots
        try:
            from biopro.sdk.core.events import CentralEventBus
            from ...analysis import events
            temp_gate = self.canvas._gate_factory.create_polygon(pts)
            CentralEventBus.publish(events.GATE_PREVIEW, {"gate": temp_gate})
        except Exception as e:
            logger.debug(f"Failed to publish polygon preview: {e}")

    def _clear_polygon_progress(self):
        for artist in self._polygon_artists:
            try: artist.remove()
            except: pass
        self._polygon_artists.clear()
        self.canvas.draw_idle()
