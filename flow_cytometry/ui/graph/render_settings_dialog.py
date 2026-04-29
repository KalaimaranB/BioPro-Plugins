"""Dialog for customizing flow cytometry rendering parameters."""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QSlider, QDoubleSpinBox, QSpinBox, QFormLayout, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.config import RenderConfig
from ...analysis import constants

logger = logging.getLogger(__name__)

class RenderSettingsDialog(QDialog):
    """Popup dialog for adjusting pseudocolor rendering parameters."""
    
    settings_applied = pyqtSignal(RenderConfig)

    def __init__(self, state: FlowState, parent: QWidget = None):
        super().__init__(parent)
        self._state = state
        self._current_config = state.view.render_config
        
        self.setWindowTitle("Rendering Settings")
        self.setMinimumWidth(400)
        self.setModal(True)
        
        # We don't apply until the user clicks Apply, so we work on a copy.
        self._working_config = RenderConfig.from_dict(self._current_config.to_dict())
        
        self._setup_ui()
        self._populate_from_config(self._working_config)
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        header = QLabel("Pseudocolor Density Settings")
        header.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.FG_PRIMARY};")
        layout.addWidget(header)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        # Helper to create a slider + spinbox row
        def add_control_row(label, tooltip, min_val, max_val, step, current_val, is_int=False):
            row_layout = QHBoxLayout()
            
            if is_int:
                spin = QSpinBox()
                spin.setRange(int(min_val), int(max_val))
                spin.setSingleStep(int(step))
            else:
                spin = QDoubleSpinBox()
                spin.setRange(min_val, max_val)
                spin.setSingleStep(step)
                spin.setDecimals(2)
            
            spin.setValue(current_val)
            spin.setFixedWidth(80)
            spin.setToolTip(tooltip)
            
            slider = QSlider(Qt.Orientation.Horizontal)
            if is_int:
                slider.setRange(int(min_val), int(max_val))
                slider.setSingleStep(int(step))
                slider.setValue(int(current_val))
                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
            else:
                # Map float to int for slider (e.g. 0.0-1.0 -> 0-100)
                precision = 100
                slider.setRange(int(min_val * precision), int(max_val * precision))
                slider.setValue(int(current_val * precision))
                slider.valueChanged.connect(lambda v: spin.setValue(v / precision))
                spin.valueChanged.connect(lambda v: slider.setValue(int(v * precision)))
            
            slider.setToolTip(tooltip)
            
            row_layout.addWidget(slider)
            row_layout.addWidget(spin)
            
            lbl = self._make_label(label)
            lbl.setToolTip(tooltip)
            form_layout.addRow(lbl, row_layout)
            return spin

        # 1. Max Events
        self.spin_events = add_control_row(
            "Max Events:",
            "The maximum number of events to render on the main plot.\n"
            "Lower values (e.g. 50k) make the UI faster and smoother.\n"
            "Higher values (e.g. 500k) show more detail but may lag during gate moves.",
            10000, 1000000, 10000, self._working_config.max_events, is_int=True
        )
        
        # 2. Grid Resolution (NBins Scaling)
        self.spin_nbins = add_control_row(
            "Grid Resolution:",
            "Multiplies the density estimation grid size.\n"
            "Higher values make populations appear sharper and less 'blocky'.\n"
            "Lower values are faster but can result in visible grid artifacts.",
            0.5, 4.0, 0.1, self._working_config.nbins_scaling
        )
        
        # 3. Smoothing (Sigma)
        self.spin_sigma = add_control_row(
            "Smoothing (Sigma):",
            "Controls the Gaussian blur applied to the density grid.\n"
            "Higher values create a softer, more continuous 'glow' around populations.\n"
            "Lower values make the population borders sharper and more granular.",
            0.1, 5.0, 0.1, self._working_config.sigma_scaling
        )
        
        # 4. Density Threshold
        self.spin_thresh = add_control_row(
            "Density Threshold:",
            "The cutoff below which points are snapped to the pure background blue.\n"
            "Increase this to hide sparse background noise and 'outliers'.\n"
            "Decrease this to see every single sparse event in the plot.",
            0.0, 0.5, 0.01, self._working_config.density_threshold
        )
        
        # 5. Vibrancy Min
        self.spin_vib_min = add_control_row(
            "Vibrancy Min:",
            "The starting brightness floor for population colors.\n"
            "Higher values make low-density regions appear brighter immediately.\n"
            "Lower values give a more dramatic contrast between sparse and dense regions.",
            0.0, 1.0, 0.05, self._working_config.vibrancy_min
        )
        
        # 6. Vibrancy Range
        self.spin_vib_range = add_control_row(
            "Vibrancy Range:",
            "The amplification factor for high-density color transitions.\n"
            "Higher values make the population 'cores' look more intense and colorful.\n"
            "Lower values result in a flatter, more uniform color appearance.",
            0.1, 2.0, 0.05, self._working_config.vibrancy_range
        )
        
        layout.addLayout(form_layout)
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setToolTip("Restore all sliders to standard optimized parameters.")
        self.btn_reset.clicked.connect(self._reset_to_defaults)
        
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setStyleSheet(f"background-color: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST}; font-weight: bold;")
        self.btn_apply.clicked.connect(self._apply_settings)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_apply)
        
        layout.addLayout(btn_layout)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {Colors.FG_SECONDARY};")
        return lbl

    def _populate_from_config(self, config: RenderConfig):
        self.spin_events.setValue(config.max_events)
        self.spin_nbins.setValue(config.nbins_scaling)
        self.spin_sigma.setValue(config.sigma_scaling)
        self.spin_thresh.setValue(config.density_threshold)
        self.spin_vib_min.setValue(config.vibrancy_min)
        self.spin_vib_range.setValue(config.vibrancy_range)

    def _reset_to_defaults(self):
        """Reset the UI sliders to standard constants."""
        default_config = RenderConfig()  # Uses constants by default
        self._populate_from_config(default_config)

    def _apply_settings(self):
        """Construct a new RenderConfig and emit it without closing."""
        new_config = RenderConfig(
            max_events=self.spin_events.value(),
            nbins_scaling=self.spin_nbins.value(),
            sigma_scaling=self.spin_sigma.value(),
            density_threshold=self.spin_thresh.value(),
            vibrancy_min=self.spin_vib_min.value(),
            vibrancy_range=self.spin_vib_range.value()
        )
        self.settings_applied.emit(new_config)

