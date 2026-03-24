"""Western Blot analysis panel.

Entry point for the Western Blot workflow.  Shows a setup screen first
so the user can choose optional stages (Ponceau normalization), then
builds a ``WizardPanel`` with the correct step list and switches to it.

This file is intentionally thin — all analysis logic lives in the step
classes under ``biopro/ui/wizard/steps/``.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

# --- USE RELATIVE IMPORTS FOR PLUGIN FILES ---
from .image_canvas import ImageCanvas
from .results_widget import ResultsWidget
from .base import WizardPanel
from .setup_screen import SetupScreen
from .steps.wb_load import WBLoadStep
from .steps.wb_lanes import WBLanesStep
from .steps.wb_bands import WBBandsStep
from .steps.wb_results import WBResultsStep
from .steps.ponceau_load import PonceauLoadStep
from .steps.ponceau_lanes import PonceauLanesStep
from .steps.ponceau_bands import PonceauBandsStep

# (You can still use absolute imports for the core app, like biopro.ui.theme,
# because the core app will always be installed!)
from biopro.plugins.western_blot.analysis.western_blot import WesternBlotAnalyzer
from biopro.plugins.western_blot.analysis.ponceau import PonceauAnalyzer

logger = logging.getLogger(__name__)

_PAGE_SETUP = 0
_PAGE_WIZARD = 1


class WesternBlotPanel(QWidget):
    """Western Blot entry point — setup screen then wizard.

    Exposes the same signals as the original monolithic panel so
    ``MainWindow`` needs no changes.
    """

    # ── Signals ───────────────────────────────────────────────────────
    state_changed = pyqtSignal()
    status_message = pyqtSignal(str)
    image_changed = pyqtSignal(object)
    lanes_detected = pyqtSignal(object)
    bands_detected = pyqtSignal(object, object)
    results_ready = pyqtSignal(object)
    selected_bands_changed = pyqtSignal(list)
    peak_picking_enabled = pyqtSignal(bool)
    crop_mode_toggled = pyqtSignal(bool)
    profile_hovered = pyqtSignal(int, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._canvas = None
        self._wizard: WizardPanel | None = None
        self._wb_results_step: WBResultsStep | None = None
        self.results_widget = ResultsWidget()
        if hasattr(self, 'selected_bands_changed'):
            self.selected_bands_changed.connect(self.results_widget.update_pairwise_comparison)
        self.canvas = ImageCanvas()
        self.set_canvas(self.canvas)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()

        # Page 0: setup screen
        self._setup_screen = SetupScreen()
        self._setup_screen.analysis_requested.connect(self._on_start_analysis)
        self._stack.addWidget(self._setup_screen)

        # Page 1: wizard — built dynamically on start
        self._wizard_placeholder = QWidget()
        self._stack.addWidget(self._wizard_placeholder)

        layout.addWidget(self._stack)

    # ── Public API ────────────────────────────────────────────────────

    def set_canvas(self, canvas) -> None:
        self._canvas = canvas
        self.results_widget.set_canvas(canvas)
        if self._wizard is not None:
            self._wizard.set_canvas(canvas)

        self.image_changed.connect(self._canvas.set_image)

        # ── NEW: Plugin -> Canvas Wiring ────────────────────────────────
        self.lanes_detected.connect(lambda lanes: self._canvas.add_lane_overlays(lanes))
        self.bands_detected.connect(lambda bands, lanes: self._canvas.add_band_overlays(lanes, bands))
        self.peak_picking_enabled.connect(self._canvas.set_peak_picking_enabled)
        self.crop_mode_toggled.connect(self._canvas.set_crop_mode)
        
        # Internal hover logic
        self.profile_hovered.connect(self._handle_profile_hovered)

        # ── NEW: Canvas -> Plugin Wiring ────────────────────────────────
        try: self._canvas.band_clicked.disconnect() 
        except Exception: pass
        self._canvas.band_clicked.connect(self.on_band_clicked)
        
        try: self._canvas.peak_pick_requested.disconnect()
        except Exception: pass
        self._canvas.peak_pick_requested.connect(self.on_peak_pick_requested)
        
        try: self._canvas.crop_requested.disconnect()
        except Exception: pass
        self._canvas.crop_requested.connect(self.on_crop_requested)

        try:
            self._canvas.band_right_clicked.disconnect()
        except Exception:
            pass
        self._canvas.band_right_clicked.connect(self.on_band_right_clicked)

        try:
            self._canvas.canvas_range_selected.disconnect()
        except Exception:
            pass
        self._canvas.canvas_range_selected.connect(self.on_canvas_range_selected)

    def _handle_profile_hovered(self, lane_idx: int, y_pos: float) -> None:
        """Calculates where to draw the hover indicator on the canvas."""
        if not self._canvas or not self._wizard:
            return

        # Dynamically get the active analyzer!
        active_step = self._wizard._steps[self._wizard._idx]
        if hasattr(active_step, "get_analyzer"):
            analyzer = active_step.get_analyzer()
        else:
            analyzer = self.analyzer

        lanes = getattr(analyzer.state, "lanes", [])
        if not lanes or lane_idx < 0 or lane_idx >= len(lanes) or y_pos < 0:
            self._canvas.hide_hover_indicator()
            return

        lane = lanes[lane_idx]
        self._canvas.show_hover_indicator(lane, lane.y_start + float(y_pos))

    def reset_to_setup(self) -> None:
        """Return to the setup screen and discard the current wizard.

        Called when the user navigates back to the home screen so they
        can change pipeline options (e.g. include/exclude Ponceau) on
        their next run.
        """
        if self._wizard is not None:
            self._stack.removeWidget(self._wizard)
            self._wizard.deleteLater()
            self._wizard = None
        self._wb_results_step = None

        self._wizard_placeholder = QWidget()
        self._stack.addWidget(self._wizard_placeholder)
        self._stack.setCurrentIndex(_PAGE_SETUP)

    # ── Slots forwarded from MainWindow / canvas ──────────────────────

    def on_band_clicked(self, band) -> None:
        if self._wizard:
            self._wizard.on_band_clicked(band)

        if hasattr(self, 'results_widget'):
            self.results_widget.assign_band_to_active_slot(band)

    def on_peak_pick_requested(self, x: float, y: float) -> None:
        if self._wizard:
            self._wizard.on_peak_pick_requested(x, y)

    def on_crop_requested(self, rect) -> None:
        if self._wizard:
            self._wizard.on_crop_requested(rect)

    def on_band_right_clicked(self, lane_idx: int, y_pos: float) -> None:
        if self._wizard:
            step = self._wizard._steps[self._wizard._idx]
            if hasattr(step, "on_band_right_clicked"):
                step.on_band_right_clicked(lane_idx, y_pos, self._wizard)

    def on_canvas_range_selected(self, lane_idx: int, y_start: float, y_end: float) -> None:
        if self._wizard:
            step = self._wizard._steps[self._wizard._idx]
            if hasattr(step, "on_canvas_range_selected"):
                step.on_canvas_range_selected(lane_idx, y_start, y_end, self._wizard)


    @property
    def analyzer(self):
        """Expose WB analyzer so MainWindow._on_profile_hovered can read lanes."""
        if self._wizard is not None:
            return self._wizard.analyzer
        return WesternBlotAnalyzer()

    # ── Build and launch the wizard ───────────────────────────────────

    def _on_start_analysis(self, include_ponceau: bool) -> None:
        """Build step list from user choices and launch the wizard."""
        steps = []

        # ── Optional: Ponceau stage ───────────────────────────────────
        if include_ponceau:
            steps += [
                PonceauLoadStep(),
                PonceauLanesStep(),
                PonceauBandsStep(),
            ]

        # ── Western Blot stage ────────────────────────────────────────
        wb_load    = WBLoadStep()
        wb_lanes   = WBLanesStep()
        wb_bands   = WBBandsStep()
        wb_results = WBResultsStep()
        steps += [wb_load, wb_lanes, wb_bands, wb_results]

        # Store reference so set_results_widget can wire the spinner
        self._wb_results_step = wb_results

        try:
            self.results_widget._spin_slots.valueChanged.disconnect()
        except Exception:
            pass

        def _on_slots_changed(n: int) -> None:
            self.results_widget._rebuild_slots(n)
            wb_results._compute_results()
            self.state_changed.emit()

        self.results_widget._spin_slots.valueChanged.connect(_on_slots_changed)

        # Wire lane detection → update ref lane combo in results step
        _orig_run = wb_lanes.run_detection
        def _run_and_update(panel):
            _orig_run(panel)
            wb_results.update_ref_lane_combo(len(panel.analyzer.state.lanes))
        wb_lanes.run_detection = _run_and_update

        # Build wizard
        wizard = WizardPanel(steps=steps, title="Western Blot Analysis")

        # Attach analyzers directly on the wizard instance so steps can
        # access them via panel.analyzer / panel.ponceau_analyzer
        wizard.analyzer = WesternBlotAnalyzer()
        wizard.ponceau_analyzer = PonceauAnalyzer() if include_ponceau else None

        # Filled by set_results_widget() once MainWindow passes the ref
        wizard._results_widget_ref = self.results_widget

        # Forward all wizard signals → this panel's signals
        wizard.status_message.connect(self.status_message)
        wizard.image_changed.connect(self.image_changed)
        wizard.lanes_detected.connect(self.lanes_detected)
        wizard.bands_detected.connect(self.bands_detected)
        wizard.state_changed.connect(self.state_changed)

        def _handle_results(df):
            self.results_widget.set_results(df)
            self.results_ready.emit(df)
            
        wizard.results_ready.connect(_handle_results)

        wizard.selected_bands_changed.connect(self.selected_bands_changed)
        wizard.peak_picking_enabled.connect(self.peak_picking_enabled)
        wizard.crop_mode_toggled.connect(self.crop_mode_toggled)
        wizard.profile_hovered.connect(self.profile_hovered)
        

        if self._canvas is not None:
            wizard.set_canvas(self._canvas)

        # Replace placeholder and show wizard
        self._wizard = wizard
        self._stack.removeWidget(self._wizard_placeholder)
        self._stack.addWidget(wizard)
        self._stack.setCurrentWidget(wizard)

    def get_right_panel_widget(self):
        """Returns the custom results widget to the core host."""
        return self.results_widget

    def get_center_widget(self):
        """Returns the custom canvas to the core host."""
        return self.canvas

    def export_state(self) -> dict:
        """Packages the complete analysis state and UI position into a JSON-safe dictionary."""
        if self._wizard is None:
            return {}

        state_dict = {
            # Use the correct WizardPanel properties!
            "current_step": self._wizard._idx,
            "max_step": self._wizard._max_idx
        }

        def _extract_analyzer_state(analyzer):
            if not analyzer or not hasattr(analyzer, 'state'):
                return {}
            st = analyzer.state
            return {
                "image_path": str(st.image_path) if st.image_path else None,
                "is_inverted": st.is_inverted,
                "rotation_angle": st.rotation_angle,
                "contrast_alpha": st.contrast_alpha,
                "contrast_beta": st.contrast_beta,
                "manual_crop_rect": st.manual_crop_rect,
                "lanes": [lane.to_dict() for lane in st.lanes] if st.lanes else [],
                "bands": [band.to_dict() for band in st.bands] if st.bands else [],
            }

        # Save both pipelines!
        state_dict["wb"] = _extract_analyzer_state(self.analyzer)
        if self._wizard.ponceau_analyzer:
            state_dict["ponceau"] = _extract_analyzer_state(self._wizard.ponceau_analyzer)
            state_dict["ponceau"]["mode"] = self._wizard.ponceau_analyzer.mode
            state_dict["ponceau"]["lane_mapping"] = self._wizard.ponceau_analyzer.lane_mapping.copy()
            state_dict["ponceau"]["ref_band_indices"] = self._wizard.ponceau_analyzer.ref_band_indices.copy()

        if hasattr(self, 'results_widget'):
            state_dict["results_widget"] = {
                "num_slots": self.results_widget._num_slots,
                # We can't save raw Python objects, so we just save their (lane, band) coordinates!
                "slots": [
                    (b.lane_index, b.band_index) if b is not None else None
                    for b in self.results_widget._slots
                ]
            }

        return state_dict

    def load_state(self, state_dict: dict) -> None:
        """Restores the analysis state, reloads images, and redraws the UI."""
        if self._wizard is None or not state_dict:
            return

        def _restore_analyzer_state(analyzer, data):
            if not analyzer or not data:
                return

            # 1. Reload the image from the hard drive
            path = data.get("image_path")
            if path:
                try:
                    analyzer.load_image(path)
                    # 2. Re-apply the exact preprocessing math
                    analyzer.preprocess(
                        invert_lut=data.get("is_inverted", False),
                        rotation_angle=data.get("rotation_angle", 0.0),
                        contrast_alpha=data.get("contrast_alpha", 1.0),
                        contrast_beta=data.get("contrast_beta", 0.0),
                        manual_crop_rect=data.get("manual_crop_rect")
                    )
                except Exception as e:
                    logger.error(f"Time Machine image restore error: {e}")

            # 3. Restore the biological data
            from biopro.plugins.western_blot.analysis.lane_detection import LaneROI
            from biopro.plugins.western_blot.analysis.peak_analysis import DetectedBand

            analyzer.state.lanes = [LaneROI.from_dict(d) for d in data.get("lanes", [])]
            analyzer.state.bands = [DetectedBand.from_dict(d) for d in data.get("bands", [])]

        # Restore both pipelines
        _restore_analyzer_state(self.analyzer, state_dict.get("wb", {}))
        if self._wizard.ponceau_analyzer:
            _restore_analyzer_state(self._wizard.ponceau_analyzer, state_dict.get("ponceau", {}))
            pon_data = state_dict.get("ponceau", {})
            self._wizard.ponceau_analyzer.mode = pon_data.get("mode", "total")
            self._wizard.ponceau_analyzer.lane_mapping = pon_data.get("lane_mapping", {})
            self._wizard.ponceau_analyzer.ref_band_indices = pon_data.get("ref_band_indices", {})

            # --- NEW: Restore ResultsWidget Slot Assignments ---
            rw_data = state_dict.get("results_widget", {})
            if rw_data and hasattr(self, "results_widget"):
                num_slots = rw_data.get("num_slots", 2)

                # 1. Quietly set the spinbox and rebuild the buttons
                self.results_widget._spin_slots.blockSignals(True)
                self.results_widget._spin_slots.setValue(num_slots)
                self.results_widget._rebuild_slots(num_slots)
                self.results_widget._spin_slots.blockSignals(False)

                # 2. Re-assign the actual band objects back into the slots
                slot_coords = rw_data.get("slots", [])
                for i, coords in enumerate(slot_coords):
                    if coords is not None and i < self.results_widget._num_slots:
                        lane_idx, band_idx = coords
                        # Find the rebuilt band object from the analyzer
                        matching_bands = [
                            b for b in self.analyzer.state.bands
                            if b.lane_index == lane_idx and b.band_index == band_idx
                        ]
                        if matching_bands:
                            self.results_widget._slots[i] = matching_bands[0]

                # 3. Update the UI text
                for i in range(self.results_widget._num_slots):
                    self.results_widget._update_slot_label(i)

        # 4. Move the UI to the correct Wizard Page
        target_step = state_dict.get("current_step", 0)
        max_step = state_dict.get("max_step", 0)

        if self._wizard:
            # We must restore the max_idx FIRST, otherwise the Time Machine
            # might get blocked by our new security check in go_to_step!
            self._wizard._max_idx = max_step
            self._wizard.go_to_step(target_step)

        # 5. Force the Canvas to Redraw
        active_analyzer = self._wizard.ponceau_analyzer if target_step < 3 and self._wizard.ponceau_analyzer else self.analyzer

        if active_analyzer and active_analyzer.state.processed_image is not None:
            self.image_changed.emit(active_analyzer.state.processed_image)

        lanes = getattr(active_analyzer.state, "lanes", [])
        bands = getattr(active_analyzer.state, "bands", [])
        self.lanes_detected.emit(lanes)
        self.bands_detected.emit(bands, lanes)

        # --- FIX 2 & 3: UI Sync & Results Widget Visibility ---
        if self._wb_results_step:
            self._wb_results_step._compute_results()

            # A. Sync the Ponceau UI dropdown to match the restored math
            if self._wizard.ponceau_analyzer:
                from biopro.plugins.western_blot.ui.steps.ponceau_bands import PonceauBandsStep
                for step in self._wizard._steps:
                    if isinstance(step, PonceauBandsStep):
                        idx = 0 if self._wizard.ponceau_analyzer.mode == "reference_band" else 1
                        step.combo_mode.blockSignals(True)
                        step.combo_mode.setCurrentIndex(idx)
                        step.combo_mode.blockSignals(False)
                        step._sync_mode(self._wizard)
                        break

            # B. Hide the Results panel if we aren't on the final step!
            parent_container = self.results_widget.parentWidget()
            if parent_container:
                # Check if the target step is actually the WBResultsStep
                is_final_step = (self._wizard._steps[target_step] == self._wb_results_step)
                if is_final_step:
                    parent_container.show()
                else:
                    parent_container.hide()

    # ── WORKFLOW EXPORT & IMPORT ──────────────────────────────────────

    def export_workflow(self) -> dict:
        """Aggregates both WB and Ponceau states, plus the Results UI state."""
        if self._wizard is None:
            return {}

        wb_payload = self.analyzer.state.to_workflow_dict()

        ponceau_payload = None
        if self._wizard.ponceau_analyzer:
            ponceau_payload = self._wizard.ponceau_analyzer.state.to_workflow_dict()

        integration_data = {}
        if self._wizard.ponceau_analyzer:
            integration_data = {
                "lane_mapping": self._wizard.ponceau_analyzer.lane_mapping,
                "mode": self._wizard.ponceau_analyzer.mode,
                "ref_band_indices": self._wizard.ponceau_analyzer.ref_band_indices
            }

        payload = {
            "western_blot": wb_payload,
            "ponceau": ponceau_payload,
            "integration": integration_data
        }

        # --- NEW: Save the Results Panel Slots ---
        if hasattr(self, 'results_widget'):
            payload["results_widget"] = {
                "num_slots": self.results_widget._num_slots,
                "slots": [
                    (b.lane_index, b.band_index) if b is not None else None
                    for b in self.results_widget._slots
                ]
            }

        return payload

    def load_workflow(self, payload: dict) -> None:
        """Strict 1:1 state reconstruction with path validation."""
        import os
        from PyQt6.QtWidgets import QMessageBox

        if self._wizard is None:
            has_ponceau = "ponceau" in payload and payload["ponceau"] is not None
            self._on_start_analysis(include_ponceau=has_ponceau)

        def _restore_analyzer(analyzer, data, name="Image"):
            if not data: return True

            img_path = data.get("image_path")
            if img_path:
                import os
                from PyQt6.QtWidgets import QMessageBox
                if not os.path.exists(img_path):
                    QMessageBox.warning(self, "Missing File",
                                        f"The {name} source file was moved or deleted:\n{img_path}")
                    return False

                analyzer.load_image(img_path)
                pre = data.get("preprocessing", {})

                # ── THE FIX: Inject the loaded contrast into the physical re-processor ──
                analyzer.preprocess(
                    invert_lut=pre.get("is_inverted", False),
                    rotation_angle=pre.get("rotation_angle", 0.0),
                    contrast_alpha=pre.get("contrast_alpha", 1.5),
                    contrast_beta=pre.get("contrast_beta", -0.7),
                    manual_crop_rect=pre.get("manual_crop_rect")
                )

            analyzer.state.from_workflow_dict(data)
            return True

        # --- Reconstruct Pipelines ---
        wb_success = _restore_analyzer(self.analyzer, payload.get("western_blot"), "Western Blot")
        if not wb_success: return  # Halt if WB image is missing

        if self._wizard.ponceau_analyzer:
            _restore_analyzer(self._wizard.ponceau_analyzer, payload.get("ponceau"), "Ponceau")

            integration = payload.get("integration", {})
            self._wizard.ponceau_analyzer.lane_mapping = {
                int(k): int(v) for k, v in integration.get("lane_mapping", {}).items()
            }
            self._wizard.ponceau_analyzer.mode = integration.get("mode", "total")
            self._wizard.ponceau_analyzer.ref_band_indices = {
                int(k): int(v) for k, v in integration.get("ref_band_indices", {}).items()
            }

        # --- Reconstruct Results UI ---
        rw_data = payload.get("results_widget", {})
        if rw_data and hasattr(self, "results_widget"):
            num_slots = rw_data.get("num_slots", 2)
            self.results_widget._spin_slots.blockSignals(True)
            self.results_widget._spin_slots.setValue(num_slots)
            self.results_widget._rebuild_slots(num_slots)
            self.results_widget._spin_slots.blockSignals(False)

            for i, coords in enumerate(rw_data.get("slots", [])):
                if coords and len(coords) == 2 and i < self.results_widget._num_slots:
                    lane_idx, band_idx = coords
                    matching = [b for b in self.analyzer.state.bands if
                                b.lane_index == lane_idx and b.band_index == band_idx]
                    if matching:
                        self.results_widget._slots[i] = matching[0]

            for i in range(self.results_widget._num_slots):
                self.results_widget._update_slot_label(i)

        # --- UI Synchronization (The Fix for blank "Back" pages) ---
        final_step_idx = len(self._wizard._steps) - 1
        self._wizard._max_idx = final_step_idx
        self._wizard.go_to_step(final_step_idx)

        # Force the Canvas to draw the active analyzer's state
        active_analyzer = self.analyzer
        if active_analyzer.state.processed_image is not None:
            self.image_changed.emit(active_analyzer.state.processed_image)
            self.lanes_detected.emit(active_analyzer.state.lanes)
            self.bands_detected.emit(active_analyzer.state.bands, active_analyzer.state.lanes)

        # Force Results step to calculate using the newly loaded math
        if hasattr(self, '_wb_results_step') and self._wb_results_step:
            self._wb_results_step._compute_results()

        parent_container = self.results_widget.parentWidget()
        if parent_container:
            parent_container.show()