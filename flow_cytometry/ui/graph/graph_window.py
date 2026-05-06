"""Graph window — interactive 2-D scatter / histogram display.

Equivalent to a standard software Graph Window.  Each GraphWindow displays one
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

from biopro.sdk.utils.logging import get_logger
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
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
from biopro.sdk.core.events import CentralEventBus
from ...analysis import events
from ...analysis.fcs_io import get_channel_marker_label
from ...analysis.transforms import TransformType
from ...analysis.scaling import AxisScale, detect_logicle_top, estimate_logicle_params,calculate_auto_range
from ...analysis.gating import Gate, GateNode
from ..widgets.styled_combo import FlowComboBox
from .flow_canvas import FlowCanvas, DisplayMode, GateDrawingMode
from .transform_dialog import TransformDialog
from .render_window import RenderWindow

logger = get_logger(__name__, "flow_cytometry")

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
    navigation_requested = pyqtSignal(str)  # "next_sample", "prev_sample", "parent_gate"

    def __init__(
        self,
        state: FlowState,
        sample_id: str,
        node_id: Optional[str] = None,
        controller: Optional[GateController] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._sample_id = sample_id
        self._node_id = node_id
        self._controller = controller or self._resolve_controller()
        
        self._x_scale = AxisScale(TransformType.LINEAR)
        self._y_scale = AxisScale(TransformType.LINEAR)

        # Debounce timer: 100 ms after the last axis change before re-rendering.
        # Prevents 5-10 redundant full redraws when the user scrolls through the combo.
        self._axis_debounce = QTimer(self)
        self._axis_debounce.setSingleShot(True)
        self._axis_debounce.setInterval(100)
        self._axis_debounce.timeout.connect(self._do_axis_render)

        # Store references to modeless render windows to prevent GC
        self._render_windows: list[RenderWindow] = []

        self._setup_ui()
        self._setup_events()
        logger.info(f"GraphWindow initialized for sample {sample_id}, node {node_id}")

        # Size watcher: some layouts are lazy on macOS, especially in QTabWidget.
        # We poll for a few seconds until we get a non-zero size.
        self._size_watcher = QTimer(self)
        self._size_watcher.timeout.connect(self._check_size_and_render)
        self._size_watcher.start(250)
        self._size_attempts = 0

    def _check_size_and_render(self) -> None:
        self._size_attempts += 1
        if self.width() > 0 and self.height() > 0:
            logger.info(f"GraphWindow size watcher: Found size {self.width()}x{self.height()} at attempt {self._size_attempts}")
            self._size_watcher.stop()
            self._render_initial()
        elif self._size_attempts > 20: # 5 seconds
            logger.warning("GraphWindow size watcher: Timed out waiting for non-zero size")
            self._size_watcher.stop()

    def _setup_events(self) -> None:
        """Subscribe to relevant state events."""
        CentralEventBus.subscribe(events.GATE_RENAMED, self._on_gate_renamed)

    def _on_gate_renamed(self, data: dict) -> None:
        """Handle incoming gate rename events."""
        # Refresh if it's our sample and node
        if data.get("sample_id") == self._sample_id:
            # We update the breadcrumb even if it's a parent gate that was renamed
            self._update_breadcrumb()

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

    def _resolve_controller(self) -> Optional[GateController]:
        """Try to find the controller in parents."""
        curr = self.parent()
        while curr:
            if hasattr(curr, "_gate_controller"):
                return curr._gate_controller
            curr = curr.parent()
        return None

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Navigation & Breadcrumb bar ───────────────────────────────
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        
        # Prev / Next sample arrows
        self._btn_prev = QPushButton("◀ Prev Sample")
        self._btn_next = QPushButton("Next Sample ▶")
        for btn in (self._btn_prev, self._btn_next):
            btn.setFixedHeight(24)
            self._style_transform_btn(btn)  # reuse the flat/accent style
            nav_layout.addWidget(btn)
            
        self._btn_prev.clicked.connect(lambda: self.navigation_requested.emit("prev_sample"))
        self._btn_next.clicked.connect(lambda: self.navigation_requested.emit("next_sample"))
        
        nav_layout.addSpacing(16)
        
        # Up to parent button
        self._btn_parent = QPushButton("↑ Parent Gate")
        self._btn_parent.setFixedHeight(24)
        self._style_transform_btn(self._btn_parent)
        self._btn_parent.setVisible(self._node_id is not None)  # Only if we are in a gate
        self._btn_parent.clicked.connect(lambda: self.navigation_requested.emit("parent_gate"))
        nav_layout.addWidget(self._btn_parent)

        self._breadcrumb = QLabel()
        self._breadcrumb.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: {Colors.BG_DARK}; padding: 4px 8px;"
            f" border-radius: 4px;"
        )
        self._update_breadcrumb()
        nav_layout.addWidget(self._breadcrumb)
        nav_layout.addStretch()
        
        layout.addLayout(nav_layout)

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

        # ── Render spinner ────────────────────────────────────────────
        self._render_spinner = QLabel("⟳ Rendering…")
        self._render_spinner.setStyleSheet(
            f"color: #58a6ff; font-size: 11px; font-weight: 600;"
            f" background: transparent; padding: 0 6px;"
        )
        self._render_spinner.setVisible(False)
        axis_row.addWidget(self._render_spinner)
        
        # ── Render Settings Button ──
        axis_row.addSpacing(16)
        self._btn_settings = QPushButton("⚙ Settings")
        self._btn_settings.setFixedHeight(24)
        self._btn_settings.setToolTip("Customize rendering parameters")
        self._style_transform_btn(self._btn_settings)
        self._btn_settings.clicked.connect(self._open_render_settings_dialog)
        axis_row.addWidget(self._btn_settings)

        axis_row.addStretch()
        layout.addLayout(axis_row)

        # ── Flow Canvas (the actual matplotlib plot) ──────────────────
        self._canvas = FlowCanvas(self._state, self._controller, self)
        self._canvas.setMinimumSize(400, 400)
        layout.addWidget(self._canvas, stretch=1)
        logger.info(f"GraphWindow._setup_ui: Canvas added to layout, canvas_size={self._canvas.width()}x{self._canvas.height()}")
        self._canvas.show()

        # Wire canvas signals
        self._canvas.gate_created.connect(self._on_gate_created)
        self._canvas.gate_selected.connect(self._on_gate_selected)
        self._canvas.render_requested.connect(self._on_render_full_quality)

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

            # Determine Smart Defaults - Default to globally active parameters
            default_x = self._state.active_x_param if hasattr(self._state, 'active_x_param') else "FSC-A"
            default_y = self._state.active_y_param if hasattr(self._state, 'active_y_param') else "SSC-A"

            # Check sample's memory (traverse up gate hierarchy)
            node_id_to_check = self._node_id
            found_memory = False
            
            while True:
                key = node_id_to_check or "root"
                if key in sample.last_viewed_axes:
                    mem = sample.last_viewed_axes[key]
                    if "x_param" in mem and "y_param" in mem:
                        default_x = mem["x_param"]
                        default_y = mem["y_param"]
                        found_memory = True
                        break
                
                if not node_id_to_check:
                    break
                    
                node = sample.gate_tree.find_node_by_id(node_id_to_check)
                if node and node.parent and not node.parent.is_root:
                    node_id_to_check = node.parent.node_id
                elif node and node.parent and node.parent.is_root:
                    node_id_to_check = None
                else:
                    break

            if not found_memory and self._node_id:
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
            logger.warning(f"GraphWindow._render_initial: Sample {self._sample_id} not found or has no FCS data")
            return
    
        sample_events = sample.fcs_data.events
        if sample_events is None:
            logger.warning(f"GraphWindow._render_initial: Sample {self._sample_id} has no events")
            return
    
        # Use PopulationService to get the actual subset (respects negations, etc)
        gated_events = self._state.population_service.get_gated_events(self._sample_id, self._node_id)
        if gated_events is None:
            logger.warning(f"GraphWindow._render_initial: PopulationService returned None for node {self._node_id}")
            return
        
        logger.info(f"GraphWindow._render_initial: Gated events size = {len(gated_events)}")
    
        # Guard against empty gate result
        if len(gated_events) == 0:
            self._canvas.set_data(gated_events)
            return
    
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()

        fcs = sample.fcs_data
        x_label = get_channel_marker_label(fcs, x_ch)
        y_label = get_channel_marker_label(fcs, y_ch)

        # Clone scales so we don't corrupt the global channel_scales store
        x_scale_active = self._x_scale.copy()
        y_scale_active = self._y_scale.copy()

        # Detect logicle T, W, and A from the *gated* events to dynamically open up the 
        # linear region for highly negative compensated data. 
        # (Note: Changed check from LINEAR to BIEXPONENTIAL)
        if x_scale_active.transform_type == TransformType.BIEXPONENTIAL and x_ch in gated_events.columns:
            if x_scale_active.min_val is None:
                x_scale_active.logicle_t = detect_logicle_top(gated_events[x_ch].values)
                
                # ── INJECT ESTIMATOR HERE ──
                w_val, a_val = estimate_logicle_params(gated_events[x_ch].values, t=x_scale_active.logicle_t)
                x_scale_active.logicle_w = w_val
                x_scale_active.logicle_a = a_val

        if y_scale_active.transform_type == TransformType.BIEXPONENTIAL and y_ch in gated_events.columns:
            if y_scale_active.min_val is None:
                y_scale_active.logicle_t = detect_logicle_top(gated_events[y_ch].values)
                
                # ── INJECT ESTIMATOR HERE ──
                w_val, a_val = estimate_logicle_params(gated_events[y_ch].values, t=y_scale_active.logicle_t)
                y_scale_active.logicle_w = w_val
                y_scale_active.logicle_a = a_val

        # ── AUTO-RANGE (first-time only) ──────────────────────────────────
        # Only compute min/max when the channel has never been ranged before
        # (min_val is None). If the user has manually set limits, or a previous
        # render already established them, we preserve those values entirely.
        # This is the single gate that prevents the view from jumping whenever
        # the user switches channels, enters a gate, or changes transform type.
        if x_ch in gated_events.columns and x_scale_active.min_val is None:
            vmin, vmax = calculate_auto_range(
                sample.fcs_data.events[x_ch].values,   # full sample, not gated subset
                x_scale_active.transform_type,
                outlier_percentile=x_scale_active.outlier_percentile
            )
            x_scale_active.min_val, x_scale_active.max_val = float(vmin), float(vmax)

        if y_ch in gated_events.columns and y_scale_active.min_val is None:
            vmin, vmax = calculate_auto_range(
                sample.fcs_data.events[y_ch].values,   # full sample, not gated subset
                y_scale_active.transform_type,
                outlier_percentile=y_scale_active.outlier_percentile
            )
            y_scale_active.min_val, y_scale_active.max_val = float(vmin), float(vmax)
    
        # ── PERSIST THE ESTIMATED SCALES ──
        # This ensures the global state (and thus the Group Preview) 
        # uses the same "Optimized" parameters as this window.
        self._x_scale = x_scale_active.copy()
        self._y_scale = y_scale_active.copy()
        if hasattr(self._state, 'axis_manager'):
            self._state.axis_manager.set_scale(x_ch, self._x_scale.copy(), sample_id=self._sample_id, notify=False)
            self._state.axis_manager.set_scale(y_ch, self._y_scale.copy(), sample_id=self._sample_id, notify=False)

        self._canvas.begin_update()
        self._canvas.set_sample_id(self._sample_id)
        self._canvas.set_axes(x_ch, y_ch, x_label, y_label)
        self._canvas.set_scales(x_scale_active, y_scale_active)
        self._canvas.end_update()       # single redraw with correct axes+scales
        self._canvas.set_data(gated_events)   # final redraw with gated data

        # Notify the system (and Group Preview) that the scale has been finalized
        CentralEventBus.publish(events.AXIS_RANGE_CHANGED, {
            "sample_id": self._sample_id,
            "x_param": x_ch, "y_param": y_ch,
            "x_scale": self._x_scale, "y_scale": self._y_scale
        })

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
        """Handle axis dropdown changes — debounced to avoid redundant renders."""
        # Update internal scale objects immediately so they match the selection,
        # even if the actual render is delayed by the debounce timer.
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        
        self._state.active_x_param = x_ch
        self._state.active_y_param = y_ch
        
        from ...analysis._utils import TransformTypeResolver
        
        # Sync X scale
        if hasattr(self._state, 'axis_manager'):
            current_x_transform = self._x_scale.transform_type if hasattr(self, '_x_scale') else None
            current_y_transform = self._y_scale.transform_type if hasattr(self, '_y_scale') else None
            
            self._x_scale = self._state.axis_manager.get_scale(
                x_ch, self._sample_id, default_transform=current_x_transform
            ).copy()
            self._y_scale = self._state.axis_manager.get_scale(
                y_ch, self._sample_id, default_transform=current_y_transform
            ).copy()
        
        # Save to memory
        sample = self._state.experiment.samples.get(self._sample_id)
        if sample:
            key = self._node_id or "root"
            sample.last_viewed_axes[key] = {
                "x_param": x_ch,
                "y_param": y_ch
            }

        # Show spinner immediately so the user knows a change was registered
        self._render_spinner.setVisible(True)
        # Restart the debounce timer; actual render fires after 100ms of quiet
        self._axis_debounce.start()

    def _do_axis_render(self) -> None:
        """Perform the actual render after axis debounce fires."""
        self._render_initial()
        self._render_spinner.setVisible(False)
        self.axis_changed.emit()
        
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        
        # Publish to event bus for Group Preview sync
        CentralEventBus.publish(events.AXIS_PARAMS_CHANGED, {
            "sample_id": self._sample_id,
            "x_param": x_ch,
            "y_param": y_ch
        })

    def _on_mode_changed(self, index: int) -> None:
        """Handle display mode changes."""
        mode = self._display_combo.currentData()
        if mode:
            self._canvas.set_display_mode(mode)
            # Update global state and notify subscribers (e.g. thumbnails)
            self._state.active_plot_type = mode.value
            CentralEventBus.publish(events.DISPLAY_MODE_CHANGED, {"mode": mode.value})

    def _open_render_settings_dialog(self) -> None:
        """Open the popup dialog to customize density rendering."""
        from .render_settings_dialog import RenderSettingsDialog
        dlg = RenderSettingsDialog(self._state, self)
        dlg.settings_applied.connect(self._on_render_settings_applied)
        dlg.show()

    def _on_render_settings_applied(self, new_config) -> None:
        """Apply new settings and re-render."""
        self._state.view.render_config = new_config
        self._canvas.redraw()

    def _on_gate_created(self, gate: Gate) -> None:
        """Handle gate_created from canvas — forward to controller."""
        self.gate_drawn.emit(gate, self._sample_id, self._node_id)

    def _on_gate_selected(self, gate_id: Optional[str]) -> None:
        """Handle gate selection on the canvas."""
        self.gate_selection_changed.emit(gate_id)

    def _on_render_full_quality(self) -> None:
        """Launch the high-quality render window."""
        # Clean up closed windows from the reference list
        self._render_windows = [w for w in self._render_windows if w.isVisible()]

        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        mode = self._display_combo.currentData()

        # Get current gate overlays
        gates = self._canvas._active_gates
        nodes = self._canvas._gate_nodes

        win = RenderWindow(
            state=self._state,
            sample_id=self._sample_id,
            node_id=self._node_id,
            x_param=x_ch,
            y_param=y_ch,
            display_mode=mode,
            x_scale=self._x_scale,
            y_scale=self._y_scale,
            gates=gates,
            gate_nodes=nodes,
            parent=self.window(), # Keep it associated with the main window
        )
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        win.show()
        self._render_windows.append(win)

    def _open_transform_dialog(self) -> None:
        """Open the unified Transform & Scaling dialog."""
        x_name = self._x_combo.currentText()
        y_name = self._y_combo.currentText()
        x_ch = self._x_combo.currentData() or x_name
        y_ch = self._y_combo.currentData() or y_name

        def do_auto_range_x(outlier_p: float = 0.1) -> tuple[float, float]:
            return self._calculate_auto_range("x", outlier_p)
            
        def do_auto_range_y(outlier_p: float = 0.1) -> tuple[float, float]:
            return self._calculate_auto_range("y", outlier_p)

        dlg = TransformDialog(
            x_name=x_name,
            y_name=y_name,
            x_scale=self._x_scale,
            y_scale=self._y_scale,
            auto_range_x_callback=do_auto_range_x,
            auto_range_y_callback=do_auto_range_y,
            parent=self,
        )
        
        # When values change, update local, redraw, and implicitly sync globally
        def on_change(axis_id: str, new_scale: AxisScale):
            old_scale = self._x_scale if axis_id == "x" else self._y_scale
            transform_changed = old_scale.transform_type != new_scale.transform_type
            
            if axis_id == "x":
                self._x_scale = new_scale.copy()
                if hasattr(self._state, 'axis_manager'):
                    self._state.axis_manager.set_scale(x_ch, self._x_scale.copy(), sample_id=self._sample_id)
                self.axis_scale_sync_requested.emit(x_ch, self._x_scale)
                self._notify_axis_change()
            else:
                self._y_scale = new_scale.copy()
                if hasattr(self._state, 'axis_manager'):
                    self._state.axis_manager.set_scale(y_ch, self._y_scale.copy(), sample_id=self._sample_id)
                self.axis_scale_sync_requested.emit(y_ch, self._y_scale)
                self._notify_axis_change()
            
            if transform_changed:
                self._canvas._on_transform_changed()
                CentralEventBus.publish(events.TRANSFORM_CHANGED, {
                    "sample_id": self._sample_id,
                    "axis": axis_id,
                    "channel": x_ch if axis_id == "x" else y_ch,
                    "old_type": old_scale.transform_type,
                    "new_type": new_scale.transform_type,
                })
                
            self._render_initial()
            
        dlg.scale_changed.connect(on_change)
        
        dlg.show()

    def _notify_axis_change(self) -> None:
        """Publish the current axis state to the global event bus."""
        x_ch = self._x_combo.currentData() or self._x_combo.currentText()
        y_ch = self._y_combo.currentData() or self._y_combo.currentText()
        CentralEventBus.publish(events.AXIS_RANGE_CHANGED, {
            "sample_id": self._sample_id,
            "x_param": x_ch, "y_param": y_ch,
            "x_scale": self._x_scale, "y_scale": self._y_scale
        })
        
    def _calculate_auto_range(self, axis: str, outlier_p: Optional[float] = None) -> tuple[float, float]:
        """Compute the robust min/max for the given axis, using gated data.
        
        Args:
            axis: "x" or "y".
            outlier_p: Percentile to clip at each end. If None, uses the
                       value stored in the current axis scale.
        """
        sample = self._state.experiment.samples.get(self._sample_id)
        if not sample or not sample.fcs_data or sample.fcs_data.events is None:
            return (0.0, 1.0)
    
        events = sample.fcs_data.events
        # Apply gate hierarchy so range reflects what is actually displayed
        if self._node_id:
            node = sample.gate_tree.find_node_by_id(self._node_id)
            if node:
                events = node.apply_hierarchy(events)
    
        col = self._x_combo.currentData() if axis == "x" else self._y_combo.currentData()
        if not col or col not in events:
            return (0.0, 1.0)
    
        scale = self._x_scale if axis == "x" else self._y_scale
        pct = outlier_p if outlier_p is not None else scale.outlier_percentile
        return calculate_auto_range(events[col].values, scale.transform_type, outlier_percentile=pct)

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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        logger.info(f"GraphWindow resized: {self.width()}x{self.height()}")

    def _style_transform_btn(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.FG_PRIMARY}; border: 1px solid {Colors.BORDER};"
            f" border-radius: 3px; font-size: 11px; font-weight: 600; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_DARK};"
            f" color: {Colors.ACCENT_PRIMARY}; }}"
        )
