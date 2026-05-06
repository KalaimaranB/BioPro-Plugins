"""Render Settings Dialog — tabbed, per-mode scientist-friendly settings.

Each tab hosts an independent panel class from ``render_panels/``.
This dialog is purely a coordinator — all business logic lives in the panels.
"""

from __future__ import annotations
from biopro.sdk.utils.logging import get_logger

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTabWidget, QScrollArea, QWidget
)
from PyQt6.QtCore import pyqtSignal
from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.config import RenderConfig
from .flow_canvas import DisplayMode
from .render_panels import (
    PseudocolorSettingsPanel,
    DotPlotSettingsPanel,
    HistogramSettingsPanel,
    ContourSettingsPanel,
    DensitySettingsPanel,
)

logger = get_logger(__name__, "flow_cytometry")

# Map DisplayMode → tab index (must match addTab order below)
_MODE_TAB = {
    DisplayMode.PSEUDOCOLOR: 0,
    DisplayMode.DOT_PLOT:    1,
    DisplayMode.HISTOGRAM:   2,
    DisplayMode.CONTOUR:     3,
    DisplayMode.DENSITY:     4,
}


def _scrollable(panel: QWidget) -> QScrollArea:
    """Wrap a panel in a scroll area so it works on small screens."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.Shape.NoFrame)
    sa.setStyleSheet(f"background: {Colors.BG_DARKEST};")
    sa.setWidget(panel)
    return sa


class RenderSettingsDialog(QDialog):
    """Context-sensitive rendering settings dialog.

    Shows only the settings relevant to the currently active plot type
    (e.g., Pseudocolor, Dot Plot, etc.) to keep the UI clean and scientist-friendly.
    """

    settings_applied = pyqtSignal(RenderConfig)

    def __init__(self, state: FlowState, parent: QWidget = None):
        super().__init__(parent)
        self._state = state
        self._cfg = RenderConfig.from_dict(state.view.render_config.to_dict())

        # Determine current sample event count for adaptive caps
        self._sample_n = self._get_sample_event_count()

        # Determine active mode
        self._active_mode = self._get_active_mode()
        
        self.setWindowTitle(f"{self._active_mode.value} Settings")
        self.setMinimumWidth(440)
        self.setMinimumHeight(650)
        self.setModal(False)   # Modeless — user can interact with plot while tweaking
        self.setStyleSheet(f"background: {Colors.BG_DARKEST}; color: {Colors.FG_PRIMARY};")

        self._active_panel = None
        self._setup_ui()

    # ── Setup ─────────────────────────────────────────────────────────

    def _get_active_mode(self) -> DisplayMode:
        """Map the string state to the DisplayMode enum."""
        try:
            mode_str = self._state.active_plot_type
            for mode in DisplayMode:
                if mode.value.lower() == mode_str.lower():
                    return mode
        except Exception:
            pass
        return DisplayMode.PSEUDOCOLOR

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 12)

        # Header
        header = QLabel(f"  {self._active_mode.value} Settings")
        header.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {Colors.FG_PRIMARY};"
            f" background: {Colors.BG_DARK}; padding: 14px 16px;"
            f" border-bottom: 1px solid {Colors.BORDER};"
        )
        root.addWidget(header)

        sub = QLabel("  Changes apply globally to all open plots")
        sub.setStyleSheet(
            f"font-size: 11px; color: {Colors.FG_SECONDARY};"
            f" background: {Colors.BG_DARK}; padding: 4px 16px 10px 16px;"
            f" border-bottom: 1px solid {Colors.BORDER};"
        )
        root.addWidget(sub)

        # Instantiate only the active panel
        mode = self._active_mode
        if mode == DisplayMode.PSEUDOCOLOR:
            self._active_panel = PseudocolorSettingsPanel(self._cfg.pseudocolor, self._sample_n)
        elif mode == DisplayMode.DOT_PLOT:
            self._active_panel = DotPlotSettingsPanel(self._cfg.dot_plot, self._sample_n)
        elif mode in (DisplayMode.HISTOGRAM, DisplayMode.CDF):
            self._active_panel = HistogramSettingsPanel(self._cfg.histogram)
        elif mode == DisplayMode.CONTOUR:
            self._active_panel = ContourSettingsPanel(self._cfg.contour)
        elif mode == DisplayMode.DENSITY:
            self._active_panel = DensitySettingsPanel(self._cfg.density)
        else:
            # Fallback to Pseudocolor if something goes wrong
            self._active_panel = PseudocolorSettingsPanel(self._cfg.pseudocolor, self._sample_n)

        # Wrap in scroll area
        root.addWidget(_scrollable(self._active_panel), stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 0)

        self._btn_reset = QPushButton("Reset to Defaults")
        self._btn_reset.setToolTip("Reset settings to factory defaults.")
        self._btn_reset.setFixedHeight(30)
        self._btn_reset.setStyleSheet(self._flat_btn_style())
        self._btn_reset.clicked.connect(self._reset_current_panel)

        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setFixedHeight(30)
        self._btn_apply.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST};"
            f" border: none; border-radius: 4px; font-size: 12px; font-weight: 700;"
            f" padding: 2px 20px; }}"
            f"QPushButton:hover {{ opacity: 0.85; }}"
        )
        self._btn_apply.clicked.connect(self._apply)

        self._btn_close = QPushButton("Close")
        self._btn_close.setFixedHeight(30)
        self._btn_close.setStyleSheet(self._flat_btn_style())
        self._btn_close.clicked.connect(self.accept)

        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        btn_row.addWidget(self._btn_apply)
        root.addLayout(btn_row)

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_sample_event_count(self) -> int:
        """Return the event count of the active sample, or max of any sample."""
        try:
            # Try current sample first
            sid = self._state.current_sample_id
            if sid:
                sample = self._state.experiment.samples.get(sid)
                if sample and sample.fcs_data and sample.fcs_data.events is not None:
                    return len(sample.fcs_data.events)
            
            # Fallback: check all loaded samples and take the max
            counts = [
                len(s.fcs_data.events) for s in self._state.experiment.samples.values()
                if s.fcs_data and s.fcs_data.events is not None
            ]
            if counts:
                return max(counts)
        except Exception:
            pass
        return 100_000

    def _flat_btn_style(self) -> str:
        return (
            f"QPushButton {{ background: {Colors.BG_MEDIUM}; color: {Colors.FG_PRIMARY};"
            f" border: 1px solid {Colors.BORDER}; border-radius: 4px; font-size: 12px;"
            f" font-weight: 600; padding: 2px 14px; }}"
            f"QPushButton:hover {{ color: {Colors.ACCENT_PRIMARY}; }}"
        )

    def _reset_current_panel(self) -> None:
        """Reset the active panel to its dataclass defaults."""
        defaults = RenderConfig()
        mode = self._active_mode
        if mode == DisplayMode.PSEUDOCOLOR:
            self._active_panel.set_config(defaults.pseudocolor)
        elif mode == DisplayMode.DOT_PLOT:
            self._active_panel.set_config(defaults.dot_plot)
        elif mode in (DisplayMode.HISTOGRAM, DisplayMode.CDF):
            self._active_panel.set_config(defaults.histogram)
        elif mode == DisplayMode.CONTOUR:
            self._active_panel.set_config(defaults.contour)
        elif mode == DisplayMode.DENSITY:
            self._active_panel.set_config(defaults.density)

    def _apply(self) -> None:
        """Collect configs from the active panel and emit."""
        mode = self._active_mode
        if mode == DisplayMode.PSEUDOCOLOR:
            self._cfg.pseudocolor = self._active_panel.get_config()
        elif mode == DisplayMode.DOT_PLOT:
            self._cfg.dot_plot = self._active_panel.get_config()
        elif mode in (DisplayMode.HISTOGRAM, DisplayMode.CDF):
            self._cfg.histogram = self._active_panel.get_config()
        elif mode == DisplayMode.CONTOUR:
            self._cfg.contour = self._active_panel.get_config()
        elif mode == DisplayMode.DENSITY:
            self._cfg.density = self._active_panel.get_config()
            
        logger.info(f"RenderSettingsDialog: applying config for {mode.value}")
        self.settings_applied.emit(self._cfg)
