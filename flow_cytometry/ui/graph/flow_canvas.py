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
from ...analysis.scaling import AxisScale
from ...analysis.gating import (
    Gate,
    RectangleGate,
    PolygonGate,
    EllipseGate,
    QuadrantGate,
    RangeGate,
    GateNode,
)

from ...analysis.scaling import AxisScale, calculate_auto_range # ADD THIS IMPORT

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
_GATE_EDGE_COLOR = "#00E5FF"
_GATE_FILL_COLOR = "#00E5FF"
_GATE_ALPHA = 0.12
_GATE_EDGE_ALPHA = 0.9
_GATE_LINEWIDTH = 1.5
_GATE_SELECTED_EDGE = "#FFAB40"
_GATE_SELECTED_ALPHA = 0.20
_RUBBER_BAND_COLOR = "#FFFFFF"
_RUBBER_BAND_ALPHA = 0.5

# Different colors for gates at different depths
_GATE_PALETTE = [
    "#00E5FF",   # Cyan
    "#76FF03",   # Light green
    "#FF4081",   # Pink
    "#FFD740",   # Amber
    "#E040FB",   # Purple
    "#64FFDA",   # Teal
    "#FF6E40",   # Deep orange
    "#448AFF",   # Blue
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

    def __init__(self, parent=None) -> None:
        # Apply BioPro theme
        import matplotlib
        for key, val in _MPL_STYLE.items():
            matplotlib.rcParams[key] = val

        self._fig = Figure(figsize=(6, 5), dpi=100)
        self._fig.set_facecolor(_PLOT_BG)
        super().__init__(self._fig)

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

        # ── Cached background bitmap ──────────────────────────────────
        # The expensive scatter data is rendered once and cached.
        # Gate overlays are drawn on top without re-rendering scatter.
        self._bg_cache = None  # matplotlib bbox cache
        self._gate_artists: list = []  # artists drawn on gate layer

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

        # ── Gate editing ──────────────────────────────────────────────
        self._editing_gate_id: Optional[str] = None
        self._edit_handle_idx: Optional[int] = None
        self._edit_handles: list = []  # matplotlib artists for handles

        # Mouse event connections
        self._cid_press = self.mpl_connect("button_press_event", self._on_press)
        self._cid_release = self.mpl_connect("button_release_event", self._on_release)
        self._cid_motion = self.mpl_connect("motion_notify_event", self._on_motion)
        self._cid_dblclick = self.mpl_connect("button_press_event", self._on_dblclick)

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

    def _transform_x(self, x: np.ndarray) -> np.ndarray:
        x_kwargs = {
            "top": self._x_scale.logicle_t, "width": self._x_scale.logicle_w,
            "positive": self._x_scale.logicle_m, "negative": self._x_scale.logicle_a,
        } if self._x_scale.transform_type == TransformType.BIEXPONENTIAL else {}
        return apply_transform(x, self._x_scale.transform_type, **x_kwargs)

    def _transform_y(self, y: np.ndarray) -> np.ndarray:
        y_kwargs = {
            "top": self._y_scale.logicle_t, "width": self._y_scale.logicle_w,
            "positive": self._y_scale.logicle_m, "negative": self._y_scale.logicle_a,
        } if self._y_scale.transform_type == TransformType.BIEXPONENTIAL else {}
        return apply_transform(y, self._y_scale.transform_type, **y_kwargs)

    def _inverse_transform_x(self, x: np.ndarray) -> np.ndarray:
        x_kwargs = {
            "top": self._x_scale.logicle_t, "width": self._x_scale.logicle_w,
            "positive": self._x_scale.logicle_m, "negative": self._x_scale.logicle_a,
        } if self._x_scale.transform_type == TransformType.BIEXPONENTIAL else {}
        return invert_transform(x, self._x_scale.transform_type, **x_kwargs)

    def _inverse_transform_y(self, y: np.ndarray) -> np.ndarray:
        y_kwargs = {
            "top": self._y_scale.logicle_t, "width": self._y_scale.logicle_w,
            "positive": self._y_scale.logicle_m, "negative": self._y_scale.logicle_a,
        } if self._y_scale.transform_type == TransformType.BIEXPONENTIAL else {}
        return invert_transform(y, self._y_scale.transform_type, **y_kwargs)

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
                alpha=0.08,
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
                alpha=0.08,
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
                alpha=0.06,
                linestyle=":",
                zorder=20,
            )
            self._ax.add_patch(self._rubber_band_patch)

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
            return

        if self._drawing_mode == GateDrawingMode.RECTANGLE:
            self._finalize_rectangle(x0, y0, x1, y1)
        elif self._drawing_mode == GateDrawingMode.ELLIPSE:
            self._finalize_ellipse(x0, y0, x1, y1)
        elif self._drawing_mode == GateDrawingMode.RANGE:
            self._finalize_range(x0, x1)

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

    # ── Gate finalization ─────────────────────────────────────────────

    def _finalize_rectangle(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """Create a RectangleGate from the drawn rectangle."""
        rx0, rx1 = self._inverse_transform_x(np.array([min(x0, x1), max(x0, x1)]))
        ry0, ry1 = self._inverse_transform_y(np.array([min(y0, y1), max(y0, y1)]))
        gate = RectangleGate(
            x_param=self._x_param,
            y_param=self._y_param,
            x_min=rx0,
            x_max=rx1,
            y_min=ry0,
            y_max=ry1,
        )
        logger.info("Rectangle gate created: %s", gate)
        self.gate_created.emit(gate)

    def _finalize_polygon(self) -> None:
        """Create a PolygonGate from the accumulated vertices."""
        pts_x = self._inverse_transform_x(np.array([v[0] for v in self._polygon_vertices]))
        pts_y = self._inverse_transform_y(np.array([v[1] for v in self._polygon_vertices]))
        raw_vertices = list(zip(pts_x, pts_y))
        
        display_vertices = list(self._polygon_vertices)
        
        gate = PolygonGate(
            x_param=self._x_param,
            y_param=self._y_param,
            vertices=display_vertices,
            x_scale=self._x_scale.copy(), 
            y_scale=self._y_scale.copy(),
        )
        self._polygon_vertices.clear()
        self._clear_polygon_progress()
        logger.info("Polygon gate created: %s (%d vertices)", gate, len(gate.vertices))
        self.gate_created.emit(gate)

    def _finalize_ellipse(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        """Create an EllipseGate from the drawn bounding box."""
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        w = abs(x1 - x0) / 2
        h = abs(y1 - y0) / 2
        
        rcx = self._inverse_transform_x(np.array([cx]))[0]
        rcy = self._inverse_transform_y(np.array([cy]))[0]
        rx_w = abs(self._inverse_transform_x(np.array([cx + w]))[0] - rcx)
        ry_h = abs(self._inverse_transform_y(np.array([cy + h]))[0] - rcy)

        gate = EllipseGate(
            x_param=self._x_param,
            y_param=self._y_param,
            center=(rcx, rcy),
            width=rx_w,
            height=ry_h,
            angle=0.0,
        )
        logger.info("Ellipse gate created: %s", gate)
        self.gate_created.emit(gate)

    def _finalize_quadrant(self, x: float, y: float) -> None:
        """Create a QuadrantGate at the clicked position."""
        rx = self._inverse_transform_x(np.array([x]))[0]
        ry = self._inverse_transform_y(np.array([y]))[0]
        gate = QuadrantGate(
            x_param=self._x_param,
            y_param=self._y_param,
            x_mid=rx,
            y_mid=ry,
        )
        logger.info("Quadrant gate created: %s at (%.2f, %.2f)", gate, x, y)
        self.gate_created.emit(gate)

    def _finalize_range(self, x0: float, x1: float) -> None:
        """Create a RangeGate from the drawn range."""
        rx0, rx1 = self._inverse_transform_x(np.array([min(x0, x1), max(x0, x1)]))
        gate = RangeGate(
            x_param=self._x_param,
            low=rx0,
            high=rx1,
        )
        logger.info("Range gate created: %s", gate)
        self.gate_created.emit(gate)

    # ── Gate selection ────────────────────────────────────────────────

    def _try_select_gate(self, x: float, y: float) -> None:
        """Check if a click hits any gate overlay and select it."""
        hit_id = None

        for gate_id, info in self._gate_patches.items():
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
                alpha=0.4,
                zorder=20,
            )
            self._polygon_marker_lines.append(close_line)

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
