"""Group Preview Panel — shows low-res renders of all samples in a group.

Fix log v3:
- Replaced scatter+rankdata density render with imshow on the 2-D histogram.
  rankdata on a subsample inflates sparse points to high percentiles, making
  the thumbnail look much denser/more colourful than the main plot.
  imshow renders the actual bin counts (sqrt-normalised), which is
  sample-count-independent and visually matches the main canvas.
- Outlier dots (bins with ≤1 count) are shown as small blue scatter on top.
- Subsample limit raised from 100k → 200k to improve histogram accuracy
  for large files like this 319k-event sample.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
)
from PyQt6.QtGui import QImage, QPixmap

from biopro.ui.theme import Colors, Fonts
from biopro.core.task_scheduler import task_scheduler
from biopro.sdk.core.managed_task import FunctionalTask

from ...analysis.state import FlowState
from ...analysis.experiment import Sample
from ...analysis.event_bus import Event, EventType
from ...analysis.transforms import apply_transform, TransformType
from ...analysis.scaling import AxisScale, calculate_auto_range
from ...analysis.constants import (
    PREVIEW_LIMIT_DEFAULT,
    PREVIEW_THUMBNAIL_SIZE,
    PREVIEW_GATE_EDGE_COLOR,
    PREVIEW_GATE_LINEWIDTH,
    PREVIEW_BG_COLOR,
)

logger = logging.getLogger(__name__)

# Standard limit for high-fidelity previews (FlowJo equivalent)
_THUMB_LIMIT = 25_000

_SCATTER_PREFIXES = ("FSC", "SSC", "Time", "time")


def _is_scatter(ch: str) -> bool:
    return any(ch.startswith(p) for p in _SCATTER_PREFIXES)


def _resolve_scale(state: FlowState, channel: str) -> AxisScale:
    """Return the best AxisScale for channel, matching GraphWindow logic."""
    if channel in state.channel_scales:
        return state.channel_scales[channel].copy()

    # Fallback heuristic when the channel has not been opened in a GraphWindow yet.
    is_fluor = any(t in channel.upper() for t in ["-A", "-H", "-W", "FITC", "PE", "PI", "APC", "CY", "BLUE", "VIOLET", "RED"])
    is_scatter = any(channel.upper().startswith(p) for p in ["FSC", "SSC"])

    if is_fluor and not is_scatter:
        sc = AxisScale(TransformType.BIEXPONENTIAL)
        sc.logicle_t = 262144.0
        sc.logicle_w = 0.5  # FlowJo standard
        sc.logicle_m = 4.5
        sc.logicle_a = 0.0  # Only set > 0 when data has negatives
        return sc

    return AxisScale(TransformType.LINEAR)


def _xform_params(scale: AxisScale) -> dict:
    if scale.transform_type == TransformType.LOG:
        return {"decades": 4.5, "min_value": 1.0}
    if scale.transform_type == TransformType.BIEXPONENTIAL:
        return {
            "top": scale.logicle_t,
            "width": scale.logicle_w,
            "positive": scale.logicle_m,
            "negative": scale.logicle_a,
        }
    return {}


def _display_range(scale: AxisScale, full_raw: np.ndarray) -> tuple[float, float]:
    """Compute display-space axis limits matching the main FlowCanvas."""
    params = _xform_params(scale)

    # Priority 1: stored limits from GraphWindow (most accurate — always wins)
    if scale.min_val is not None and scale.max_val is not None:
        lo = float(apply_transform(np.array([scale.min_val]), scale.transform_type, **params)[0])
        hi = float(apply_transform(np.array([scale.max_val]), scale.transform_type, **params)[0])
        return lo, hi

    valid = full_raw[np.isfinite(full_raw)]
    if len(valid) == 0:
        return 0.0, 262144.0

    if scale.transform_type == TransformType.LINEAR:
        # Match FlowCanvas: floor at 0 for scatter channels; ceiling at instrument max.
        # Using p99.9 vs 262144 ceiling ensures FSC/SSC always fills the axis.
        floor = min(0.0, float(np.percentile(valid, 0.05)))
        ceiling = max(float(np.percentile(valid, 99.9)), 262144.0)
        return floor, ceiling

    # LOG / BIEX — adaptive based on data (no hardcoded 262144 ceiling)
    raw_lo, raw_hi = calculate_auto_range(valid, scale.transform_type)
    lo = float(apply_transform(np.array([raw_lo]), scale.transform_type, **params)[0])
    hi = float(apply_transform(np.array([raw_hi]), scale.transform_type, **params)[0])
    return lo, hi


# ── Off-thread render ─────────────────────────────────────────────────────────

def render_preview_to_buffer(
    sample_id: str,
    events: pd.DataFrame,
    x_param: str,
    y_param: str,
    x_scale: AxisScale,
    y_scale: AxisScale,
    gate,
    limit: int,
    width_px: int,
    height_px: int,
    plot_type: str = "pseudocolor",
) -> bytes:
    """Render a density thumbnail to an RGBA byte buffer (off the main thread)."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    # ── 1. Validate ───────────────────────────────────────────────────
    if x_param not in events.columns or y_param not in events.columns:
        blank = np.ones((height_px, width_px, 4), dtype=np.uint8) * 255
        return blank.tobytes()

    x_params = _xform_params(x_scale)
    y_params = _xform_params(y_scale)

    # ── 2. Axis limits — from FULL dataset before any subsampling ─────
    x_min, x_max = _display_range(x_scale, events[x_param].values)
    y_min, y_max = _display_range(y_scale, events[y_param].values)
    if x_max <= x_min: x_max = x_min + 1.0
    if y_max <= y_min: y_max = y_min + 1.0

    # ── 3. Subsample ──────────────────────────────────────────────────
    n = len(events)
    if n > limit:
        rng = np.random.default_rng(42)
        df = events.iloc[rng.choice(n, limit, replace=False)]
    else:
        df = events

    x_raw = df[x_param].values.astype(np.float64)
    y_raw = df[y_param].values.astype(np.float64)

    # ── 4. Transform & clip ───────────────────────────────────────────
    x_disp = np.clip(
        apply_transform(x_raw, x_scale.transform_type, **x_params),
        x_min, x_max,
    )
    y_disp = np.clip(
        apply_transform(y_raw, y_scale.transform_type, **y_params),
        y_min, y_max,
    )

    # ── 5. Figure ─────────────────────────────────────────────────────
    dpi = 100
    fig = Figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax = fig.add_subplot(111)
    ax.set_facecolor(PREVIEW_BG_COLOR)
    fig.set_facecolor(PREVIEW_BG_COLOR)

    # ── 6. Rendering Core ─────────────────────────────────────────────
    try:
        from fast_histogram import histogram2d
        from scipy.ndimage import gaussian_filter
        from scipy.stats import rankdata

        if plot_type == "histogram":
            # 1D Histogram render
            n_bins = min(128, max(32, int(np.sqrt(len(x_disp)) * 1.5)))
            counts, edges = np.histogram(x_disp, bins=n_bins, range=(x_min, x_max))
            
            # Draw as filled area (FlowJo style)
            ax.fill_between(edges[:-1], 0, counts, color="#58a6ff", alpha=0.7)
            ax.set_ylim(0, counts.max() * 1.1 if len(counts) > 0 else 1.0)
            
        else:
            # 2D Pseudocolor render
            # 1. Density Estimation (Matches GraphWindow "Optimized" mode)
            n_points = len(x_disp)
            N_BINS = int(min(256, max(64, np.sqrt(n_points) * 1.2)))
            sigma = max(0.8, 1.5 * (N_BINS / 256))
            
            H = histogram2d(
                y_disp, x_disp,
                bins=(N_BINS, N_BINS),
                range=[[y_min, y_max], [x_min, x_max]],
            )
            H_smooth = gaussian_filter(H.astype(np.float64), sigma=sigma)

            # 2. Per-event density lookup
            x_span = max(x_max - x_min, 1e-12)
            y_span = max(y_max - y_min, 1e-12)
            x_idx = np.clip(((x_disp - x_min) / x_span * N_BINS).astype(int), 0, N_BINS - 1)
            y_idx = np.clip(((y_disp - y_min) / y_span * N_BINS).astype(int), 0, N_BINS - 1)
            densities = H_smooth[y_idx, x_idx]

            # 3. Equal Probability (Percentile) Normalization
            if len(densities) > 0:
                c_plot = rankdata(densities) / len(densities)
                # Z-sort: dense events render on top
                sort_idx = np.argsort(c_plot)
                ax.scatter(
                    x_disp[sort_idx], y_disp[sort_idx],
                    c=c_plot[sort_idx],
                    cmap="turbo",
                    vmin=0.0, vmax=1.0,
                    s=0.8, # Slightly larger for thumbnails
                    alpha=0.6,
                    edgecolors="none",
                    rasterized=True
                )
            else:
                # Fallback for empty/low data
                ax.scatter(x_disp, y_disp, s=1.0, c="#58a6ff", alpha=0.5, edgecolors="none")

        # Option C: Linear region shading (visual parity)
        if x_scale.transform_type == TransformType.BIEXPONENTIAL:
            r_lo, r_hi = apply_transform(np.array([-1000.0, 1000.0]), TransformType.BIEXPONENTIAL, **x_params)
            ax.axvspan(r_lo, r_hi, color="#000000", alpha=0.04, zorder=0, linewidth=0)
        if y_scale.transform_type == TransformType.BIEXPONENTIAL and plot_type != "histogram":
            r_lo, r_hi = apply_transform(np.array([-1000.0, 1000.0]), TransformType.BIEXPONENTIAL, **y_params)
            ax.axhspan(r_lo, r_hi, color="#000000", alpha=0.04, zorder=0, linewidth=0)

    except Exception as exc:
        logger.warning("Thumbnail render failed (%s): %s", sample_id, exc, exc_info=True)
        ax.scatter(x_disp, y_disp, s=1.0, c="#58a6ff", alpha=0.5, edgecolors="none")

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    # ── 7. Gate overlay ───────────────────────────────────────────────
    if gate is not None:
        try:
            _draw_gate(ax, gate, x_scale, y_scale, x_params, y_params)
        except Exception as exc:
            logger.debug("Gate overlay failed: %s", exc)

    # ── 7. Rendering Logic ────────────────────────────────────────────
    # THUMBNAILS STAY IN LINEAR DISPLAY SPACE (Decades/Normalized)
    # This is more robust for small renders and ensures density matching.
    ax.set_xscale("linear")
    ax.set_yscale("linear")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    buf = bytes(canvas.buffer_rgba())
    plt.close(fig)
    return buf


def _draw_gate(ax, gate, x_scale, y_scale, x_params, y_params):
    """Draw a gate boundary on thumbnail axes."""
    import matplotlib.patches as mpatches
    from ...analysis.gating import (
        RectangleGate, PolygonGate, EllipseGate, RangeGate, QuadrantGate,
    )

    lw = PREVIEW_GATE_LINEWIDTH
    ec = PREVIEW_GATE_EDGE_COLOR

    def tx(v):
        return float(apply_transform(np.array([v], dtype=np.float64),
                                     x_scale.transform_type, **x_params)[0])
    def ty(v):
        return float(apply_transform(np.array([v], dtype=np.float64),
                                     y_scale.transform_type, **y_params)[0])

    if isinstance(gate, RectangleGate):
        x0 = tx(gate.x_min) if np.isfinite(gate.x_min) else ax.get_xlim()[0]
        x1 = tx(gate.x_max) if np.isfinite(gate.x_max) else ax.get_xlim()[1]
        y0 = ty(gate.y_min) if np.isfinite(gate.y_min) else ax.get_ylim()[0]
        y1 = ty(gate.y_max) if np.isfinite(gate.y_max) else ax.get_ylim()[1]
        ax.add_patch(mpatches.Rectangle(
            (x0, y0), x1-x0, y1-y0, fill=False, edgecolor=ec, linewidth=lw))

    elif isinstance(gate, PolygonGate) and len(gate.vertices) >= 2:
        # Drawing a polygon in progress or finished
        vx = apply_transform(np.array([v[0] for v in gate.vertices], dtype=np.float64),
                             x_scale.transform_type, **x_params)
        vy = apply_transform(np.array([v[1] for v in gate.vertices], dtype=np.float64),
                             y_scale.transform_type, **y_params)
        
        # If only 2 points, draw a line instead of a closed polygon
        is_closed = len(gate.vertices) >= 3
        ax.add_patch(mpatches.Polygon(
            list(zip(vx, vy)), closed=is_closed, fill=False, 
            edgecolor=ec, linewidth=lw, alpha=0.8, zorder=30))

    elif isinstance(gate, EllipseGate):
        theta = np.linspace(0, 2*np.pi, 64)
        ca, sa = np.cos(np.radians(gate.angle)), np.sin(np.radians(gate.angle))
        xe = gate.center[0] + gate.width*np.cos(theta)*ca - gate.height*np.sin(theta)*sa
        ye = gate.center[1] + gate.width*np.cos(theta)*sa + gate.height*np.sin(theta)*ca
        vx = apply_transform(xe, x_scale.transform_type, **x_params)
        vy = apply_transform(ye, y_scale.transform_type, **y_params)
        ax.add_patch(mpatches.Polygon(
            list(zip(vx, vy)), closed=True, fill=False, edgecolor=ec, linewidth=lw))

    elif isinstance(gate, RangeGate):
        xlim = ax.get_xlim(); ylim = ax.get_ylim()
        x0 = tx(gate.low)  if np.isfinite(gate.low)  else xlim[0]
        x1 = tx(gate.high) if np.isfinite(gate.high) else xlim[1]
        ax.add_patch(mpatches.Rectangle(
            (x0, ylim[0]), x1-x0, ylim[1]-ylim[0],
            fill=False, edgecolor=ec, linewidth=lw, linestyle="--"))

    elif isinstance(gate, QuadrantGate):
        ax.axvline(tx(gate.x_mid), color=ec, linewidth=lw, linestyle="--", alpha=0.8)
        ax.axhline(ty(gate.y_mid), color=ec, linewidth=lw, linestyle="--", alpha=0.8)


# ── UI Components ─────────────────────────────────────────────────────────────

class PreviewThumbnail(QFrame):
    """Single-sample preview thumbnail."""

    def __init__(self, state: FlowState, sample_id: str, parent_panel: "GroupPreviewPanel"):
        super().__init__(parent_panel)
        self._state = state
        self._sample_id = sample_id
        self._last_params = None
        # No longer need a _pending dict — we connect directly to each worker

        self.setFixedSize(PREVIEW_THUMBNAIL_SIZE[0], PREVIEW_THUMBNAIL_SIZE[1] + 20)
        self.setStyleSheet(
            f"border: 1px solid {Colors.BORDER};"
            f" background: {Colors.BG_DARK}; border-radius: 4px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet("border: none; background: #FFFFFF;")
        layout.addWidget(self._img, stretch=1)

        s = self._state.experiment.samples.get(sample_id)
        self._lbl = QLabel(s.display_name if s else "Unknown")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: 10px; border: none;")
        layout.addWidget(self._lbl)

    def refresh(self, x_param: str, y_param: str, node_id: Optional[str]) -> None:
        plot_type = getattr(self._state, "active_plot_type", "pseudocolor")
        self._submit(x_param, y_param, node_id, _THUMB_LIMIT, plot_type=plot_type)

    def preview_gate(self, x_param: str, y_param: str, node_id: Optional[str], gate) -> None:
        """Lightweight update for live gate drawing feedback."""
        plot_type = getattr(self._state, "active_plot_type", "pseudocolor")
        # Use a slightly lower limit for real-time previews to maintain responsiveness
        self._submit(x_param, y_param, node_id, 20000, gate, plot_type=plot_type)

    def _submit(self, x_param, y_param, node_id, limit, temp_gate=None, plot_type="pseudocolor"):
        x_scale = _resolve_scale(self._state, x_param)
        y_scale = _resolve_scale(self._state, y_param)
        gate = temp_gate
        gate_id = gate.gate_id if gate else None

        # Cache invalidation check — must include scale info and plot type!
        scale_key = (x_scale.min_val, x_scale.max_val, y_scale.min_val, y_scale.max_val)
        current_params = (x_param, y_param, node_id, limit, gate_id, scale_key, plot_type)
        if current_params == self._last_params:
            return
        self._last_params = current_params

        sample = self._state.experiment.samples.get(self._sample_id)
        if not sample or not sample.has_data:
            return

        events = sample.fcs_data.events
        
        if node_id:
            node = sample.gate_tree.find_node_by_id(node_id)
            if node:
                if gate is not None:
                    # ── Drawing Mode ──────────────────────────────────
                    # Show the population the user is currently gating ON (the parent events)
                    # and overlay the temporary gate.
                    events = node.apply_hierarchy(events)
                else:
                    # ── Viewing Mode ──────────────────────────────────
                    # Show the gated population itself. Do NOT show the gate outline
                    # as it is redundant when we are "inside" the gate.
                    events = node.apply_hierarchy(events)
                    gate = None

        x_scale = _resolve_scale(self._state, x_param)
        y_scale = _resolve_scale(self._state, y_param)

        _ev, _xp, _yp = events, x_param, y_param
        _xs, _ys, _g, _lim = x_scale, y_scale, gate, limit
        _w, _h = PREVIEW_THUMBNAIL_SIZE

        def task_func():
            return render_preview_to_buffer(
                self._sample_id, _ev, _xp, _yp, _xs, _ys, _g, _lim, _w, _h, plot_type)

        worker = task_scheduler.submit(
            FunctionalTask(task_func, name=f"Thumb-{self._sample_id[:8]}"), None
        )
        # Connect directly to this specific worker — avoids the global bus ID mismatch
        worker.finished.connect(self._on_render_done)

    def _on_render_done(self, results: dict) -> None:
        """Called on the UI thread when the off-thread render completes."""
        buf = results.get("result") if isinstance(results, dict) else results
        if not isinstance(buf, (bytes, bytearray)) or not buf:
            logger.warning("Thumbnail for %s: empty buffer returned", self._sample_id)
            return
        w, h = PREVIEW_THUMBNAIL_SIZE
        qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
        self._img.setPixmap(QPixmap.fromImage(qimg))

    # Legacy hook kept for GroupPreviewPanel compatibility
    def on_task_finished(self, task_id: str, results) -> None:
        pass


class GroupPreviewPanel(QWidget):
    """Panel showing previews for all samples in a group."""

    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        self._current_sample_id: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._thumbnails: Dict[str, PreviewThumbnail] = {}
        self._setup_ui()
        task_scheduler.task_finished.connect(self._on_task_finished)
        self._setup_events()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        hdr = QLabel("👥 Group Preview")
        hdr.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: 10px; font-weight: 700;")
        layout.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background: {Colors.BG_DARKEST};")

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)
        self.setMinimumHeight(200)

    def _setup_events(self) -> None:
        eb = self._state.event_bus
        eb.subscribe(EventType.AXIS_PARAMS_CHANGED, self._on_axis_changed)
        eb.subscribe(EventType.AXIS_RANGE_CHANGED,  self._on_axis_changed)
        eb.subscribe(EventType.TRANSFORM_CHANGED,    self._on_axis_changed)
        eb.subscribe(EventType.GATE_CREATED,        self._on_gate_event)
        eb.subscribe(EventType.GATE_MODIFIED,       self._on_gate_event)
        eb.subscribe(EventType.GATE_DELETED,        self._on_gate_event)
        eb.subscribe(EventType.GATE_PREVIEW,        self._on_gate_preview)
        eb.subscribe(EventType.DISPLAY_MODE_CHANGED, self._on_axis_changed)

    def update_context(self, sample_id: str, node_id: Optional[str]) -> None:
        if sample_id == self._current_sample_id and node_id == self._current_node_id:
            # If the sample is the same, just refresh the existing thumbnails
            # with the latest state (axes/gates/scales)
            self._refresh_all()
            return
        self._current_sample_id = sample_id
        self._current_node_id = node_id
        self._rebuild()

    def _rebuild(self) -> None:
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w: w.deleteLater()
        self._thumbnails.clear()

        if not self._current_sample_id:
            return

        sample = self._state.experiment.samples.get(self._current_sample_id)
        if not sample:
            return

        peers: list[Sample] = []
        if sample.group_ids:
            gid = list(sample.group_ids)[0]
            peers = [s for s in self._state.experiment.samples.values()
                     if gid in s.group_ids and s.sample_id != self._current_sample_id]
        if not peers:
            peers = [s for s in self._state.experiment.samples.values()
                     if s.sample_id != self._current_sample_id]

        x_param = getattr(self._state, "active_x_param", "FSC-A")
        y_param = getattr(self._state, "active_y_param", "SSC-A")

        cols = 2
        for i, s in enumerate(peers):
            thumb = PreviewThumbnail(self._state, s.sample_id, self)
            self._thumbnails[s.sample_id] = thumb
            self._grid.addWidget(thumb, i // cols, i % cols)
            thumb.refresh(x_param, y_param, self._current_node_id)

    def _on_task_finished(self, task_id: str, results) -> None:
        # Legacy — no longer needed since thumbnails connect directly to their workers
        pass

    def _on_axis_changed(self, event: Event) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        """Refresh data for all existing thumbnails without rebuilding the grid."""
        x = getattr(self._state, "active_x_param", "FSC-A")
        y = getattr(self._state, "active_y_param", "SSC-A")
        for thumb in self._thumbnails.values():
            thumb.refresh(x, y, self._current_node_id)

    def _on_gate_event(self, event: Event) -> None:
        x = getattr(self._state, "active_x_param", "FSC-A")
        y = getattr(self._state, "active_y_param", "SSC-A")
        for thumb in self._thumbnails.values():
            thumb.refresh(x, y, self._current_node_id)

    def _on_gate_preview(self, event: Event) -> None:
        """Handle live gate drawing feedback."""
        gate = event.data.get("gate")
        # Do NOT return early if gate is None — we need to clear the preview!
            
        # Only show preview if the axes match what we are currently looking at
        x = getattr(self._state, "active_x_param", "FSC-A")
        y = getattr(self._state, "active_y_param", "SSC-A")
        
        # If we have a gate, check if its channels match
        if gate:
            if hasattr(gate, "channels") and gate.channels:
                if x not in gate.channels or y not in gate.channels:
                    return
            elif hasattr(gate, "x_param") and gate.x_param:
                if x != gate.x_param or (gate.y_param and y != gate.y_param):
                    return
                
        for thumb in self._thumbnails.values():
            thumb.preview_gate(x, y, self._current_node_id, gate)
