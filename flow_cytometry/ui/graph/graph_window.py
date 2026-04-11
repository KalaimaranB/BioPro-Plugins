"""Graph window — interactive 2-D scatter / histogram display.

Equivalent to FlowJo's Graph Window.  Each GraphWindow displays one
plot of a single population (sample or gated subset) with:
- X/Y axis dropdowns for parameter selection
- Transform buttons (linear / log / biexponential)
- Gate overlay rendering with named, color-coded patches
- Breadcrumb navigation bar showing the gating hierarchy path
- Active gate info and statistics display
- Multiple display modes (dot, pseudocolor, contour, density, histogram)

GraphWindows are managed by :class:`GraphManager` which handles tabbing
and tiling.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.experiment import Sample
from ...analysis.fcs_io import get_channel_marker_label
from ...analysis.transforms import TransformType
from ...analysis.scaling import AxisScale, calculate_auto_range, detect_logicle_top
from ...analysis.gating import Gate, GateNode
from ..widgets.styled_combo import FlowComboBox
from .flow_canvas import FlowCanvas, DisplayMode, GateDrawingMode
from .transform_dialog import TransformDialog
logger = logging.getLogger(__name__)

# Map tool names to drawing modes
_TOOL_MODE_MAP = {
    "select": GateDrawingMode.NONE,
    "rectangle": GateDrawingMode.RECTANGLE,
    "polygon": GateDrawingMode.POLYGON,
    "ellipse": GateDrawingMode.ELLIPSE,
    "quadrant": GateDrawingMode.QUADRANT,
    "range": GateDrawingMode.RANGE,
}


class GraphWindow(QWidget):
    """Interactive flow cytometry plot widget.

    Displays a single bivariate (scatter) or univariate (histogram)
    plot of events.  Gate drawing, axis selection, and display mode
    changes are handled here.

    Signals:
        gate_drawn(Gate, str, str):   Emitted when a gate is drawn.
                                       (gate, sample_id, parent_gate_id)
        gate_selection_changed(str):  Emitted when a gate overlay is clicked.
        axis_changed:                 Emitted when axis selection changes.
    """

    gate_drawn = pyqtSignal(object, str, object)  # Gate, sample_id, parent_node_id
    gate_selection_changed = pyqtSignal(object)    # gate_id or None
    axis_changed = pyqtSignal()
    axis_scale_sync_requested = pyqtSignal(str, object)  # channel_name, AxisScale

    def __init__(
        self,
        state: FlowState,
        sample_id: str,
        node_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._sample_id = sample_id
        self._node_id = node_id
        
        self._x_scale = AxisScale(TransformType.LINEAR)
        self._y_scale = AxisScale(TransformType.LINEAR)
        
        self._setup_ui()

    @property
    def sample_id(self) -> str:
        return self._sample_id

    @property
    def node_id(self) -> Optional[str]:
        return self._node_id

    @property
    def canvas(self) -> FlowCanvas:
        """Expose the canvas for external signal wiring."""
        return self._canvas

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Breadcrumb bar ────────────────────────────────────────────
        self._breadcrumb = QLabel()
        self._breadcrumb.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: {Colors.BG_DARK}; padding: 4px 8px;"
            f" border-radius: 4px;"
        )
        self._update_breadcrumb()
        layout.addWidget(self._breadcrumb)

        # ── Axis selection row ────────────────────────────────────────
        axis_row = QHBoxLayout()
        axis_row.setSpacing(6)

        axis_row.addWidget(self._make_label("X:"))
        self._x_combo = FlowComboBox()
        self._x_combo.setMinimumWidth(140)
        self._x_combo.currentTextChanged.connect(self._on_axis_changed)
        axis_row.addWidget(self._x_combo)

        axis_row.addSpacing(16)
        axis_row.addWidget(self._make_label("Y:"))

        self._y_combo = FlowComboBox()
        self._y_combo.setMinimumWidth(140)
        self._y_combo.currentTextChanged.connect(self._on_axis_changed)
        axis_row.addWidget(self._y_combo)

        # Display mode
        axis_row.addSpacing(16)
        self._display_combo = FlowComboBox()
        for mode in DisplayMode:
            self._display_combo.addItem(mode.value, mode)
        self._display_combo.currentIndexChanged.connect(self._on_mode_changed)
        axis_row.addWidget(self._display_combo)
        
        # ── Unified Transforms Button ──
        axis_row.addSpacing(16)
        self._transform_btn = QPushButton("⚙ Transforms")
        self._transform_btn.setFixedHeight(24)
        self._transform_btn.setToolTip("Open Axis Scaling & Transforms dialog")
        self._style_transform_btn(self._transform_btn)
        self._transform_btn.clicked.connect(self._open_transform_dialog)
        axis_row.addWidget(self._transform_btn)

        axis_row.addStretch()
        layout.addLayout(axis_row)

        # ── Flow Canvas (the actual matplotlib plot) ──────────────────
        self._canvas = FlowCanvas()
        layout.addWidget(self._canvas, stretch=1)

        # Wire canvas signals
        self._canvas.gate_created.connect(self._on_gate_created)
        self._canvas.gate_selected.connect(self._on_gate_selected)

        # ── Gate info bar ─────────────────────────────────────────────
        self._gate_info = QLabel()
        self._gate_info.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: 10px;"
            f" background: {Colors.BG_DARK}; padding: 3px 8px;"
            f" border-radius: 3px;"
        )
        self._gate_info.setVisible(False)
        layout.addWidget(self._gate_info)

        # Populate axis combos and trigger initial scale sync and render
        self._populate_axis_combos()
        self._on_axis_changed()

    def set_drawing_mode(self, tool_name: str) -> None:
        """Set the canvas drawing mode from a tool name.

        Args:
            tool_name: One of "select", "rectangle", "polygon",
                       "ellipse", "quadrant", "range".
        """
        mode = _TOOL_MODE_MAP.get(tool_name, GateDrawingMode.NONE)
        self._canvas.set_drawing_mode(mode)

    def refresh_gates(
        self, gates: list[Gate], gate_nodes: list[GateNode]
    ) -> None:
        """Refresh the gate overlays on this canvas.

        Args:
            gates:      Gates to render.
            gate_nodes: Matching GateNode list for stat labels.
        """
        self._canvas.set_gates(gates, gate_nodes)

    def update_gate_info(self, gate: Optional[Gate], stats: dict) -> None:
        """Update the gate info bar at the bottom of the window.

        Args:
            gate:  The currently selected gate (None to hide).
            stats: Statistics dictionary {count, pct_parent, pct_total}.
        """
        if gate is None:
            self._gate_info.setVisible(False)
            return

        count = stats.get("count", 0)
        pct_parent = stats.get("pct_parent", 0.0)
        pct_total = stats.get("pct_total", 0.0)

        text = (
            f"  ⊳ {stats.get('name', 'Population')}  │  "
            f"{int(count):,} events  │  "
            f"{pct_parent:.1f}% of parent  │  "
            f"{pct_total:.1f}% of total"
        )
        self._gate_info.setText(text)
        self._gate_info.setVisible(True)

    def _populate_axis_combos(self) -> None:
        """Fill axis dropdowns with parameter names from the sample."""
        sample = self._state.experiment.samples.get(self._sample_id)

        # Block signals during population to avoid premature redraws
        self._x_combo.blockSignals(True)
        self._y_combo.blockSignals(True)

        if sample is None or sample.fcs_data is None:
            defaults = ["FSC-A", "SSC-A", "FSC-H", "SSC-H"]
            self._x_combo.addItems(defaults)
            self._y_combo.addItems(defaults)
            self._x_combo.setCurrentText("FSC-A")
            self._y_combo.setCurrentText("SSC-A")
        else:
            fcs = sample.fcs_data
            for ch in fcs.channels:
                label = get_channel_marker_label(fcs, ch)
                self._x_combo.addItem(label, ch)
                self._y_combo.addItem(label, ch)

            # Determine Smart Defaults
            default_x = "FSC-A"
            default_y = "SSC-A"

            if self._node_id:
                node = sample.gate_tree.find_node_by_id(self._node_id)
                if node and node.gate:
                    channels = getattr(node.gate, "channels", [])
                    # If the parent gate was purely scatter, guess they want to see fluorescence now
                    if channels and all("FSC" in ch or "SSC" in ch for ch in channels):
                        fluo_channels = [
                            ch for ch in fcs.channels 
                            if "FSC" not in ch and "SSC" not in ch and "Time" not in ch
                        ]
                        if len(fluo_channels) >= 2:
                            default_x = fluo_channels[0]
                            default_y = fluo_channels[1]

            # Apply defaults
            for i in range(self._x_combo.count()):
                if self._x_combo.itemData(i) == default_x:
                    self._x_combo.setCurrentIndex(i)
                    break
            for i in range(self._y_combo.count()):
                if self._y_combo.itemData(i) == default_y:
                    self._y_combo.setCurrentIndex(i)
                    break

        self._x_combo.blockSignals(False)
        self._y_combo.blockSignals(False)

    def _render_initial(self) -> None:
        """Render the initial plot from the sample's data."""
        sample = self._state.experiment.samples.get(self._sample_id)
        if sample is None or sample.fcs_data is None:
            return

        events = sample.fcs_data.events
        if events is None:
            return

        # If gated, apply the population hierarchy
        is_gated = False
        if self._node_id:
            node = sample.gate_tree.find_node_by_id(self._node_id)
            if node:
                events = node.apply_hierarchy(events)
                is_gated = True

        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()

        fcs = sample.fcs_data
        x_label = get_channel_marker_label(fcs, x_ch)
        y_label = get_channel_marker_label(fcs, y_ch)

        # Do one-time T detection if linear
        if self._x_scale.transform_type == TransformType.LINEAR and x_ch in events.columns:
            self._x_scale.logicle_t = detect_logicle_top(events[x_ch].values)
        if self._y_scale.transform_type == TransformType.LINEAR and y_ch in events.columns:
            self._y_scale.logicle_t = detect_logicle_top(events[y_ch].values)

        # FlowJo Auto-Zoom: If we are viewing a gated subset, tighten the limits
        if is_gated and len(events) > 0:
            import numpy as np
            raw_events = sample.fcs_data.events
            if x_ch in events.columns:
                p1, p99 = np.percentile(events[x_ch], [1, 99])
                margin = (p99 - p1) * 0.1
                if margin > 0:
                    x_min = max(float(raw_events[x_ch].min()), float(p1 - margin))
                    x_max = min(float(raw_events[x_ch].max()), float(p99 + margin))
                    self._x_scale.min_val = x_min
                    self._x_scale.max_val = x_max
            if y_ch in events.columns:
                p1, p99 = np.percentile(events[y_ch], [1, 99])
                margin = (p99 - p1) * 0.1
                if margin > 0:
                    y_min = max(float(raw_events[y_ch].min()), float(p1 - margin))
                    y_max = min(float(raw_events[y_ch].max()), float(p99 + margin))
                    self._y_scale.min_val = y_min
                    self._y_scale.max_val = y_max

        self._canvas.set_axes(x_ch, y_ch, x_label, y_label)
        self._canvas.set_scales(self._x_scale, self._y_scale)
        self._canvas.set_data(events)

    def apply_axis_scale(self, channel_name: str, scale: AxisScale) -> None:
        """Apply an external scale setting if this graph uses that channel."""
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        
        needs_redraw = False
        if x_ch == channel_name:
            self._x_scale = scale.copy()
            needs_redraw = True
        if y_ch == channel_name:
            self._y_scale = scale.copy()
            needs_redraw = True
            
        if needs_redraw:
            self._canvas.set_scales(self._x_scale, self._y_scale)

    def _on_axis_changed(self) -> None:
        """Handle axis dropdown changes — sync global channel scales and redraw."""
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        if x_ch in self._state.channel_scales:
            self._x_scale = self._state.channel_scales[x_ch].copy()
            
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        if y_ch in self._state.channel_scales:
            self._y_scale = self._state.channel_scales[y_ch].copy()
            
        self._render_initial()
        self.axis_changed.emit()

    def _on_mode_changed(self, index: int) -> None:
        """Handle display mode changes."""
        mode = self._display_combo.currentData()
        if mode:
            self._canvas.set_display_mode(mode)

    def _on_gate_created(self, gate: Gate) -> None:
        """Handle gate_created from canvas — forward to controller."""
        self.gate_drawn.emit(gate, self._sample_id, self._node_id)

    def _on_gate_selected(self, gate_id: Optional[str]) -> None:
        """Handle gate selection on the canvas."""
        self.gate_selection_changed.emit(gate_id)

    def _open_transform_dialog(self) -> None:
        """Open the unified Transform & Scaling dialog."""
        x_name = self._x_combo.currentText()
        y_name = self._y_combo.currentText()

        def do_auto_range_x() -> tuple[float, float]:
            return self._calculate_auto_range("x")
            
        def do_auto_range_y() -> tuple[float, float]:
            return self._calculate_auto_range("y")

        dlg = TransformDialog(
            x_name=x_name,
            y_name=y_name,
            x_scale=self._x_scale,
            y_scale=self._y_scale,
            auto_range_x_callback=do_auto_range_x,
            auto_range_y_callback=do_auto_range_y,
            parent=self,
        )
        
        # When values change, update local and redraw
        def on_change(axis_id: str, new_scale: AxisScale):
            if axis_id == "x":
                self._x_scale = new_scale.copy()
            else:
                self._y_scale = new_scale.copy()
            self._canvas.set_scales(self._x_scale, self._y_scale)
            
        dlg.scale_changed.connect(on_change)
        
        # Auto-apply to all other samples
        def on_apply_all(axis_id: str, scale_val: AxisScale):
            ch_name = self._x_combo.currentText() if axis_id == "x" else self._y_combo.currentText()
            self.axis_scale_sync_requested.emit(ch_name, scale_val)
            
        dlg.apply_to_all_requested.connect(on_apply_all)
        
        dlg.show()
        
    def _calculate_auto_range(self, axis: str) -> tuple[float, float]:
        """Compute the robust min/max for the given axis data."""
        sample = self._state.experiment.samples.get(self._sample_id)
        if not sample or not sample.fcs_data or sample.fcs_data.events is None:
            return (0.0, 1.0)
            
        events = sample.fcs_data.events
        if self._node_id:
            node = sample.gate_tree.find_node_by_id(self._node_id)
            if node:
                events = node.apply_hierarchy(events)
                
        col = self._x_combo.currentData() if axis == "x" else self._y_combo.currentData()
        if not col or col not in events:
            return (0.0, 1.0)
            
        scale = self._x_scale if axis == "x" else self._y_scale
        return calculate_auto_range(events[col].values, scale.transform_type)

    def _update_breadcrumb(self) -> None:
        """Update the breadcrumb navigation bar showing gating path."""
        sample = self._state.experiment.samples.get(self._sample_id)
        if sample is None:
            self._breadcrumb.setText("⊘ No sample selected")
            return

        parts = [f"🧪 {sample.display_name}"]

        if self._node_id:
            # Build full path from root to this population node
            node = sample.gate_tree.find_node_by_id(self._node_id)
            if node:
                path: list[str] = []
                current = node
                while current and not current.is_root:
                    path.append(current.name)
                    current = current.parent
                path.reverse()
                for p in path:
                    parts.append(f"⊳ {p}")

        self._breadcrumb.setText("  ›  ".join(parts))

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" font-weight: 600; background: transparent;"
        )
        return lbl

    # QComboBox styling unified in FlowComboBox

    def _style_transform_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.FG_PRIMARY}; border: 1px solid {Colors.BORDER};"
            f" border-radius: 3px; font-size: 11px; font-weight: 600; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_DARK};"
            f" color: {Colors.ACCENT_PRIMARY}; }}"
        )
