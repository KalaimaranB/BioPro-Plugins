"""Group Preview Panel — shows low-res renders of all samples in a group.

Uses progressive rendering to provide instant feedback followed by higher
fidelity results. Leverages the BioPro SDK TaskScheduler for parallel execution.
"""

from __future__ import annotations

import logging
import io
from typing import Optional, List, Dict

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QFrame,
    QGridLayout,
)
from PyQt6.QtGui import QImage, QPixmap

from biopro.ui.theme import Colors, Fonts
from biopro.core.task_scheduler import task_scheduler
from biopro.sdk.core.managed_task import FunctionalTask

from ...analysis.state import FlowState
from ...analysis.experiment import Sample
from ...analysis.event_bus import Event, EventType
from ...analysis.transforms import apply_transform
from ...analysis.constants import (
    PREVIEW_LIMIT_DEFAULT,
    PREVIEW_THUMBNAIL_SIZE,
    PREVIEW_GATE_EDGE_COLOR,
    PREVIEW_GATE_LINEWIDTH,
    PREVIEW_BG_COLOR
)

logger = logging.getLogger(__name__)

# ── Background Rendering Logic ────────────────────────────────────────

def render_preview_to_buffer(
    sample_id: str,
    events: pd.DataFrame,
    x_param: str,
    y_param: str,
    x_scale: object,
    y_scale: object,
    gate: Optional[object],
    limit: int,
    width_px: int,
    height_px: int
) -> bytes:
    """Perform off-thread Matplotlib rendering to an RGB buffer."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    
    # 1. Subsample
    n = len(events)
    if n > limit:
        idx = np.random.choice(n, limit, replace=False)
        df = events.iloc[idx]
    else:
        df = events
        
    x_data = df[x_param].values
    y_data = df[y_param].values
    
    # 2. Apply transforms
    # Get the specific parameters for each scale type to ensure thumbnails match main plot
    def _get_params(scale):
        from ...analysis.transforms import TransformType
        if scale.transform_type == TransformType.LOG:
            return {"decades": 4.5, "min_value": 1.0}
        elif scale.transform_type == TransformType.BIEXPONENTIAL:
            return {
                "top": scale.logicle_t,
                "width": scale.logicle_w,
                "positive": scale.logicle_m,
                "negative": scale.logicle_a
            }
        return {}

    x_disp = apply_transform(x_data, x_scale.transform_type, **_get_params(x_scale))
    y_disp = apply_transform(y_data, y_scale.transform_type, **_get_params(y_scale))
    
    # 3. Handle coordinate boundaries (Use scale limits if available)
    if hasattr(x_scale, 'min_val') and x_scale.min_val is not None:
        x_min = apply_transform(np.array([x_scale.min_val]), x_scale.transform_type, **_get_params(x_scale))[0]
        x_max = apply_transform(np.array([x_scale.max_val]), x_scale.transform_type, **_get_params(x_scale))[0]
    else:
        x_min, x_max = np.min(x_disp), np.max(x_disp)
        
    if hasattr(y_scale, 'min_val') and y_scale.min_val is not None:
        y_min = apply_transform(np.array([y_scale.min_val]), y_scale.transform_type, **_get_params(y_scale))[0]
        y_max = apply_transform(np.array([y_scale.max_val]), y_scale.transform_type, **_get_params(y_scale))[0]
    else:
        y_min, y_max = np.min(y_disp), np.max(y_disp)
        
    # Avoid division by zero/flat ranges
    if x_max == x_min: x_max += 1
    if y_max == y_min: y_max += 1

    # 4. Create Figure (small)
    dpi = 100
    fig = Figure(figsize=(width_px/dpi, height_px/dpi), dpi=dpi)
    ax = fig.add_subplot(111)
    ax.set_facecolor(PREVIEW_BG_COLOR)
    fig.set_facecolor(PREVIEW_BG_COLOR)
    
    # ── Pseudocolor (Density) Render ──
    try:
        from fast_histogram import histogram2d
        h = histogram2d(
            y_disp, x_disp,
            bins=(160, 160), # Match thumbnail pixels for maximum sharpness
            range=[[y_min, y_max], [x_min, x_max]]
        )
        
        # Identify outliers (points in low-density bins)
        # Map points back to bin indices
        x_bins = ((x_disp - x_min) / (x_max - x_min) * 159).astype(int)
        y_bins = ((y_disp - y_min) / (y_max - y_min) * 159).astype(int)
        x_bins = np.clip(x_bins, 0, 159)
        y_bins = np.clip(y_bins, 0, 159)
        
        counts_per_point = h[y_bins, x_bins]
        outlier_mask = counts_per_point <= 1
        
        # Sharper smoothing for clearer population edges
        from scipy.ndimage import gaussian_filter
        h_smooth = gaussian_filter(h, sigma=0.7) 
        
        # Sqrt scaling is better for linear data (FSC/SSC) than Log
        h_smooth = np.sqrt(h_smooth)
        
        # Minimal threshold just to hide background noise
        threshold = np.max(h_smooth) * 0.02
        h_masked = np.ma.masked_where(h_smooth < threshold, h_smooth)
        
        # 1. Plot Density Map
        ax.imshow(
            h_masked, origin='lower', aspect='auto', 
            extent=[x_min, x_max, y_min, y_max],
            cmap='jet', interpolation='bicubic'
        )
        
        # 2. Plot Outliers as individual dots
        if np.any(outlier_mask):
            # Subsample outliers to keep it clean
            o_x = x_disp[outlier_mask]
            o_y = y_disp[outlier_mask]
            if len(o_x) > 5000:
                idx = np.random.choice(len(o_x), 5000, replace=False)
                o_x, o_y = o_x[idx], o_y[idx]
                
            ax.scatter(
                o_x, o_y,
                s=1,
                c="#58a6ff", # Light blue for outliers (matches main plot)
                alpha=0.5,
                edgecolors="none"
            )
    except Exception as e:
        logger.debug(f"Pseudocolor failed, falling back to scatter: {e}")
        ax.scatter(x_disp, y_disp, s=2, c="#58a6ff", alpha=0.6, edgecolors="none")
    
    # Ensure axes limits are set to show the synchronized data
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.axis('off')
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    
    # 4. Draw Gate Boundary in Black
    if gate:
        try:
            # We use a simplified boundary drawer for thumbnails
            # Gate must have a 'render_on_axes' or similar helper
            # or we just draw its vertices if it's a polygon/rectangle.
            from ..graph.flow_services import GateOverlayRenderer, CoordinateMapper
            mapper = CoordinateMapper(x_scale, y_scale)
            # Use black color as requested
            from matplotlib.patches import Polygon, Rectangle, Ellipse
            
            # Simple manual drawing for performance in threads
            if hasattr(gate, 'vertices'): # Polygon
                v = mapper.transform_points(gate.vertices)
                patch = Polygon(v, fill=False, edgecolor="black", linewidth=PREVIEW_GATE_LINEWIDTH)
                ax.add_patch(patch)
            elif hasattr(gate, 'x_min'): # Rectangle
                x0 = mapper.transform_x(gate.x_min)
                y0 = mapper.transform_y(gate.y_min)
                w = mapper.transform_x(gate.x_max) - x0
                h = mapper.transform_y(gate.y_max) - y0
                patch = Rectangle((x0, y0), w, h, fill=False, edgecolor="black", linewidth=PREVIEW_GATE_LINEWIDTH)
                ax.add_patch(patch)
        except Exception as e:
            logger.debug(f"Could not draw gate on thumbnail: {e}")

    ax.axis('off')
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    
    # 5. Render to buffer
    # 5. Render to buffer
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    
    # Crucial: Convert memoryview to bytes to ensure the data persists
    # after the figure is garbage collected.
    buf = bytes(canvas.buffer_rgba())
    
    # Cleanup to avoid memory build-up in threads
    plt.close(fig)
    
    return buf

# ── UI Components ─────────────────────────────────────────────────────

class PreviewThumbnail(QFrame):
    """Small widget displaying a single sample preview."""
    
    def __init__(self, state: FlowState, sample_id: str, parent_panel: GroupPreviewPanel):
        super().__init__(parent_panel)
        self._state = state
        self._sample_id = sample_id
        self._parent_panel = parent_panel
        self._current_task_id: Optional[str] = None
        self._is_high_res = False
        self._last_was_preview = False
        self._last_request_params = (None, None, None, 0)
        
        self.setFixedSize(PREVIEW_THUMBNAIL_SIZE[0], PREVIEW_THUMBNAIL_SIZE[1] + 20)
        self.setStyleSheet(f"border: 1px solid {Colors.BORDER}; background: {Colors.BG_DARK}; border-radius: 4px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("border: none; background: #FFFFFF;")
        layout.addWidget(self._img_label, stretch=1)
        
        self._name_label = QLabel(self._get_sample_name())
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: 10px; border: none;")
        layout.addWidget(self._name_label)

    def _get_sample_name(self) -> str:
        sample = self._state.experiment.samples.get(self._sample_id)
        return sample.display_name if sample else "Unknown"

    def preview_gate(self, x_param: str, y_param: str, gate: object):
        """Update preview with a temporary gate (low-res only)."""
        self._is_high_res = False
        self._last_was_preview = True
        self._last_request_params = (x_param, y_param, None, PREVIEW_LIMIT_DEFAULT)
        self._cancel_current_task()
        # Request render with limit
        self._request_render(x_param, y_param, None, PREVIEW_LIMIT_DEFAULT, temp_gate=gate)

    def refresh(self, x_param: str, y_param: str, node_id: Optional[str]):
        """Trigger a new render pass (starting with low-res)."""
        self._is_high_res = False
        self._last_was_preview = False
        self._last_request_params = (x_param, y_param, node_id, PREVIEW_LIMIT_DEFAULT)
        self._cancel_current_task()
        self._request_render(x_param, y_param, node_id, PREVIEW_LIMIT_DEFAULT)

    def _request_render(self, x_param: str, y_param: str, node_id: Optional[str], limit: int, temp_gate: Optional[object] = None):
        # Throttling: If we are already rendering, and this is a high-frequency preview,
        # skip it to avoid overloading the TaskScheduler.
        if self._current_task_id is not None and temp_gate is not None:
            return

        sample = self._state.experiment.samples.get(self._sample_id)
        if not sample or not sample.has_data:
            return

        events = sample.fcs_data.events
        gate = None
        
        if temp_gate:
            gate = temp_gate
        elif node_id:
            node = sample.gate_tree.find_node_by_id(node_id)
            if node:
                gate = node.gate
                # If we are viewing a gated population, apply parent gates
                if node.parent and not node.parent.is_root:
                    events = node.parent.apply_hierarchy(events)

        # Get scales (X/Y)
        # In a real app, these would come from the active GraphWindow or global store
        x_scale = self._state.channel_scales.get(x_param)
        y_scale = self._state.channel_scales.get(y_param)
        
        if not x_scale or not y_scale:
            from ...analysis.scaling import AxisScale
            from ...analysis.transforms import TransformType
            x_scale = x_scale or AxisScale(TransformType.LINEAR)
            y_scale = y_scale or AxisScale(TransformType.LINEAR)

        # Build task
        def task_func():
            return render_preview_to_buffer(
                self._sample_id, events, x_param, y_param, 
                x_scale, y_scale, gate, limit,
                PREVIEW_THUMBNAIL_SIZE[0], PREVIEW_THUMBNAIL_SIZE[1]
            )

        task = FunctionalTask(task_func, name=f"Thumbnail {self._sample_id}")
        
        # We connect to the global scheduler
        self._current_task_id = task_scheduler.submit(task, None)

    def _on_global_task_finished(self, task_id, results):
        """Handler for the global task_finished signal."""
        if task_id == self._current_task_id:
            # We need to know if this was a preview or not.
            # We'll store that state on the thumbnail itself.
            is_preview = getattr(self, '_last_was_preview', False)
            # We also need to recover the params from our last request
            x, y, node, limit = self._last_request_params
            self._on_render_finished(results, x, y, node, limit, is_preview)

    def _on_render_finished(self, results: Any, x_param: str, y_param: str, node_id: str, last_limit: int, is_preview: bool):
        if not results:
            return
            
        # The TaskScheduler wraps FunctionalTask results in a dict {"result": ...}
        if isinstance(results, dict):
            buffer = results.get("result")
        else:
            buffer = results
            
        if not buffer or not isinstance(buffer, bytes):
            return

        # Convert to QPixmap
        qimg = QImage(buffer, PREVIEW_THUMBNAIL_SIZE[0], PREVIEW_THUMBNAIL_SIZE[1], QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)
        self._img_label.setPixmap(pixmap)
        
        # Single-pass render logic. We removed multi-pass refinement
        # to prevent the 'animation' flicker.
        pass

    def _cancel_current_task(self):
        # BioPro TaskScheduler doesn't have per-task cancellation yet,
        # but we ignore the result by clearing our task_id.
        self._current_task_id = None


class GroupPreviewPanel(QWidget):
    """Panel showing previews for all samples in a group."""
    
    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        self._current_sample_id: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._thumbnails: Dict[str, PreviewThumbnail] = {}
        
        self._setup_ui()
        
        # Connect to task finished once to avoid leaks
        task_scheduler.task_finished.connect(self._on_global_task_finished)
        self._setup_events()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        header = QLabel("👥 Group Preview")
        header.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: 10px; font-weight: 700; text-transform: uppercase;")
        layout.addWidget(header)
        
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        
        self._container = QWidget()
        self._container.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        
        self._container_layout = QGridLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(12)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)
        
        self.setMinimumHeight(200)

    def _setup_events(self):
        self._state.event_bus.subscribe(EventType.AXIS_PARAMS_CHANGED, self._on_axis_changed)
        self._state.event_bus.subscribe(EventType.AXIS_RANGE_CHANGED, self._on_axis_changed)
        self._state.event_bus.subscribe(EventType.GATE_CREATED, self._on_gate_event)
        self._state.event_bus.subscribe(EventType.GATE_MODIFIED, self._on_gate_event)
        self._state.event_bus.subscribe(EventType.GATE_DELETED, self._on_gate_event)
        # Disabling high-frequency GATE_PREVIEW as per user request (no live-draw animation)

    def update_context(self, sample_id: str, node_id: Optional[str]):
        """Update which group we are displaying based on selected sample."""
        if sample_id == self._current_sample_id and node_id == self._current_node_id:
            return
            
        self._current_sample_id = sample_id
        self._current_node_id = node_id
        self._rebuild_previews()

    def _rebuild_previews(self):
        """Find other samples in the same group and create thumbnails."""
        # Clear existing
        while self._container_layout.count():
            child = self._container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._thumbnails.clear()

        if not self._current_sample_id:
            return

        # Find group
        sample = self._state.experiment.samples.get(self._current_sample_id)
        if not sample:
            logger.warning(f"Preview: Sample {self._current_sample_id} not found")
            return
            
        group_samples = []
        if sample.group_ids:
            # Get samples from the first explicit group
            group_id = list(sample.group_ids)[0]
            group_samples = [
                s for s in self._state.experiment.samples.values()
                if group_id in s.group_ids and s.sample_id != self._current_sample_id
            ]
            logger.debug(f"Preview: Found {len(group_samples)} samples in group {group_id}")
        
        # Fallback: If no group found or group is empty, show all other samples
        if not group_samples:
            group_samples = [
                s for s in self._state.experiment.samples.values()
                if s.sample_id != self._current_sample_id
            ]
            logger.debug(f"Preview: Fallback to all samples, found {len(group_samples)}")
        
        # Use active axes from state
        x_param = getattr(self._state, 'active_x_param', "FSC-A")
        y_param = getattr(self._state, 'active_y_param', "SSC-A")

        cols = 2
        for i, sample in enumerate(group_samples):
            thumb = PreviewThumbnail(self._state, sample.sample_id, self)
            self._thumbnails[sample.sample_id] = thumb
            
            row = i // cols
            col = i % cols
            self._container_layout.addWidget(thumb, row, col)
            
            # Initial render
            thumb.refresh(x_param, y_param, self._current_node_id)

    def _on_global_task_finished(self, task_id, results):
        """Delegate task results to all thumbnails."""
        for thumb in self._thumbnails.values():
            thumb._on_global_task_finished(task_id, results)

    def _on_axis_changed(self, event: Event):
        # event.data: {sample_id, x_param, y_param}
        x_param = event.data.get("x_param")
        y_param = event.data.get("y_param")
        
        for thumb in self._thumbnails.values():
            thumb.refresh(x_param, y_param, self._current_node_id)

    def _on_gate_event(self, event: Event):
        # Refresh all thumbnails with current axes
        x_param = getattr(self._state, 'active_x_param', "FSC-A")
        y_param = getattr(self._state, 'active_y_param', "SSC-A")
        
        for thumb in self._thumbnails.values():
            thumb.refresh(x_param, y_param, self._current_node_id)

    def _on_gate_preview(self, event: Event):
        # We no longer respond to live previews to prevent flicker/animation
        pass
