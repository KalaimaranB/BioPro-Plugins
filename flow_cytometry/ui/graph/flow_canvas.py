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

import logging
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import (
    Rectangle as MplRectangle,
    Polygon as MplPolygon,
    Ellipse as MplEllipse,
    FancyBboxPatch,
)
from matplotlib.lines import Line2D
from matplotlib import colormaps
from fast_histogram import histogram2d as fast_hist2d

from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QSizePolicy, QLabel

from biopro.ui.theme import Colors

from ...analysis.transforms import TransformType, apply_transform, invert_transform
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

logger = logging.getLogger(__name__)


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
# so the dark purple "turbo" outlier dots are perfectly visible.
_PLOT_BG = "#FFFFFF"

_MPL_STYLE = {
    "figure.facecolor": Colors.BG_DARKEST,
    "axes.facecolor": _PLOT_BG,
    "axes.edgecolor": Colors.BORDER,
    "axes.labelcolor": Colors.FG_SECONDARY,
    "xtick.color": Colors.FG_SECONDARY,
    "ytick.color": Colors.FG_SECONDARY,
    "text.color": Colors.FG_PRIMARY,
    "grid.color": "#B0B0B0",  # Darker grey for visibility on white background
    "grid.alpha": 0.35,
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
}

# Gate drawing colours
_GATE_EDGE_COLOR = "#000000"  # Black
_GATE_FILL_COLOR = "#000000"  # Black
_GATE_ALPHA = 0.05
_GATE_EDGE_ALPHA = 1.0
_GATE_LINEWIDTH = 1.2
_GATE_SELECTED_EDGE = "#2188FF" # Subtle blue for selection
_GATE_SELECTED_ALPHA = 0.10
_RUBBER_BAND_COLOR = "#333333"
_RUBBER_BAND_ALPHA = 0.4

# Different shades of dark for multi-gate plots
_GATE_PALETTE = [
    "#000000",   # Black
    "#333333",   # Dark gray
    "#555555",   # Medium gray
    "#222222",   # Near black
    "#444444",   # Charcoal
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

    def __init__(self, state: Optional[FlowState] = None, parent=None) -> None:
        # Apply BioPro theme
        import matplotlib
        for key, val in _MPL_STYLE.items():
            matplotlib.rcParams[key] = val

        self._fig = Figure(figsize=(6, 5), dpi=100)
        self._fig.set_facecolor(_PLOT_BG)
        super().__init__(self._fig)

        self._state = state
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
        self._is_drawing = False
        self._drag_start: Optional[tuple[float, float]] = None
        self._rubber_band_patch = None
        self._polygon_vertices: list[tuple[float, float]] = []
        self._polygon_marker_lines: list = []
        self._instruction_text = None  # on-canvas drawing hint
        self._closing_line = None      # polygon closing preview line

        # ── Gate overlays ─────────────────────────────────────────────
        self._gate_patches: dict[str, dict] = {}  # gate_id → patch info
        self._active_gates: list[Gate] = []
        self._gate_nodes: list[GateNode] = []      # for stat labels
        self._selected_gate_id: Optional[str] = None

        # ── Rendering constraints ─────────────────────────────────────
        self._render_quality: str = "optimized"  # "optimized" or "transparent"
        self._max_events: Optional[int] = 100_000  # Default subsampling limit
        self._quality_multiplier: float = 1.0     # Grid resolution scaler
        self._use_cache: bool = True              # Use bitmap caching for fast redraws

        # ── Gate editing ──────────────────────────────────────────────
        self._editing_gate_id: Optional[str] = None
        self._edit_handle_idx: Optional[int] = None
        self._edit_handles: list = []  # matplotlib artists for handles

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

    def resizeEvent(self, event) -> None:
        """Keep the loading overlay centered over the canvas."""
        super().resizeEvent(event)
        if hasattr(self, "_loading_label"):
            lw, lh = 160, 36
            x = (self.width() - lw) // 2
            y = (self.height() - lh) // 2
            self._loading_label.setGeometry(x, y, lw, lh)

    # ── coordinate mapping ────────────────────────────────────────────

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

    def _on_quality_mode_changed(self, mode: str) -> None:
        """Handle render quality changes.
        
        Optimized: 100k events, 1x resolution, caching enabled.
        Full: All events, 2x resolution, caching disabled.
        """
        self._render_quality = mode
        if mode == "transparent": # "Full" mode
            self._max_events = None
            self._quality_multiplier = 2.0
            self._use_cache = False
        else: # "optimized"
            self._max_events = 100_000
            self._quality_multiplier = 1.0
            self._use_cache = True
        
        # Notify subscribers (like GraphWindow) that quality changed
        self.quality_mode_changed.emit(mode)
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

        if not self.isVisible():
            self._dirty = True
            return

        self._dirty = False
        self._canvas_bitmap_cache = None  # Invalidate cached bitmap
        self._show_loading()
        try:
            self._render_data_layer()
        except Exception as exc:
            logger.exception("Canvas render failed: %s", exc)
            self._show_error(f"Render error: {exc}")
        finally:
            # Always hide the overlay — even if the render crashed.
            self._hide_loading()
        self._render_gate_layer()

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

        After this runs, we snapshot the axes bitmap so that gate
        overlays can be drawn on top without re-rendering data.
        """
        self._ax.clear()
        # ax.clear() resets facecolor to rcParams default, but re-apply
        # explicitly so the white plot background is always consistent.
        self._ax.set_facecolor(_PLOT_BG)
        self._gate_patches.clear()
        self._edit_handles.clear()
        self._gate_artists.clear()

        if self._current_data is None or len(self._current_data) == 0:
            self._show_empty()
            return

        df = self._current_data

        # Validate columns exist
        if self._x_param not in df.columns:
            self._show_error(f"Channel '{self._x_param}' not found")
            return

        # Get raw data
        x_raw = df[self._x_param].values.astype(np.float64)

        # Histogram mode only needs X
        if self._display_mode == DisplayMode.HISTOGRAM:
            self._draw_histogram(x_raw)
            return
        elif self._display_mode == DisplayMode.CDF:
            self._draw_cdf(x_raw)
            return

        if self._y_param not in df.columns:
            self._show_error(f"Channel '{self._y_param}' not found")
            return

        y_raw = df[self._y_param].values.astype(np.float64)

        # Apply transforms based on AxisScale settings
        x_kwargs = {
            "top": self._x_scale.logicle_t,
            "width": self._x_scale.logicle_w,
            "positive": self._x_scale.logicle_m,
            "negative": self._x_scale.logicle_a,
        } if self._x_scale.transform_type == TransformType.BIEXPONENTIAL else {}
        
        y_kwargs = {
            "top": self._y_scale.logicle_t,
            "width": self._y_scale.logicle_w,
            "positive": self._y_scale.logicle_m,
            "negative": self._y_scale.logicle_a,
        } if self._y_scale.transform_type == TransformType.BIEXPONENTIAL else {}

        # ... 
        x_data = apply_transform(x_raw, self._x_scale.transform_type, **x_kwargs)
        y_data = apply_transform(y_raw, self._y_scale.transform_type, **y_kwargs)

        # 1. Establish stable axis limits BEFORE rendering.
        if self._x_scale.min_val is not None and self._x_scale.max_val is not None:
            x_lim = apply_transform(
                np.array([self._x_scale.min_val, self._x_scale.max_val]),
                self._x_scale.transform_type, **x_kwargs,
            )
            self._ax.set_xlim(x_lim[0], x_lim[1])
        else:
            # FIX: Calculate boundaries using RAW data, then transform the limits
            valid_x_raw = x_raw[np.isfinite(x_raw)]
            if len(valid_x_raw) > 0:
                raw_min, raw_max = calculate_auto_range(valid_x_raw, self._x_scale.transform_type)
                x_lim = apply_transform(
                    np.array([raw_min, raw_max]), 
                    self._x_scale.transform_type, **x_kwargs
                )
                self._ax.set_xlim(x_lim[0], x_lim[1])

        if self._y_scale.min_val is not None and self._y_scale.max_val is not None:
            y_lim = apply_transform(
                np.array([self._y_scale.min_val, self._y_scale.max_val]),
                self._y_scale.transform_type, **y_kwargs,
            )
            self._ax.set_ylim(y_lim[0], y_lim[1])
        else:
            # FIX: Calculate boundaries using RAW data, then transform the limits
            valid_y_raw = y_raw[np.isfinite(y_raw)]
            if len(valid_y_raw) > 0:
                raw_min, raw_max = calculate_auto_range(valid_y_raw, self._y_scale.transform_type)
                y_lim = apply_transform(
                    np.array([raw_min, raw_max]), 
                    self._y_scale.transform_type, **y_kwargs
                )
                self._ax.set_ylim(y_lim[0], y_lim[1])

        # 2. Draw based on mode using the established limits
        if self._display_mode == DisplayMode.DOT_PLOT:
            self._draw_dot(x_data, y_data)
        elif self._display_mode == DisplayMode.PSEUDOCOLOR:
            self._draw_pseudocolor(x_data, y_data)
        elif self._display_mode == DisplayMode.CONTOUR:
            self._draw_contour(x_data, y_data)
        elif self._display_mode == DisplayMode.DENSITY:
            self._draw_density(x_data, y_data)

        # Labels
        self._ax.set_xlabel(self._x_label, fontsize=9, color=Colors.FG_SECONDARY)
        self._ax.set_ylabel(self._y_label, fontsize=9, color=Colors.FG_SECONDARY)
        self._apply_axis_formatting()

        # Event count annotation
        n = len(x_data)
        self._ax.annotate(
            f"{n:,} events",
            xy=(0.98, 0.98),
            xycoords="axes fraction",
            ha="right", va="top",
            fontsize=8,
            color=Colors.FG_DISABLED,
            alpha=0.8,
        )

        self._ax.grid(True, color="#B0B0B0", alpha=0.35, linewidth=0.5)
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        self.draw()  # flush to Qt so we can snapshot

        # Cache the bitmap of the data layer
        try:
            self._canvas_bitmap_cache = self._fig.canvas.copy_from_bbox(self._ax.bbox)
        except Exception:
            self._canvas_bitmap_cache = None

    def _apply_axis_formatting(self) -> None:
        """Apply biological decade formatting to axes if transformed.
        
        For biexponential axes with negative decades (A > 0 or min_val < 0),
        negative ticks (-10³, -10², 0, 10², …) are added to give the classic
        FlowJo-style display.
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
        """Build FlowJo-canonical tick positions and labels.
    
        Biexponential: -10^3, 0, 10^3, 10^4, 10^5  (FlowJo standard)
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

        This is extremely fast because it never touches scatter data.
        """
        # Remove previous gate artists
        for artist in self._gate_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        self._gate_artists.clear()
        self._gate_patches.clear()

        # Draw new gate overlays (this populates self._gate_artists)
        self._redraw_gate_overlays()

        # Re-show instruction text if a tool is active
        if self._drawing_mode != GateDrawingMode.NONE:
            self._show_instruction(self._drawing_mode)

        self.draw_idle()

    # ── Drawing modes ─────────────────────────────────────────────────

    def _draw_dot(self, x: np.ndarray, y: np.ndarray) -> None:
        """Simple scatter plot with small, translucent dots."""
        # Subsample if too many events for performance
        n = len(x)
        if self._max_events is not None and n > self._max_events:
            idx = np.random.choice(n, self._max_events, replace=False)
            x, y = x[idx], y[idx]

        self._ax.scatter(
            x, y,
            s=2,
            c=Colors.ACCENT_PRIMARY,
            alpha=0.25,
            rasterized=True,
            edgecolors="none",
        )

    def _draw_pseudocolor(self, x, y):
        """FlowJo-style pseudocolor with Equal Probability and Axis Pile-up."""
        import numpy as np
        from scipy.ndimage import gaussian_filter
        from scipy.stats import rankdata
        from matplotlib import colormaps
        from fast_histogram import histogram2d as fast_hist2d
    
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]
    
        if len(x_vis) < 10:
            self._draw_dot(x_vis, y_vis)
            return
    
        x_lo, x_hi = self._ax.get_xlim()
        y_lo, y_hi = self._ax.get_ylim()
    
        def _safe_range(lo, hi, data, margin=0.05):
            if not (np.isfinite(lo) and np.isfinite(hi)) or hi - lo < 1e-6:
                p1, p99 = np.percentile(data[np.isfinite(data)], [1, 99])
                span = max(p99 - p1, 1.0)
                return p1 - span * margin, p99 + span * margin
            return lo, hi
    
        x_lo, x_hi = _safe_range(x_lo, x_hi, x_vis)
        y_lo, y_hi = _safe_range(y_lo, y_hi, y_vis)
        
        # FIX 1: Axis Pile-up. Force out-of-bounds data to the visual boundaries
        # so they don't disappear from the density calculation.
        x_vis = np.clip(x_vis, x_lo, x_hi)
        y_vis = np.clip(y_vis, y_lo, y_hi)
    
        # Uniform subsampling
        if self._max_events is not None and len(x_vis) > self._max_events:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(x_vis), self._max_events, replace=False)
            x_vis, y_vis = x_vis[idx], y_vis[idx]
    
        # ── Density estimation ────────────────────────────────────────────────
        # Adaptive bin count and sigma based on event density
        n_points = len(x_vis)
        N_BINS = int(min(512, max(64, np.sqrt(n_points) * 1.5)) * self._quality_multiplier)
        sigma = max(0.8, 1.5 * (N_BINS / 512))

        H = fast_hist2d(
            y_vis, x_vis,
            range=[[y_lo, y_hi], [x_lo, x_hi]],
            bins=N_BINS,
        )
        H_smooth = gaussian_filter(H.astype(np.float64), sigma=sigma)
    
        # ── Per-event density lookup (bilinear interpolation) ─────────────────
        # Nearest-neighbour (H_smooth[y_idx, x_idx]) makes events in the same
        # bin share an identical colour, creating a visible grid / "pixelated"
        # pattern. Bilinear interpolation blends between neighbouring bins for
        # smooth FlowJo-quality density gradients.
        x_span = max(x_hi - x_lo, 1e-12)
        y_span = max(y_hi - y_lo, 1e-12)
        x_frac = np.clip((x_vis - x_lo) / x_span * N_BINS - 0.5, 0, N_BINS - 1)
        y_frac = np.clip((y_vis - y_lo) / y_span * N_BINS - 0.5, 0, N_BINS - 1)
        from scipy.ndimage import map_coordinates
        densities = map_coordinates(H_smooth, [y_frac, x_frac], order=1, mode='nearest')
    
        # FIX 2: Equal Probability (Percentile) Normalization.
        # This converts linear density into a percentile, inflating sparse populations
        # so they get assigned hot colors just like FlowJo does.
        if len(densities) > 0:
            c_plot = rankdata(densities) / len(densities)
        else:
            c_plot = densities
    
        # Z-sort: dense events render on top
        sort_idx = np.argsort(c_plot)
        x_plot = x_vis[sort_idx]
        y_plot = y_vis[sort_idx]
        c_plot_sorted = c_plot[sort_idx]
    
        self._ax.scatter(
            x_plot, y_plot,
            c=c_plot_sorted,
            cmap=colormaps['turbo'],
            vmin=0.0, vmax=1.0,
            s=2.0,
            alpha=0.8,
            edgecolors='none',
            linewidths=0,
            rasterized=True,
        )
    
        self._ax.set_xlim(x_lo, x_hi)
        self._ax.set_ylim(y_lo, y_hi)


    def _draw_contour(self, x: np.ndarray, y: np.ndarray) -> None:
        """Contour density plot using 2D histogram."""
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]

        if len(x_vis) < 50:
            self._draw_dot(x_vis, y_vis)
            return

        x_lo, x_hi = self._ax.get_xlim()
        y_lo, y_hi = self._ax.get_ylim()

        # Adaptive binning for contour
        n_points = len(x_vis)
        n_bins = int(min(256, max(64, np.sqrt(n_points))))
        
        from fast_histogram import histogram2d
        h = histogram2d(y_vis, x_vis, bins=n_bins, range=[[y_lo, y_hi], [x_lo, x_hi]])
        
        # Smooth for cleaner contours
        from scipy.ndimage import gaussian_filter
        sigma = max(0.8, 1.5 * (n_bins / 128))
        h_smooth = gaussian_filter(h.astype(np.float64), sigma=sigma)

        x_grid = np.linspace(x_lo, x_hi, n_bins)
        y_grid = np.linspace(y_lo, y_hi, n_bins)

        self._ax.contourf(
            x_grid, y_grid, h_smooth,
            levels=12,
            cmap="magma",
        )
        self._ax.contour(
            x_grid, y_grid, h_smooth,
            levels=6,
            colors="#FFFFFF",
            alpha=0.3,
            linewidths=0.5,
        )

    def _draw_density(self, x: np.ndarray, y: np.ndarray) -> None:
        """2D density plot using imshow (faster than KDE)."""
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]

        if len(x_vis) < 50:
            self._draw_dot(x_vis, y_vis)
            return

        x_lo, x_hi = self._ax.get_xlim()
        y_lo, y_hi = self._ax.get_ylim()

        n_points = len(x_vis)
        n_bins = int(min(512, max(64, np.sqrt(n_points) * 1.5)))
        
        from fast_histogram import histogram2d
        h = histogram2d(y_vis, x_vis, bins=n_bins, range=[[y_lo, y_hi], [x_lo, x_hi]])
        
        from scipy.ndimage import gaussian_filter
        sigma = max(0.8, 1.5 * (n_bins / 256))
        h_smooth = gaussian_filter(h.astype(np.float64), sigma=sigma)

        # Log scaling for density visualization (FlowJo style)
        h_log = np.log1p(h_smooth)

        self._ax.imshow(
            h_log,
            extent=[x_lo, x_hi, y_lo, y_hi],
            origin='lower',
            cmap="viridis",
            aspect='auto',
            interpolation='gaussian',
        )

    def _draw_histogram(self, x: np.ndarray) -> None:
        """1-D histogram."""
        x_data = apply_transform(
            x, self._x_scale.transform_type,
            top=self._x_scale.logicle_t,
            width=self._x_scale.logicle_w,
            positive=self._x_scale.logicle_m,
            negative=self._x_scale.logicle_a,
        )
        valid = np.isfinite(x_data)
        x_data = x_data[valid]

        if len(x_data) == 0:
            self._show_empty()
            return

        n_points = len(x_data)
        n_bins = min(256, max(64, int(np.sqrt(n_points) * 2)))

        counts, bins, patches = self._ax.hist(
            x_data,
            bins=n_bins,
            color=Colors.ACCENT_PRIMARY,
            alpha=0.7,
            edgecolor="none",
            density=False,
        )
        # Apply padding to top of histogram
        if len(counts) > 0:
            self._ax.set_ylim(0, counts.max() * 1.1)
        self._ax.set_xlabel(self._x_label, fontsize=9, color=Colors.FG_SECONDARY)
        self._ax.set_ylabel("Density", fontsize=9, color=Colors.FG_SECONDARY)

        n = len(x_data)
        self._ax.annotate(
            f"{n:,} events",
            xy=(0.98, 0.98),
            xycoords="axes fraction",
            ha="right", va="top",
            fontsize=8,
            color=Colors.FG_DISABLED,
        )
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        self.draw()

    def _draw_cdf(self, x: np.ndarray) -> None:
        """1-D CDF plot."""
        x_data = apply_transform(
            x, self._x_scale.transform_type,
            top=self._x_scale.logicle_t,
            width=self._x_scale.logicle_w,
            positive=self._x_scale.logicle_m,
            negative=self._x_scale.logicle_a,
        )
        valid = np.isfinite(x_data)
        x_data = np.sort(x_data[valid])

        if len(x_data) == 0:
            self._show_empty()
            return

        cdf = np.arange(1, len(x_data) + 1) / len(x_data)
        self._ax.plot(
            x_data, cdf,
            color=Colors.ACCENT_PRIMARY,
            linewidth=1.5,
        )
        self._ax.set_xlabel(self._x_label, fontsize=9, color=Colors.FG_SECONDARY)
        self._ax.set_ylabel("CDF", fontsize=9, color=Colors.FG_SECONDARY)
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        self.draw()

    # ── Gate overlay rendering ────────────────────────────────────────

    def _redraw_gate_overlays(self) -> None:
        """Draw all active gate overlays on the axes.
        
        All created artists are appended to self._gate_artists for
        lightweight cleanup by _render_gate_layer().
        """
        self._gate_patches.clear()

        recorded_geometries = set()
        for i, gate in enumerate(self._active_gates):
            if gate.gate_id in recorded_geometries:
                continue
            recorded_geometries.add(gate.gate_id)

            # Base style
            is_selected = (gate.gate_id == self._selected_gate_id)
            color = _GATE_PALETTE[i % len(_GATE_PALETTE)]
            edge_color = _GATE_SELECTED_EDGE if is_selected else color
            lw = 3.0 if is_selected else max(_GATE_LINEWIDTH * 0.5, 0.8)
            
            fill_alpha = _GATE_SELECTED_ALPHA if is_selected else max(_GATE_ALPHA * 0.2, 0.05)
            
            # Find all nodes sharing this gate to determine style and labels
            sharing_nodes = [n for n in self._gate_nodes if n.gate and n.gate.gate_id == gate.gate_id]
            if not sharing_nodes:
                continue
            
            # Use the style of the first node for the primary boundary
            primary_node = sharing_nodes[0]
            ls = "-"
            if primary_node.negated:
                ls = ":" if not is_selected else "--"
                edge_color = Colors.ACCENT_NEGATIVE if not is_selected else edge_color

            # We have sharing_nodes populated above

            patch = None

            if isinstance(gate, RectangleGate):
                x_min = self._coordinate_mapper.transform_x(np.array([gate.x_min]))[0] if np.isfinite(gate.x_min) else self._ax.get_xlim()[0]
                x_max = self._coordinate_mapper.transform_x(np.array([gate.x_max]))[0] if np.isfinite(gate.x_max) else self._ax.get_xlim()[1]
                y_min = self._coordinate_mapper.transform_y(np.array([gate.y_min]))[0] if np.isfinite(gate.y_min) else self._ax.get_ylim()[0]
                y_max = self._coordinate_mapper.transform_y(np.array([gate.y_max]))[0] if np.isfinite(gate.y_max) else self._ax.get_ylim()[1]

                patch = MplRectangle(
                    (x_min, y_min),
                    x_max - x_min,
                    y_max - y_min,
                    linewidth=lw,
                    edgecolor=edge_color,
                    facecolor=color,
                    alpha=fill_alpha,
                    linestyle=ls,
                    zorder=10,
                )
                self._ax.add_patch(patch)
                self._gate_artists.append(patch)
                self._draw_node_labels(sharing_nodes, (x_min + (x_max - x_min)*0.02, y_max - (y_max - y_min)*0.05), is_selected, va="top")

            elif isinstance(gate, PolygonGate):
                if len(gate.vertices) >= 3:
                    tx = self._coordinate_mapper.transform_x(np.array([v[0] for v in gate.vertices]))
                    ty = self._coordinate_mapper.transform_y(np.array([v[1] for v in gate.vertices]))
                    transformed_vertices = list(zip(tx, ty))
                    patch = MplPolygon(
                        transformed_vertices,
                        closed=True,
                        linewidth=lw,
                        edgecolor=edge_color,
                        facecolor=color,
                        alpha=fill_alpha,
                        linestyle="--" if not is_selected else "-",
                        zorder=10,
                    )
                    self._ax.add_patch(patch)
                    self._gate_artists.append(patch)
                    self._draw_node_labels(sharing_nodes, (np.mean(tx), np.mean(ty)), is_selected, ha="center", va="center")

            elif isinstance(gate, EllipseGate):
                # Sample the ellipse and transform the points to render properly in non-linear spaces
                theta = np.linspace(0, 2*np.pi, 64)
                cos_a, sin_a = np.cos(np.radians(gate.angle)), np.sin(np.radians(gate.angle))
                x_edge = gate.center[0] + gate.width * np.cos(theta) * cos_a - gate.height * np.sin(theta) * sin_a
                y_edge = gate.center[1] + gate.width * np.cos(theta) * sin_a + gate.height * np.sin(theta) * cos_a
                
                tx_edge = self._coordinate_mapper.transform_x(x_edge)
                ty_edge = self._coordinate_mapper.transform_y(y_edge)
                transformed_vertices = list(zip(tx_edge, ty_edge))

                patch = MplPolygon(
                    transformed_vertices,
                    closed=True,
                    linewidth=lw,
                    edgecolor=edge_color,
                    facecolor=color,
                    alpha=fill_alpha,
                    linestyle=ls,
                    zorder=10,
                )
                self._ax.add_patch(patch)
                self._gate_artists.append(patch)

                cx = self._coordinate_mapper.transform_x(np.array([gate.center[0]]))[0]
                cy = self._coordinate_mapper.transform_y(np.array([gate.center[1]]))[0]
                self._draw_node_labels(sharing_nodes, (cx, cy), is_selected, ha="center", va="center")

            elif isinstance(gate, QuadrantGate):
                x_mid = self._coordinate_mapper.transform_x(np.array([gate.x_mid]))[0]
                y_mid = self._coordinate_mapper.transform_y(np.array([gate.y_mid]))[0]
                xlim = self._ax.get_xlim()
                ylim = self._ax.get_ylim()

                # Draw crosshair lines
                vl = self._ax.axvline(
                    x_mid, color=edge_color,
                    linewidth=lw, linestyle="--",
                    alpha=0.7, zorder=10,
                )
                self._gate_artists.append(vl)
                hl = self._ax.axhline(
                    y_mid, color=edge_color,
                    linewidth=lw, linestyle="--",
                    alpha=0.7, zorder=10,
                )
                self._gate_artists.append(hl)

                # Quadrant labels
                q_nodes = sharing_nodes[0].children if sharing_nodes else []
                if len(q_nodes) == 4:
                    q_labels = [self._format_gate_label(None, n) for n in q_nodes]
                else:
                    q_labels = ["Q1 ++", "Q2 −+", "Q3 −−", "Q4 +−"]

                q_positions = [
                    (x_mid + (xlim[1] - x_mid) * 0.5, y_mid + (ylim[1] - y_mid) * 0.5),
                    (xlim[0] + (x_mid - xlim[0]) * 0.5, y_mid + (ylim[1] - y_mid) * 0.5),
                    (xlim[0] + (x_mid - xlim[0]) * 0.5, ylim[0] + (y_mid - ylim[0]) * 0.5),
                    (x_mid + (xlim[1] - x_mid) * 0.5, ylim[0] + (y_mid - ylim[0]) * 0.5),
                ]
                for ql, (qx, qy) in zip(q_labels, q_positions):
                    txt = self._ax.annotate(
                        ql,
                        xy=(qx, qy),
                        fontsize=10, 
                        color="#000000",
                        fontweight="bold",
                        ha="center", va="center",
                        zorder=12,
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFFCC", edgecolor="#CCCCCC", linewidth=0.5)
                    )
                    self._gate_artists.append(txt)

            elif isinstance(gate, RangeGate):
                low = self._coordinate_mapper.transform_x(np.array([gate.low]))[0] if np.isfinite(gate.low) else self._ax.get_xlim()[0]
                high = self._coordinate_mapper.transform_x(np.array([gate.high]))[0] if np.isfinite(gate.high) else self._ax.get_xlim()[1]
                ylim = self._ax.get_ylim()

                patch = MplRectangle(
                    (low, ylim[0]),
                    high - low,
                    ylim[1] - ylim[0],
                    linewidth=lw,
                    edgecolor=edge_color,
                    facecolor=color,
                    alpha=fill_alpha * 0.6,
                    zorder=10,
                )
                self._ax.add_patch(patch)
                self._gate_artists.append(patch)

                # Boundary lines
                vl1 = self._ax.axvline(
                    low, color=edge_color, linewidth=lw,
                    linestyle="--", alpha=0.7, zorder=11,
                )
                self._gate_artists.append(vl1)
                vl2 = self._ax.axvline(
                    high, color=edge_color, linewidth=lw,
                    linestyle="--", alpha=0.7, zorder=11,
                )
                self._gate_artists.append(vl2)

                cx = low + (high - low) * 0.5
                cy = ylim[1] * 0.95
                self._draw_node_labels(sharing_nodes, (cx, cy), is_selected, ha="center", va="top")

            # Store patch reference for hit-testing
            if patch is not None:
                self._gate_overlay_artists[gate.gate_id] = {
                    "patch": patch,
                    "gate": gate,
                    "color": color,
                }

    def _draw_node_labels(
        self, 
        nodes: list[GateNode], 
        pos: tuple[float, float], 
        is_selected: bool,
        **text_kwargs
    ) -> None:
        """Draw labels for all populations sharing a gate, offset vertically."""
        for i, node in enumerate(nodes):
            label_text = self._format_gate_label(node.gate, node)
            color = "#000000" # Pure black text for all labels
            if is_selected:
                color = "#000000" # Stay black but maybe bolded via kwargs

            # Vertical offset: 14 points per label
            direction = -1 if text_kwargs.get("va") == "top" else 1
            y_off = 14 * i * direction
            
            txt = self._ax.annotate(
                label_text,
                xy=pos,
                xytext=(0, y_off),
                textcoords="offset points",
                fontsize=10,
                color="#000000",
                fontweight="bold",
                zorder=12 + i,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFFCC", edgecolor="#CCCCCC", linewidth=0.5),
                **text_kwargs
            )
            self._gate_artists.append(txt)

    def _format_gate_label(
        self, gate: Gate, node: Optional[GateNode] = None
    ) -> str:
        """Format a gate label with indentation, negation, and statistics."""
        if node:
            name = node.name
        else:
            prefix = "NOT " if gate.negated else ""
            name = prefix + gate.name

        # Indentation based on tree depth
        indent = ""
        if node:
            depth = 0
            curr = node
            while curr.parent:
                depth += 1
                curr = curr.parent
            indent = "  " * (max(0, depth - 1)) # Indent relative to plot population

        label = f"{indent}{name}"
        
        if node and node.statistics:
            count = node.statistics.get("count", "")
            pct = node.statistics.get("pct_parent", "")
            
            if count:
                label += f"\n{indent}{int(count):,}"
            if pct:
                label += f" ({pct:.1f}%)"
        return label

    # ── Mouse event handlers — gate drawing state machine ─────────────

    def keyPressEvent(self, event) -> None:
        """Handle keyboard — Escape cancels drawing."""
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape:
            if self._drawing_mode != GateDrawingMode.NONE:
                self._cancel_drawing()
                self._render_gate_layer()  # clean up any artifacts
        super().keyPressEvent(event)

    def _on_press(self, event) -> None:
        """Handle mouse press — start drawing or select gate."""
        if event.inaxes != self._ax:
            return
        if event.dblclick:
            return  # handled by _on_dblclick

        x, y = event.xdata, event.ydata

        # ── NONE mode: select existing gate ───────────────────────────
        if self._drawing_mode == GateDrawingMode.NONE:
            self._try_select_gate(x, y)
            return

        # ── POLYGON mode: add vertex on each click ────────────────────
        if self._drawing_mode == GateDrawingMode.POLYGON:
            self._polygon_vertices.append((x, y))
            self._draw_polygon_progress()
            return

        # ── QUADRANT mode: single click to place crosshair ────────────
        if self._drawing_mode == GateDrawingMode.QUADRANT:
            self._finalize_quadrant(x, y)
            return

        # ── RECTANGLE / ELLIPSE / RANGE: start drag ───────────────────
        self._drag_start = (x, y)
        self._is_drawing = True

    def _on_motion(self, event) -> None:
        """Handle mouse movement — rubber-band preview during drawing."""
        if event.inaxes != self._ax:
            return

        if not self._is_drawing or self._drag_start is None:
            return

        x0, y0 = self._drag_start
        x1, y1 = event.xdata, event.ydata

        # Remove previous rubber band
        self._clear_rubber_band()

        if self._drawing_mode == GateDrawingMode.RECTANGLE:
            self._rubber_band_patch = MplRectangle(
                (min(x0, x1), min(y0, y1)),
                abs(x1 - x0), abs(y1 - y0),
                linewidth=1.5,
                edgecolor=_RUBBER_BAND_COLOR,
                facecolor=_RUBBER_BAND_COLOR,
                alpha=0.2,
                linestyle=":",
                zorder=20,
            )
            self._ax.add_patch(self._rubber_band_patch)

        elif self._drawing_mode == GateDrawingMode.ELLIPSE:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            w, h = abs(x1 - x0), abs(y1 - y0)
            self._rubber_band_patch = MplEllipse(
                (cx, cy), w, h,
                linewidth=1.5,
                edgecolor=_RUBBER_BAND_COLOR,
                facecolor=_RUBBER_BAND_COLOR,
                alpha=0.2,
                linestyle=":",
                zorder=20,
            )
            self._ax.add_patch(self._rubber_band_patch)

        elif self._drawing_mode == GateDrawingMode.RANGE:
            ylim = self._ax.get_ylim()
            self._rubber_band_patch = MplRectangle(
                (min(x0, x1), ylim[0]),
                abs(x1 - x0), ylim[1] - ylim[0],
                linewidth=1.5,
                edgecolor=_RUBBER_BAND_COLOR,
                facecolor=_RUBBER_BAND_COLOR,
                alpha=0.2,
                linestyle=":",
                zorder=20,
            )
            self._ax.add_patch(self._rubber_band_patch)

        # Publish preview event for Group Preview
        if self._state and self._state.event_bus:
            # Create a temporary gate object for preview
            temp_gate = None
            if self._drawing_mode == GateDrawingMode.RECTANGLE:
                temp_gate = self._gate_factory.create_rectangle(x0, y0, x1, y1)
            elif self._drawing_mode == GateDrawingMode.ELLIPSE:
                temp_gate = self._gate_factory.create_ellipse(x0, y0, x1, y1)
            elif self._drawing_mode == GateDrawingMode.RANGE:
                temp_gate = self._gate_factory.create_range(x0, x1)
            
            if temp_gate:
                from ...analysis.event_bus import Event, EventType
                self._state.event_bus.publish(Event(
                    EventType.GATE_PREVIEW,
                    data={"gate": temp_gate, "sample_id": getattr(self, '_sample_id', None)},
                    source="flow_canvas"
                ))

        self.draw_idle()

    def _on_release(self, event) -> None:
        """Handle mouse release — finalize gate drawing."""
        if event.inaxes != self._ax:
            self._cancel_drawing()
            return

        if not self._is_drawing or self._drag_start is None:
            return

        x0, y0 = self._drag_start
        x1, y1 = event.xdata, event.ydata
        self._is_drawing = False
        self._drag_start = None
        self._clear_rubber_band()

        # Skip if the drag was too small (accidental click)
        drag_dist = max(abs(x1 - x0), abs(y1 - y0))
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        threshold = min(xlim[1] - xlim[0], ylim[1] - ylim[0]) * 0.005
        if drag_dist < threshold:
            self._clear_previews()
            return

        if self._drawing_mode == GateDrawingMode.RECTANGLE:
            self._finalize_rectangle(x0, y0, x1, y1)
        elif self._drawing_mode == GateDrawingMode.ELLIPSE:
            self._finalize_ellipse(x0, y0, x1, y1)
        elif self._drawing_mode == GateDrawingMode.RANGE:
            self._finalize_range(x0, x1)
        
        self._clear_previews()

    def _on_dblclick(self, event) -> None:
        """Handle double-click — close polygon."""
        if not event.dblclick or event.inaxes != self._ax:
            return

        if (self._drawing_mode == GateDrawingMode.POLYGON
                and len(self._polygon_vertices) >= 3):
            # Remove the extra vertex added by the dblclick press event
            if len(self._polygon_vertices) > 3:
                self._polygon_vertices.pop()
            self._finalize_polygon()
            self._clear_previews()

    # ── Gate finalization ─────────────────────────────────────────────

    def _finalize_rectangle(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """Create a RectangleGate from the drawn rectangle."""
        gate = self._gate_factory.create_rectangle(x0, y0, x1, y1)
        self.gate_created.emit(gate)

    def _finalize_polygon(self) -> None:
        """Create a PolygonGate from the accumulated vertices."""
        gate = self._gate_factory.create_polygon(self._polygon_vertices)
        self._polygon_vertices.clear()
        self._clear_polygon_progress()
        self.gate_created.emit(gate)

    def _finalize_ellipse(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """Create an EllipseGate from the drawn bounding box."""
        gate = self._gate_factory.create_ellipse(x0, y0, x1, y1)
        self.gate_created.emit(gate)

    def _finalize_quadrant(self, x: float, y: float) -> None:
        """Create a QuadrantGate at the clicked position."""
        gate = self._gate_factory.create_quadrant(x, y)
        self.gate_created.emit(gate)

    def _finalize_range(self, x0: float, x1: float) -> None:
        """Create a RangeGate from the drawn range."""
        gate = self._gate_factory.create_range(x0, x1)
        self.gate_created.emit(gate)

    # ── Gate selection ────────────────────────────────────────────────

    def _try_select_gate(self, x: float, y: float) -> None:
        """Check if a click hits any gate overlay and select it."""
        hit_id = None

        for gate_id, info in self._gate_overlay_artists.items():
            patch = info["patch"]
            if patch.contains_point(self._ax.transData.transform((x, y))):
                hit_id = gate_id
                break

        old_selected = self._selected_gate_id
        self._selected_gate_id = hit_id

        if hit_id != old_selected:
            self._render_gate_layer()
            self.gate_selected.emit(hit_id)

    # ── Rubber-band and polygon progress helpers ──────────────────────

    def _clear_rubber_band(self) -> None:
        """Remove the current rubber-band preview patch."""
        if self._rubber_band_patch is not None:
            try:
                self._rubber_band_patch.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
            self._rubber_band_patch = None

    def _draw_polygon_progress(self) -> None:
        """Draw vertices, connecting lines, and closing preview for polygon."""
        self._clear_polygon_progress()

        if len(self._polygon_vertices) < 1:
            return

        xs = [v[0] for v in self._polygon_vertices]
        ys = [v[1] for v in self._polygon_vertices]

        # Vertex markers
        line, = self._ax.plot(
            xs, ys, "o",
            color=_GATE_EDGE_COLOR,
            markersize=6,
            alpha=0.9,
            zorder=20,
        )
        self._polygon_marker_lines.append(line)

        # Connecting lines
        if len(self._polygon_vertices) >= 2:
            line2, = self._ax.plot(
                xs, ys, "-",
                color=_GATE_EDGE_COLOR,
                linewidth=1.5,
                alpha=0.7,
                zorder=20,
            )
            self._polygon_marker_lines.append(line2)

            # Closing preview line (last vertex → first vertex, dashed)
            close_line, = self._ax.plot(
                [xs[-1], xs[0]], [ys[-1], ys[0]], "--",
                color=_GATE_EDGE_COLOR,
                linewidth=1.0,
                alpha=0.5,
                zorder=20,
            )
            self._polygon_marker_lines.append(close_line)

        # ── Publish partial polygon for Group Preview ──────────────────
        if len(self._polygon_vertices) >= 2:
            from ...analysis.gating import PolygonGate
            from ...analysis.event_bus import Event, EventType
            
            # Map vertices back to data space for the preview gate
            raw_verts = [self._coordinate_mapper.untransform_point(v[0], v[1]) 
                         for v in self._polygon_vertices]
            temp_gate = PolygonGate(
                self._x_param, self._y_param,
                vertices=raw_verts
            )
            self._state.event_bus.publish(Event(
                EventType.GATE_PREVIEW,
                data={"gate": temp_gate, "sample_id": getattr(self, '_sample_id', None)},
                source="flow_canvas"
            ))

        self.draw_idle()

        # Update instruction with vertex count
        n_pts = len(self._polygon_vertices)
        hint = f"{n_pts} point{'s' if n_pts != 1 else ''} — double-click to close"
        if n_pts < 3:
            hint = f"{n_pts} point{'s' if n_pts != 1 else ''} — need at least 3"
        self._update_instruction(hint)

        self.draw_idle()

    def _clear_polygon_progress(self) -> None:
        """Remove polygon progress markers."""
        for artist in self._polygon_marker_lines:
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        self._polygon_marker_lines.clear()
        if self._closing_line is not None:
            try:
                self._closing_line.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
            self._closing_line = None

    def _cancel_drawing(self) -> None:
        """Cancel any in-progress drawing operation."""
        self._is_drawing = False
        self._drag_start = None
        self._polygon_vertices.clear()
        self._clear_rubber_band()
        self._clear_polygon_progress()
        self._hide_instruction()

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
        self._ax.clear()
        self._ax.set_facecolor(_PLOT_BG)
        self._ax.text(
            0.5, 0.5,
            "Load FCS data to visualize",
            transform=self._ax.transAxes,
            ha="center", va="center",
            fontsize=12,
            color=Colors.FG_DISABLED,
            alpha=0.6,
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        self.draw()

    def _show_error(self, msg: str) -> None:
        """Display an error message on the canvas."""
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
        from ...analysis.event_bus import Event, EventType
        if self._state and self._state.event_bus:
            self._state.event_bus.publish(Event(
                EventType.GATE_PREVIEW,
                data={"gate": None},
                source="flow_canvas"
            ))
