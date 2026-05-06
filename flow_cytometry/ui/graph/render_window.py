"""Render window — high-quality, full-dataset rendering for FACS plots.

Provides a modeless window to view and export FACS plots at maximum resolution
without the subsampling used in the main workspace.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QToolBar,
    QFileDialog,
    QApplication,
    QMessageBox,
)

from biopro.ui.theme import Colors, Fonts
from .flow_canvas import FlowCanvas, DisplayMode
from ...analysis.state import FlowState
from ...analysis.scaling import AxisScale
from ...analysis.gating import Gate, GateNode

logger = get_logger(__name__, "flow_cytometry")


class RenderWindow(QMainWindow):
    """Deep-render window for high-quality FACS plots."""

    def __init__(
        self,
        state: FlowState,
        sample_id: str,
        node_id: Optional[str] = None,
        x_param: str = "FSC-A",
        y_param: str = "SSC-A",
        display_mode: DisplayMode = DisplayMode.PSEUDOCOLOR,
        x_scale: Optional[AxisScale] = None,
        y_scale: Optional[AxisScale] = None,
        gates: Optional[list[Gate]] = None,
        gate_nodes: Optional[list[GateNode]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Full Render — {sample_id}")
        self.setMinimumSize(800, 700)
        
        # Make it modeless by default, but ensure it stays on top if desired
        # self.setWindowFlags(Qt.WindowType.Window) 

        self._state = state
        self._sample_id = sample_id
        self._node_id = node_id

        self._setup_ui()
        
        # Configure canvas for high quality
        self._canvas._max_events = None           # No subsampling
        self._canvas._quality_multiplier = 2.0    # Double grid resolution
        
        # Apply parameters
        sample = self._state.experiment.samples.get(sample_id)
        if sample and sample.fcs_data is not None:
            events = sample.fcs_data.events
            if node_id:
                node = sample.gate_tree.find_node_by_id(node_id)
                if node:
                    events = node.apply_hierarchy(events)
            
            self._canvas.begin_update()
            self._canvas.set_axes(x_param, y_param)
            if x_scale and y_scale:
                self._canvas.set_scales(x_scale, y_scale)
            self._canvas.set_display_mode(display_mode)
            if gates:
                self._canvas.set_gates(gates, gate_nodes)
            self._canvas.end_update()
            self._canvas.set_data(events)

    def _setup_ui(self) -> None:
        # Main widget and layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self._toolbar = QToolBar("Render Actions")
        self._toolbar.setIconSize(QSize(18, 18))
        self._toolbar.setMovable(False)
        self._toolbar.setStyleSheet(
            f"QToolBar {{ background: {Colors.BG_DARK}; border-bottom: 1px solid {Colors.BORDER};"
            f" padding: 4px; spacing: 8px; }}"
            f"QToolButton {{ color: {Colors.FG_PRIMARY}; font-size: 11px; font-weight: 600;"
            f" border-radius: 4px; padding: 4px 8px; }}"
            f"QToolButton:hover {{ background: {Colors.BG_MEDIUM}; color: {Colors.ACCENT_PRIMARY}; }}"
        )
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)

        # Actions
        copy_act = QAction("📋 Copy to Clipboard", self)
        copy_act.triggered.connect(self._on_copy)
        self._toolbar.addAction(copy_act)

        save_act = QAction("💾 Save High-Res Image...", self)
        save_act.triggered.connect(self._on_save)
        self._toolbar.addAction(save_act)

        self._toolbar.addSeparator()
        
        close_act = QAction("✕ Close", self)
        close_act.triggered.connect(self.close)
        self._toolbar.addAction(close_act)

        # Canvas
        self._canvas = FlowCanvas(self)
        layout.addWidget(self._canvas, stretch=1)

    def _on_copy(self) -> None:
        """Copy the current canvas to clipboard as a high-res pixmap."""
        try:
            # Grab the canvas as a pixmap
            pixmap = self._canvas.grab()
            QApplication.clipboard().setPixmap(pixmap)
            # Show a brief status bar message or tray hint if possible
            self.statusBar().showMessage("Copied to clipboard", 2000)
        except Exception as e:
            logger.error("Clipboard copy failed: %s", e)
            QMessageBox.warning(self, "Copy Failed", f"Could not copy to clipboard: {e}")

    def _on_save(self) -> None:
        """Save the high-quality render to disk."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save High-Res Render", "",
            "PNG Image (*.png);;PDF Document (*.pdf);;SVG Vector (*.svg)"
        )
        if not path:
            return

        try:
            # Use matplotlib savefig for high-quality export
            # If PNG, use 300 DPI for publication quality
            dpi = 300 if path.endswith(".png") else None
            self._canvas._fig.savefig(path, dpi=dpi, bbox_inches='tight')
            QMessageBox.information(self, "Success", f"Plot saved to:\n{path}")
        except Exception as e:
            logger.error("Save failed: %s", e)
            QMessageBox.critical(self, "Save Error", f"Failed to save image:\n{e}")
