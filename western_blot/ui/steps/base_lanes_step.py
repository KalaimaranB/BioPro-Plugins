"""Base class for Lane Detection Wizard steps.

Consolidates lane detection, state syncing, layout construction, 
spinbox events, and lane boundary manipulation into a base UI class.
"""

from __future__ import annotations
import logging

from PyQt6.QtWidgets import (
    QCheckBox, QGroupBox, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget, QHBoxLayout
)
from biopro.plugins.western_blot.ui.base import WizardPanel, WizardStep
from biopro.plugins.western_blot.ui.steps.base_step import BaseStepWidget
from biopro.ui.theme import Colors

logger = logging.getLogger(__name__)

class BaseLanesStep(WizardStep):
    """Abstract base class for lane detection (Ponceau and WB)."""
    
    label = "Base Lanes"

    _step_title = "Step 2: Detect Lanes"
    _step_subtitle = "Auto-detect or manually set the number of lanes."
    _detect_btn_text = "🔍  Detect Lanes"
    
    def get_analyzer(self, panel: WizardPanel):
        """Must return the correct analyzer for this step."""
        raise NotImplementedError
        
    def _build_extra_ui(self, layout: QVBoxLayout, panel: WizardPanel) -> None:
        """Hook to add additional UI groups (Types or Mappings)."""
        pass

    def _on_lanes_updated(self, num_lanes: int) -> None:
        """Hook called after lane count changes (to rebuild mappings/types)."""
        pass

    def _save_state(self, panel: WizardPanel) -> None:
        """Hook for saving final mappings or types to analyzer."""
        pass

    def build_page(self, panel: WizardPanel) -> QWidget:
        self._panel = panel
        self._canvas = None
        self._manually_adjusted = False

        page = BaseStepWidget(title=self._step_title, subtitle=self._step_subtitle)

        lane_group = QGroupBox("Lane Detection")
        lane_layout = QVBoxLayout(lane_group)
        lane_layout.setSpacing(8)

        self.chk_auto = QCheckBox("Auto-detect lanes")
        self.chk_auto.setChecked(True)
        lane_layout.addWidget(self.chk_auto)

        self.spin_lanes = QSpinBox()
        self.spin_lanes.setRange(1, 30)
        self.spin_lanes.setValue(6)
        self.spin_lanes.valueChanged.connect(lambda _: self._on_lane_count_manually_changed(panel))
        lane_layout.addLayout(self._row("Number of lanes:", self.spin_lanes))

        self.spin_smoothing = QSpinBox()
        self.spin_smoothing.setRange(3, 51)
        self.spin_smoothing.setValue(15)
        self.spin_smoothing.setSingleStep(2)
        lane_layout.addLayout(self._row("Smoothing:", self.spin_smoothing))

        self.btn_detect = QPushButton(self._detect_btn_text)
        self.btn_detect.setStyleSheet(
            f"QPushButton {{ background-color: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST};"
            f" border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_PRIMARY_HOVER}; }}"
        )
        self.btn_detect.setMinimumHeight(36)
        self.btn_detect.clicked.connect(lambda: self.run_detection(panel))
        lane_layout.addWidget(self.btn_detect)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("subtitle")
        self.lbl_status.setWordWrap(True)
        lane_layout.addWidget(self.lbl_status)

        page.add_content_widget(lane_group)

        self._build_extra_ui(page.content_layout, panel)

        return self._scroll(page)

    def set_canvas(self, canvas) -> None:
        self._canvas = canvas

    def on_enter(self) -> None:
        """
        Architectural Pillar 1 & 2:
        Strict Unidirectional State Hydration for Lanes.
        """
        self._on_enter_hook()
        analyzer = self.get_analyzer(self._panel)
        lanes = analyzer.state.lanes

        # 1. Sync UI Spinners
        if lanes:
            self.spin_lanes.blockSignals(True)
            self.spin_lanes.setValue(len(lanes))
            self.spin_lanes.blockSignals(False)
            self._on_lanes_updated(len(lanes))

            # Since lanes exist, uncheck "Auto-detect" so the user knows they are manually set
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(False)
            self.chk_auto.blockSignals(False)
            self._manually_adjusted = True

        # 2. Explicit Canvas Context Switching (Pillar 2)
        if self._canvas is not None:
            # First, ensure the correct underlying image is visible
            if analyzer.state.processed_image is not None:
                self._panel.image_changed.emit(analyzer.state.processed_image)
            elif analyzer.state.original_image is not None:
                self._panel.image_changed.emit(analyzer.state.original_image)

            # Second, set up the interaction mode
            self._canvas.set_lane_edit_mode(True)
            try:
                self._canvas.lane_border_changed.disconnect(self._on_lane_border_changed)
            except Exception:
                pass
            self._canvas.lane_border_changed.connect(self._on_lane_border_changed)

            # Third, broadcast the lanes to be drawn
            if lanes:
                self._panel.lanes_detected.emit(lanes)
            else:
                self._panel.lanes_detected.emit([])

            # Crucially, clear any BANDS! This step is for lanes only.
            self._panel.bands_detected.emit([], [])

    def _on_enter_hook(self) -> None:
        pass

    def on_leave(self) -> None:
        if self._canvas is not None:
            self._canvas.set_lane_edit_mode(False)
            try:
                self._canvas.lane_border_changed.disconnect(self._on_lane_border_changed)
            except Exception:
                pass
            analyzer = self.get_analyzer(self._panel)
            if analyzer.state.lanes:
                self._canvas.add_lane_overlays(analyzer.state.lanes)

    def on_next(self, panel: WizardPanel) -> bool:
        analyzer = self.get_analyzer(panel)
        if self._manually_adjusted and analyzer.state.lanes:
            self._save_state(panel)
            return True
        self.run_detection(panel)
        if not analyzer.state.lanes:
            return False
        self._save_state(panel)
        return True

    def _auto_lanes_checked(self) -> bool:
        return self.chk_auto.isChecked()

    def _on_lane_border_changed(self, border_idx: int, new_x: float) -> None:
        analyzer = self.get_analyzer(self._panel)
        lanes = analyzer.state.lanes
        if not lanes:
            return

        boundaries = [lanes[0].x_start]
        for lane in lanes:
            boundaries.append(lane.x_end)

        if border_idx < 1 or border_idx >= len(boundaries) - 1:
            return

        boundaries[border_idx] = int(round(new_x))
        MIN_WIDTH = 10
        for i in range(1, len(boundaries)):
            if boundaries[i] <= boundaries[i - 1] + MIN_WIDTH:
                boundaries[i] = boundaries[i - 1] + MIN_WIDTH

        from biopro.plugins.western_blot.analysis.lane_detection import LaneROI
        img_h = lanes[0].y_end
        new_lanes = [
            LaneROI(
                index=i,
                x_start=boundaries[i],
                x_end=boundaries[i + 1],
                y_start=0,
                y_end=img_h,
                lane_type=self._get_default_lane_type(i)
            )
            for i in range(len(boundaries) - 1)
        ]

        analyzer.state.lanes = new_lanes
        analyzer.state.profiles = []
        analyzer.state.baselines = []
        analyzer.state.bands = []
        if hasattr(analyzer.state, 'results_df'):
            analyzer.state.results_df = None

        if self._canvas is not None:
            self._canvas.add_lane_overlays(new_lanes)

        self._panel.lanes_detected.emit(new_lanes)
        self._on_lanes_updated(len(new_lanes))
        self._manually_adjusted = True
        
        prefix = self._get_status_prefix()
        self._panel.status_message.emit(
            f"{prefix}Lane border moved — {len(new_lanes)} lanes."
        )
        self.lbl_status.setText(f"✅  {len(new_lanes)} lanes (manually adjusted)")
        self.lbl_status.setStyleSheet(f"color: {Colors.SUCCESS};")
        self._panel.state_changed.emit()

    def _get_default_lane_type(self, index: int) -> str:
        return "Sample"

    def _on_lane_count_manually_changed(self, panel: WizardPanel) -> None:
        self._manually_adjusted = False
        if self.chk_auto.isChecked():
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(False)
            self.chk_auto.blockSignals(False)
        analyzer = self.get_analyzer(panel)
        if analyzer.state.processed_image is not None:
            self.run_detection(panel)

    def run_detection(self, panel: WizardPanel) -> None:
        try:
            analyzer = self.get_analyzer(panel)
            num_lanes = None if self.chk_auto.isChecked() else self.spin_lanes.value()
            lanes = analyzer.detect_lanes(
                num_lanes=num_lanes,
                smoothing_window=self.spin_smoothing.value(),
            )
            self.spin_lanes.blockSignals(True)
            self.spin_lanes.setValue(len(lanes))
            self.spin_lanes.blockSignals(False)

            self.lbl_status.setText(f"✅  Detected {len(lanes)} lanes")
            self.lbl_status.setStyleSheet(f"color: {Colors.SUCCESS};")
            prefix = self._get_status_prefix()
            panel.status_message.emit(f"{prefix}Detected {len(lanes)} lanes")
            
            panel.lanes_detected.emit(lanes)
            self._on_lanes_updated(len(lanes))
            
            if self._canvas is not None and getattr(self._canvas, '_lane_edit_mode', False):
                self._canvas.add_lane_overlays(lanes)
                
            self._panel.state_changed.emit()
        except Exception as e:
            self.lbl_status.setText(f"❌  {e}")
            self.lbl_status.setStyleSheet(f"color: {Colors.ACCENT_DANGER};")
            logger.exception("Lane detection error")

    def _get_status_prefix(self) -> str: return ""
