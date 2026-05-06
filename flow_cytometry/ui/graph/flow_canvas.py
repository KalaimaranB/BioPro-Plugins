"""FlowCanvas — embedded matplotlib widget for flow cytometry plots.

This is the core rendering engine for the graph window.  It creates
a ``FigureCanvasQTAgg`` embedded in PyQt6 and handles:
- Scatter (dot) plots
- Pseudocolor (hexbin density) plots
- Contour plots
- Histograms (1-D)
- Density plots (KDE)
- CDF plots
- Interactive gate drawing (Rectangle, Polygon, Ellipse, Quadrant, Range)
- Gate overlay rendering with named, color-coded patches
- Gate selection and editing via drag handles

Mouse events are handled via matplotlib's ``mpl_connect`` system with a
state machine that manages drawing, selection, and editing modes.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QSizePolicy, QLabel

from biopro.ui.theme import Colors

from ...analysis.transforms import TransformType, apply_transform
from ...analysis.scaling import AxisScale, calculate_auto_range
from ...analysis.gating import (
    Gate,
    RectangleGate,
    PolygonGate,
    EllipseGate,
    QuadrantGate,
    RangeGate,
    GateNode,
)

from .flow_services import (
    CoordinateMapper,
    GateFactory,
    GateOverlayRenderer,
)
from .renderers.factory import RenderStrategyFactory
from biopro.sdk.core.events import CentralEventBus
from ...analysis import events

# Decomposed components
from .canvas.data_layer import DataLayerRenderer
from .canvas.gate_layer import GateLayerRenderer
from .canvas.event_handler import CanvasEventHandler

logger = get_logger(__name__, "flow_cytometry")
print(f"DEBUG: flow_canvas.py LOADED from {__file__}")


class DisplayMode(Enum):
    """Available plot display modes."""
    PSEUDOCOLOR = "Pseudocolor"
    DOT_PLOT = "Dot Plot"
    CONTOUR = "Contour"
    DENSITY = "Density"
    HISTOGRAM = "Histogram"
    CDF = "CDF"


class GateDrawingMode(Enum):
    """Active gate drawing tool."""
    NONE = "none"              # Default — pointer / selection mode
    RECTANGLE = "rectangle"
    POLYGON = "polygon"
    ELLIPSE = "ellipse"
    QUADRANT = "quadrant"
    RANGE = "range"


# ── Visual constants ─────────────────────────────────────────────────────────

# Plot area uses a pure white background inside the axes
# so all populations and density hexbins are perfectly visible.
_PLOT_BG = "#FFFFFF"

_MPL_STYLE = {
    "figure.facecolor": "#FFFFFF",
    "axes.facecolor": _PLOT_BG,
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#333333",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "text.color": "#333333",
    "grid.color": "#E0E0E0",  # Light grey for visibility on white background
    "grid.alpha": 0.5,
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
}

# Gate drawing colours (Clean & Professional)
_GATE_EDGE_COLOR = "#000000"  # Black
_GATE_FILL_COLOR = "#000000"
_GATE_ALPHA = 0.05
_GATE_EDGE_ALPHA = 1.0
_GATE_LINEWIDTH = 1.2
_GATE_SELECTED_EDGE = "#2188FF" # Subtle blue for selection
_GATE_SELECTED_ALPHA = 0.10
_RUBBER_BAND_COLOR = "#333333"
_RUBBER_BAND_ALPHA = 0.4

# Vibrant palette for multi-gate plots on white background
_GATE_PALETTE = [
    "#FF0000",   # Red
    "#0000FF",   # Blue
    "#008000",   # Green
    "#FF8C00",   # Dark Orange
    "#8B008B",   # Dark Magenta
]


class FlowCanvas(FigureCanvasQTAgg):
    """Interactive matplotlib canvas for flow cytometry plots.

    Signals:
        point_clicked(x, y):     Emitted on left-click with data coords.
        region_selected(dict):   Emitted when a rectangular selection is made.
        gate_created(Gate):      Emitted when a gate drawing is completed.
        gate_modified(str):      Emitted when a gate is edited (gate_id).
        gate_selected(str):      Emitted when a gate overlay is clicked (gate_id).
    """

    point_clicked = pyqtSignal(float, float)
    region_selected = pyqtSignal(dict)
    gate_created = pyqtSignal(object)       # Gate instance
    gate_modified = pyqtSignal(str)         # gate_id
    gate_selected = pyqtSignal(object)      # gate_id or None
    render_requested = pyqtSignal()         # Emitted on context menu "Render"
    quality_mode_changed = pyqtSignal(str)  # "optimized" or "transparent"
    gate_preview_emitted = pyqtSignal(object) # Temporary gate object

    def __init__(self, state: Optional[FlowState] = None, controller: Optional[GateController] = None, parent=None) -> None:
        # Apply BioPro theme
        import matplotlib
        for key, val in _MPL_STYLE.items():
            matplotlib.rcParams[key] = val

        self._fig = Figure(figsize=(6, 5), dpi=100)
        self._fig.set_facecolor(_PLOT_BG)
        super().__init__(self._fig)
        self.setStyleSheet(f"background-color: {_PLOT_BG};")

        logger.info(f"FlowCanvas.__init__: state={state}, controller={controller}, parent={parent}")
        self._state = state
        self._controller = controller
        self.setParent(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setFocusPolicy(__import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.FocusPolicy.StrongFocus)

        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor(_PLOT_BG)
        self._ax.grid(True, color="#B0B0B0", alpha=0.35, linewidth=0.5)

        # Set fixed subplot margins once — avoids calling tight_layout()
        # which inspects every artist and crashes with non-standard ones.
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)

        # ── Data state ────────────────────────────────────────────────
        self._sample_id: Optional[str] = None
        self._current_data: Optional[pd.DataFrame] = None
        self._x_param: str = "FSC-A"
        self._y_param: str = "SSC-A"
        self._x_scale = AxisScale(TransformType.LINEAR)
        self._y_scale = AxisScale(TransformType.LINEAR)
        self._display_mode = DisplayMode.PSEUDOCOLOR
        self._x_label: str = "FSC-A"
        self._y_label: str = "SSC-A"

        # ── Service instances (SOLID: Separation of concerns) ────────────
        # These services decouple rendering, drawing, and gate creation logic
        self._coordinate_mapper = CoordinateMapper(self._x_scale, self._y_scale)
        self._gate_factory = GateFactory(
            self._x_param, self._y_param, self._x_scale, self._y_scale, self._coordinate_mapper
        )
        self._gate_overlay_renderer = GateOverlayRenderer(self._coordinate_mapper)

        # ── Cached background bitmap ──────────────────────────────────
        # The expensive scatter data is rendered once and cached.
        # Gate overlays are drawn on top without re-rendering scatter.
        self._canvas_bitmap_cache = None  # Matplotlib canvas background bitmap for fast redraw
        self._gate_overlay_artists: dict = {}  # gate_id → OverlayArtists
        self._gate_artists: list = []  # matplotlib patches/lines for all gates

        # ── Gate drawing state machine ────────────────────────────────
        self._drawing_mode = GateDrawingMode.NONE
        
        # Phase 5: Gate Drawing FSM (Manages state, previews, and instructions)
        from .gate_drawing_fsm import GateDrawingFSM
        self._fsm = GateDrawingFSM(self)

        # ── Gate overlays ─────────────────────────────────────────────
        self._gate_patches: dict[str, dict] = {}  # gate_id → patch info
        self._active_gates: list[Gate] = []
        self._gate_nodes: list[GateNode] = []      # for stat labels
        self._selected_gate_id: Optional[str] = None
        self._instruction_text = None  # on-canvas drawing hint

        # ── Setup ──────────────────────────────────────────────────────
        self._max_events: Optional[int] = 100_000  # Default subsampling limit
        self._quality_multiplier: float = 1.0     # Grid resolution scaler
        self._use_cache: bool = False              # DISABLED FOR DEBUGGING

        # ── Gate editing ──────────────────────────────────────────────
        self._editing_gate_id: Optional[str] = None
        self._edit_handle_idx: Optional[int] = None
        self._edit_handles: list = []  # matplotlib artists for handles

        # ── Signals ───────────────────────────────────────────────────
        if self._controller:
            self._controller.gate_geometry_changed.connect(self._on_controller_geometry_changed)
            self._controller.gate_selected.connect(self._on_controller_selected)
            self._controller.gate_removed.connect(self._on_controller_gate_removed)
            self._controller.gate_renamed.connect(self._on_controller_gate_renamed)

        # Mouse event connections
        self._mpl_conn_press = self.mpl_connect("button_press_event", self._on_press)
        self._mpl_conn_release = self.mpl_connect("button_release_event", self._on_release)
        self._cid_motion = self.mpl_connect("motion_notify_event", self._on_motion)
        self._mpl_conn_dblclick = self.mpl_connect("button_press_event", self._on_dblclick)

        # ── Loading overlay ───────────────────────────────────────────
        # A translucent label that sits on top of the canvas to signal
        # that a render is in progress.  Positioned in resizeEvent.
        self._loading_label = QLabel("  ⟳  Rendering…  ", self)
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            "background: rgba(18, 18, 30, 200);"
            "color: #58a6ff;"
            "font-size: 13px;"
            "font-weight: 600;"
            "border-radius: 8px;"
            "padding: 6px 14px;"
        )
        self._loading_label.setVisible(False)
        self._loading_label.raise_()

        # ── Decomposed components ─────────────────────────────────────
        self._data_renderer = DataLayerRenderer(self)
        self._gate_renderer = GateLayerRenderer(self)
        self._event_handler = CanvasEventHandler(self)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Show empty state
        self._show_empty()

    def mouseDoubleClickEvent(self, event) -> None:
        """Intercept double clicks to prevent macOS fullscreen tearing.
        
        On macOS, QMainWindow interprets unhandled double-clicks as a
        title-bar toggle, dropping the app out of full screen. By explicitly
        accepting the event after Matplotlib processes it, we stop the
        bubbling.
        """
        super().mouseDoubleClickEvent(event)
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if getattr(self, "_dirty", False):
            self.redraw()

    def paintEvent(self, event) -> None:
        if not hasattr(self, "_paint_count"): self._paint_count = 0
        self._paint_count += 1
        if self._paint_count <= 5:
            logger.info(f"FlowCanvas.paintEvent {self._paint_count} for {self._x_param}/{self._y_param}")
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        """Keep the loading overlay centered over the canvas."""
        super().resizeEvent(event)
        logger.info(f"FlowCanvas resized: {self.width()}x{self.height()}")
        if hasattr(self, "_loading_label"):
            lw, lh = 160, 36
            x = (self.width() - lw) // 2
            y = (self.height() - lh) // 2
            self._loading_label.setGeometry(x, y, lw, lh)

    # ── coordinate mapping ────────────────────────────────────────────

    def set_sample_id(self, sample_id: str) -> None:
        """Set the sample ID for event publication context."""
        self._sample_id = sample_id

    # ── Public API ────────────────────────────────────────────────────

    def set_data(self, events: pd.DataFrame) -> None:
        """Set the event data for this canvas.

        Args:
            events: DataFrame with columns matching axis parameters.
        """
        self._current_data = events
        self.redraw()

    def set_axes(
        self,
        x_param: str,
        y_param: str,
        x_label: str = "",
        y_label: str = "",
    ) -> None:
        """Update axis parameters and labels.

        Args:
            x_param: Column name for X axis.
            y_param: Column name for Y axis.
            x_label: Display label for X axis.
            y_label: Display label for Y axis.
        """
        self._x_param = x_param
        self._y_param = y_param
        self._x_label = x_label or x_param
        self._y_label = y_label or y_param
        # Update services with new parameters
        self._gate_factory.update_params(x_param, y_param)
        self.redraw()

    def set_scales(
        self,
        x_scale: AxisScale,
        y_scale: AxisScale,
    ) -> None:
        """Update the axis scaling configurations.

        Args:
            x_scale: Scale configuration for X axis.
            y_scale: Scale configuration for Y axis.
        """
        self._x_scale = x_scale
        self._y_scale = y_scale
        # Update services with new scales
        self._coordinate_mapper.update_scales(x_scale, y_scale)
        self._gate_factory.update_scales(x_scale, y_scale)
        self.redraw()

    def set_display_mode(self, mode: DisplayMode) -> None:
        """Change the plot display mode.

        Args:
            mode: One of the :class:`DisplayMode` values.
        """
        self._display_mode = mode
        self.redraw()

    def set_drawing_mode(self, mode: GateDrawingMode) -> None:
        """Set the active gate drawing tool.

        Args:
            mode: The drawing mode to activate.
        """
        self._cancel_drawing()
        self._drawing_mode = mode

        from PyQt6.QtCore import Qt as _Qt
        if mode == GateDrawingMode.NONE:
            self.setCursor(_Qt.CursorShape.ArrowCursor)
            self._hide_instruction()
        else:
            self.setCursor(_Qt.CursorShape.CrossCursor)
            self._show_instruction(mode)

    def set_gates(
        self, gates: list[Gate], gate_nodes: Optional[list[GateNode]] = None
    ) -> None:
        """Set the gates to render as overlays.

        Args:
            gates:      List of Gate objects to render.
            gate_nodes: Optional matching GateNode list for stat labels.
        """
        self._active_gates = gates
        self._gate_nodes = gate_nodes or []
        # Only redraw the gate layer — never re-render the scatter data
        self._render_gate_layer()

    def select_gate(self, gate_id: Optional[str]) -> None:
        """Programmatically select a gate overlay."""
        self._selected_gate_id = gate_id
        self._render_gate_layer()



    def _on_transform_changed(self) -> None:
        """Called when a transform is modified (e.g. logicle params).
        
        Invalidates the bitmap cache so the plot is fully re-rendered
        in the next frame with new scales applied to the data.
        """
        logger.info("FlowCanvas: Transform changed, invalidating cache.")
        self._canvas_bitmap_cache = None
        self.redraw()

    def _auto_range_axes(self) -> None:
        """Request parent window to re-calculate auto-range for active axes."""
        # This is typically called when switching to Full quality
        # to ensure the plot is centered on the real data boundaries.
        parent = self.parent()
        while parent and not hasattr(parent, "_calculate_auto_range"):
            parent = parent.parent()
            
        if parent:
            # We use the parent's logic to compute and apply new scales
            x_min, x_max = parent._calculate_auto_range("x")
            y_min, y_max = parent._calculate_auto_range("y")
            
            # Update local scales (parent will also sync globally)
            parent._x_scale.min_val = x_min
            parent._x_scale.max_val = x_max
            parent._y_scale.min_val = y_min
            parent._y_scale.max_val = y_max
            
            self.set_scales(parent._x_scale, parent._y_scale)
            # Notify the system to refresh thumbnails and sidebar
            parent._notify_axis_change()

    # ── Batch update ───────────────────────────────────────────────

    def begin_update(self) -> None:
        """Start a batch update — suppress intermediate redraws."""
        self._batch_update = True

    def end_update(self) -> None:
        """End batch — perform a single redraw with final state."""
        self._batch_update = False
        self.redraw()

    def redraw(self) -> None:
        """Full redraw: render data layer (expensive) + gate layer (cheap)."""
        if getattr(self, '_batch_update', False):
            return

        # If the canvas is 0x0, defer the redraw until it has a size.
        if self.width() <= 0 or self.height() <= 0:
            logger.warning("Canvas redraw deferred: size is 0x0. Setting timer for retry.")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self.redraw)
            return

        # Removed isVisible guard to ensure rendering even if Qt state is delayed
        self._dirty = False
        logger.info("Canvas redraw triggered: data_size=%s, x=%s, y=%s, size=(%d, %d)", 
                     len(self._current_data) if self._current_data is not None else "None",
                     self._x_param, self._y_param, self.width(), self.height())
        self._canvas_bitmap_cache = None  # Invalidate cached bitmap
        
        self._show_loading()
        
        # Defer the heavy data rendering by 50ms to allow the Qt event loop
        # to process the show_loading() call and paint the overlay.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, self._perform_heavy_redraw)

    def _perform_heavy_redraw(self) -> None:
        try:
            self._render_data_layer()
        except Exception as exc:
            logger.exception("Canvas render failed: %s", exc)
            self._show_error(f"Render error: {exc}")
        finally:
            # Always hide the overlay — even if the render crashed.
            self._hide_loading()
        self._render_gate_layer()
        self.draw() # Forced immediate draw instead of idle

    def _show_loading(self) -> None:
        """Show the loading overlay, keeping it on top."""
        if hasattr(self, "_loading_label"):
            # Re-center in case we haven't had a resizeEvent yet
            lw, lh = 160, 36
            x = max(0, (self.width() - lw) // 2)
            y = max(0, (self.height() - lh) // 2)
            self._loading_label.setGeometry(x, y, lw, lh)
            self._loading_label.setVisible(True)
            self._loading_label.raise_()
            # Force Qt to process the show so the label appears before the
            # blocking matplotlib render begins.
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

    def _hide_loading(self) -> None:
        """Hide the loading overlay."""
        if hasattr(self, "_loading_label"):
            self._loading_label.setVisible(False)

    def _render_data_layer(self) -> None:
        """Render the expensive scatter/histogram data.
        
        Delegated to DataLayerRenderer.
        """
        self._data_renderer.render()

    def _apply_axis_formatting(self) -> None:
        """Apply biological decade formatting to axes if transformed.
        
        For biexponential axes with negative decades (A > 0 or min_val < 0),
        negative ticks (-10³, -10², 0, 10², …) are added to give the classic
        canonical display.
        """
        from matplotlib.ticker import FixedLocator, FixedFormatter
        
        if self._x_scale.transform_type != TransformType.LINEAR:
            raw_ticks, labels = self._build_bio_ticks(
                self._x_scale, self._x_scale.transform_type == TransformType.BIEXPONENTIAL
            )
            disp_ticks = self._coordinate_mapper.transform_x(raw_ticks)
            self._ax.xaxis.set_major_locator(FixedLocator(disp_ticks))
            self._ax.xaxis.set_major_formatter(FixedFormatter(labels))
            
            # Option C: Linear region shading for X
            if self._x_scale.transform_type == TransformType.BIEXPONENTIAL:
                self._add_linear_region_shading("x")
            
        if self._display_mode not in (DisplayMode.HISTOGRAM, DisplayMode.CDF):
            if self._y_scale.transform_type != TransformType.LINEAR:
                raw_ticks, labels = self._build_bio_ticks(
                    self._y_scale, self._y_scale.transform_type == TransformType.BIEXPONENTIAL
                )
                disp_ticks = self._coordinate_mapper.transform_y(raw_ticks)
                self._ax.yaxis.set_major_locator(FixedLocator(disp_ticks))
                self._ax.yaxis.set_major_formatter(FixedFormatter(labels))

                # Option C: Linear region shading for Y
                if self._y_scale.transform_type == TransformType.BIEXPONENTIAL:
                    self._add_linear_region_shading("y")

    def _add_linear_region_shading(self, axis: str) -> None:
        """Add a subtle shaded band to indicate the linear region of biexponential."""
        # Typically +/- 1000 in raw data space is the 'squish' zone
        raw_bounds = np.array([-1000.0, 1000.0])
        if axis == "x":
            disp_bounds = self._coordinate_mapper.transform_x(raw_bounds)
            self._ax.axvspan(disp_bounds[0], disp_bounds[1], color="#000000", alpha=0.03, zorder=0, linewidth=0)
        else:
            disp_bounds = self._coordinate_mapper.transform_y(raw_bounds)
            self._ax.axhspan(disp_bounds[0], disp_bounds[1], color="#000000", alpha=0.03, zorder=0, linewidth=0)

    def _build_bio_ticks(self, scale, is_biex):
        """Build canonical tick positions and labels.
    
        Biexponential: -10^3, 0, 10^3, 10^4, 10^5  (standard)
        Log:            10^3, 10^4, 10^5
        The shading band added by _add_linear_region_shading() is the
        visual indicator for the squish zone — no extra ticks needed.
        """
        import numpy as np
    
        pos_decades = [10**3, 10**4, 10**5]
        pos_labels  = ["$10^3$", "$10^4$", "$10^5$"]
    
        if is_biex:
            # Show negative side only when axis extends below zero
            show_neg = scale.logicle_a > 0 or (
                scale.min_val is not None and scale.min_val < 0
            )
            if show_neg:
                raw = np.array([-10**3, 0] + pos_decades, dtype=float)
                lbl = [r"$-10^3$", "0"] + pos_labels
            else:
                raw = np.array([0] + pos_decades, dtype=float)
                lbl = ["0"] + pos_labels
        else:
            raw = np.array(pos_decades, dtype=float)
            lbl = pos_labels
    
        return raw, lbl

    def _render_gate_layer(self) -> None:
        """Draw gate overlays on top of the cached data layer.
        
        Delegated to GateLayerRenderer.
        """
        self._gate_renderer.render()





    # ── Mouse event handlers — gate drawing state machine ─────────────

    def keyPressEvent(self, event) -> None:
        """Handle keyboard — Escape cancels drawing."""
        self._event_handler.handle_key_press(event)
        super().keyPressEvent(event)

    def _on_press(self, event) -> None:
        """Handle mouse press — start drawing or select gate."""
        self._event_handler.handle_press(event)

    def _on_motion(self, event) -> None:
        """Handle mouse movement — rubber-band preview during drawing."""
        self._event_handler.handle_motion(event)

    def _on_release(self, event) -> None:
        """Handle mouse release — finalize gate drawing."""
        self._event_handler.handle_release(event)

    def _on_dblclick(self, event) -> None:
        """Handle double-click — close polygon."""
        self._event_handler.handle_dblclick(event)

    def _finalize_drag_gate(self, x0: float, y0: float, x1: float, y1: float, mode: str) -> None:
        self._event_handler.finalize_drag_gate(x0, y0, x1, y1, mode)

    def _finalize_rectangle(self, x0, y0, x1, y1):
        # Kept for backward compatibility if needed, but FSM calls _finalize_drag_gate
        self._event_handler.finalize_drag_gate(x0, y0, x1, y1, "rectangle")

    def _finalize_polygon(self, vertices: List[Tuple[float, float]]) -> None:
        self._event_handler.finalize_polygon(vertices)

    def _finalize_ellipse(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self._event_handler.finalize_drag_gate(x0, y0, x1, y1, "ellipse")

    def _finalize_quadrant(self, x: float, y: float) -> None:
        self._event_handler.finalize_quadrant(x, y)

    def _finalize_range(self, x0: float, x1: float) -> None:
        self._event_handler.finalize_drag_gate(x0, 0, x1, 0, "range")

    def _try_select_gate(self, x: float, y: float) -> bool:
        return self._event_handler.try_select_gate(x, y)

    def _find_node_id_for_gate(self, gate_id: str) -> Optional[str]:
        """Look up which node_id corresponds to this gate_id in active nodes."""
        for node in self._gate_nodes:
            if node.gate and node.gate.gate_id == gate_id:
                return node.node_id
        return None

    # ── Controller Event Handlers ─────────────────────────────────────

    def _on_controller_geometry_changed(self, sample_id: str, gate_id: str) -> None:
        """Update a specific gate overlay when its geometry changes elsewhere."""
        if sample_id != self._sample_id:
            return
        
        logger.debug(f"FlowCanvas: Handling geometry change for {gate_id}")
        self.update_gate_overlays()

    def _on_controller_selected(self, sample_id: str, node_id: str) -> None:
        """Update selection highlight when changed globally."""
        if sample_id != self._sample_id:
            return
        
        self._selected_gate_id = node_id if node_id else None
        self.gate_selected.emit(self._selected_gate_id)
        self._render_gate_layer()

    def _on_controller_gate_removed(self, sample_id: str, node_id: str) -> None:
        if sample_id == self._sample_id:
            self.refresh_gates()

    def _on_controller_gate_renamed(self, sample_id: str, node_id: str) -> None:
        if sample_id == self._sample_id:
            self._render_gate_layer()

    def refresh_gates(self) -> None:
        """Fetch the latest gates from the controller and re-render."""
        if self._controller and self._sample_id:
            # Note: parent_node_id could be passed if we want to support nested gating view
            # For now, we assume root-level display or that the controller knows the context.
            gates, nodes = self._controller.get_gates_for_display(self._sample_id)
            self.set_gates(gates, nodes)
        else:
            self._render_gate_layer()

    def update_gate_overlays(self) -> None:
        """Backward-compatible alias for refreshing and re-rendering gates."""
        self.refresh_gates()

    def _cancel_drawing(self) -> None:
        """Cancel the active drawing operation."""
        self._fsm.cancel()
        self._hide_instruction()
        self._clear_previews()

    def _clear_drawing_state(self) -> None:
        """Backward-compatible alias for clearing the drawing state."""
        self._cancel_drawing()
        self._drawing_mode = GateDrawingMode.NONE

    def _setup_axis_ticks(self) -> None:
        """Backward-compatible alias for axis tick setup."""
        self._apply_axis_formatting()

    # ── Instruction overlay helpers ───────────────────────────────────

    _INSTRUCTION_MAP = {
        GateDrawingMode.RECTANGLE: "Click and drag to draw a rectangle",
        GateDrawingMode.POLYGON:   "Click to add points, double-click to close",
        GateDrawingMode.ELLIPSE:   "Click and drag to draw an ellipse",
        GateDrawingMode.QUADRANT:  "Click to place the crosshair",
        GateDrawingMode.RANGE:     "Click and drag horizontally",
    }

    def _show_instruction(self, mode: GateDrawingMode) -> None:
        """Show a drawing instruction overlay on the axes."""
        self._hide_instruction()
        text = self._INSTRUCTION_MAP.get(mode)
        if text:
            self._instruction_text = self._ax.text(
                0.5, 0.02, text,
                transform=self._ax.transAxes,
                ha="center", va="bottom",
                fontsize=10,
                color="#333333",
                alpha=0.7,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFFCC",
                          edgecolor="#CCCCCC", linewidth=0.5),
                zorder=30,
            )
            self.draw_idle()

    def _update_instruction(self, text: str) -> None:
        """Update the instruction text content in-place."""
        if self._instruction_text is not None:
            self._instruction_text.set_text(text)
        else:
            self._instruction_text = self._ax.text(
                0.5, 0.02, text,
                transform=self._ax.transAxes,
                ha="center", va="bottom",
                fontsize=10,
                color="#333333",
                alpha=0.7,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFFCC",
                          edgecolor="#CCCCCC", linewidth=0.5),
                zorder=30,
            )

    def _hide_instruction(self) -> None:
        """Remove the instruction text overlay."""
        if self._instruction_text is not None:
            try:
                self._instruction_text.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
            self._instruction_text = None
            self.draw_idle()

    # ── Internal helpers ──────────────────────────────────────────────

    def _show_empty(self) -> None:
        """Display an empty-state message."""
        logger.info("FlowCanvas._show_empty called (triggering empty state)")
        self._ax.clear()
        self._ax.set_facecolor(_PLOT_BG)
        self._ax.text(
            0.5, 0.5,
            "Load FCS data to visualize",
            transform=self._ax.transAxes,
            ha="center", va="center",
            fontsize=12,
            color="#333333",
            alpha=0.6,
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        self.draw()

    def _show_error(self, msg: str) -> None:
        """Display an error message on the canvas."""
        logger.error(f"FlowCanvas._show_error: {msg}")
        self._ax.clear()
        self._ax.set_facecolor(_PLOT_BG)
        self._ax.text(
            0.5, 0.5,
            f"⚠ {msg}",
            transform=self._ax.transAxes,
            ha="center", va="center",
            fontsize=11,
            color="#FF5252",
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self.draw()

    # ── Context Menu ──────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        """Show context menu on right click."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {Colors.BG_DARK}; color: {Colors.FG_PRIMARY};"
            f" border: 1px solid {Colors.BORDER}; font-size: 11px; }}"
            f"QMenu::item:selected {{ background: {Colors.BG_MEDIUM}; }}"
        )

        # Copy to clipboard
        copy_act = QAction("📋  Copy to Clipboard (PNG)", self)
        copy_act.triggered.connect(self._copy_to_clipboard)
        menu.addAction(copy_act)

        menu.addSeparator()

        # Download submenu
        download_menu = menu.addMenu("💾  Download")
        for fmt, suffix in [("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg")]:
            action = QAction(fmt, self)
            action.triggered.connect(lambda checked=False, f=suffix: self._on_download_plot(f))
            download_menu.addAction(action)

        menu.exec(self.mapToGlobal(pos))

    def _copy_to_clipboard(self) -> None:
        """Render figure to PNG in memory and copy to system clipboard."""
        from PyQt6.QtGui import QImage, QClipboard
        from PyQt6.QtWidgets import QApplication
        import io

        try:
            buf = io.BytesIO()
            self._fig.savefig(buf, format='png', dpi=96, bbox_inches='tight')
            buf.seek(0)
            image = QImage()
            image.loadFromData(buf.read())

            clipboard = QApplication.clipboard()
            clipboard.setImage(image)
            logger.info("Plot copied to clipboard")
        except Exception as e:
            logger.error(f"Failed to copy plot: {e}")

    def _on_download_plot(self, fmt: str) -> None:
        """Download plot in specified format (png, pdf, or svg)."""
        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime

        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"flow_plot_{timestamp}.{fmt}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save plot as {fmt.upper()}",
            default_name,
            f"{fmt.upper()} (*.{fmt})"
        )

        if not file_path:
            return

        try:
            # DPI settings for different formats
            dpi = 300 if fmt == "pdf" else 150
            self._fig.savefig(file_path, format=fmt, dpi=dpi, bbox_inches='tight')
            logger.info(f"Plot saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save plot: {e}")

    def _clear_previews(self) -> None:
        """Clear temporary gate previews across all views."""
        CentralEventBus.publish(events.GATE_PREVIEW, {"gate": None})
