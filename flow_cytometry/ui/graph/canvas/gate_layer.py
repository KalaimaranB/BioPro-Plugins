"""Gate layer rendering for FlowCanvas.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..flow_canvas import FlowCanvas

logger = get_logger(__name__, "flow_cytometry")

class GateLayerRenderer:
    """Handles rendering of gate overlays and labels.
    """

    def __init__(self, canvas: FlowCanvas) -> None:
        self.canvas = canvas

    def render(self) -> None:
        """Draw gate overlays on top of the cached data layer.
        """
        canvas = self.canvas
        # Remove previous gate artists
        for artist in canvas._gate_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        canvas._gate_artists.clear()
        canvas._gate_patches.clear()

        # Draw new gate overlays
        self._redraw_gate_overlays()

        # Re-show instruction text if a tool is active
        from ..flow_canvas import GateDrawingMode
        if canvas._drawing_mode != GateDrawingMode.NONE:
            canvas._show_instruction(canvas._drawing_mode)

        canvas.draw_idle()

    def _redraw_gate_overlays(self) -> None:
        """Draw all active gate overlays on the axes.
        """
        canvas = self.canvas
        ax = canvas._ax
        canvas._gate_patches.clear()
        canvas._gate_overlay_artists.clear()

        recorded_geometries = set()
        from ..flow_canvas import _GATE_PALETTE, _GATE_SELECTED_EDGE, _GATE_LINEWIDTH, _GATE_SELECTED_ALPHA, _GATE_ALPHA
        from biopro.ui.theme import Colors

        for i, gate in enumerate(canvas._active_gates):
            if gate.gate_id in recorded_geometries:
                continue
            recorded_geometries.add(gate.gate_id)

            is_selected = (gate.gate_id == canvas._selected_gate_id)
            color = _GATE_PALETTE[i % len(_GATE_PALETTE)]
            edge_color = _GATE_SELECTED_EDGE if is_selected else color
            
            sharing_nodes = [n for n in canvas._gate_nodes if n.gate and n.gate.gate_id == gate.gate_id]
            if not sharing_nodes:
                continue
            
            # Use the new GateOverlayRenderer service
            artists = canvas._gate_overlay_renderer.render_gate(ax, gate, is_selected, edge_color)

            if artists:
                canvas._gate_overlay_artists[gate.gate_id] = {
                    "patch": artists.patch,
                    "gate": gate,
                    "artists": artists,
                }
                if artists.patch:
                    canvas._gate_artists.append(artists.patch)
                if artists.label_text:
                    canvas._gate_artists.append(artists.label_text)
                if artists.handles:
                    for h in artists.handles.values():
                        canvas._gate_artists.append(h)
