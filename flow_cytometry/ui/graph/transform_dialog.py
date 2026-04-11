"""Transform and scaling dialog — the FlowJo 'T' button equivalent.

Allows the user to adjust axis limits and transformation parameters
(Linear, Log, Biexponential/Logicle) interactively.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.scaling import AxisScale
from ...analysis.transforms import TransformType

logger = logging.getLogger(__name__)


class AxisTransformPanel(QWidget):
    """Panel for adjusting a single axis's scale and limits.
    
    Signals:
        scale_changed: Emitted whenever a setting is changed.
    """

    scale_changed = pyqtSignal()

    def __init__(
        self,
        axis_name: str,
        current_scale: AxisScale,
        auto_range_callback: Callable[[], tuple[float, float]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._axis_name = axis_name
        self._scale = current_scale.copy()
        self._auto_range_callback = auto_range_callback
        
        self._updating_ui = False
        
        self._setup_ui()
        self._load_from_scale()

    @property
    def scale(self) -> AxisScale:
        return self._scale

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)
        
        # ── Scale Type ────────────────────────────────────────────────
        type_group_box = QWidget()
        type_layout = QVBoxLayout(type_group_box)
        type_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_type = QLabel("Scale Type")
        lbl_type.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-weight: bold;")
        type_layout.addWidget(lbl_type)
        
        self._type_group = QButtonGroup(self)
        
        hbox_type = QHBoxLayout()
        self._rb_lin = QRadioButton("Linear")
        self._rb_log = QRadioButton("Log")
        self._rb_biex = QRadioButton("Biexponential")
        
        self._type_group.addButton(self._rb_lin, 0)
        self._type_group.addButton(self._rb_log, 1)
        self._type_group.addButton(self._rb_biex, 2)
        
        hbox_type.addWidget(self._rb_lin)
        hbox_type.addWidget(self._rb_log)
        hbox_type.addWidget(self._rb_biex)
        type_layout.addLayout(hbox_type)
        
        self._type_group.idClicked.connect(self._on_type_changed)
        layout.addWidget(type_group_box)
        
        self._add_separator(layout)
        
        # ── Range Limits ──────────────────────────────────────────────
        range_box = QWidget()
        range_layout = QVBoxLayout(range_box)
        range_layout.setContentsMargins(0, 0, 0, 0)
        
        hbox_range_header = QHBoxLayout()
        lbl_range = QLabel("Display Range")
        lbl_range.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-weight: bold;")
        hbox_range_header.addWidget(lbl_range)
        
        self._btn_auto = QPushButton("Auto-Range")
        self._style_button(self._btn_auto)
        self._btn_auto.clicked.connect(self._on_auto_range)
        hbox_range_header.addWidget(self._btn_auto, alignment=Qt.AlignmentFlag.AlignRight)
        range_layout.addLayout(hbox_range_header)
        
        grid_range = QGridLayout()
        
        # Min
        grid_range.addWidget(QLabel("Min:"), 0, 0)
        self._min_input = QLineEdit()
        self._min_input.setValidator(QDoubleValidator())
        self._min_input.textChanged.connect(self._on_limits_changed)
        grid_range.addWidget(self._min_input, 0, 1)
        
        btn_min_down = QPushButton("−")
        btn_min_up = QPushButton("+")
        self._style_button(btn_min_down)
        self._style_button(btn_min_up)
        btn_min_down.setFixedSize(24, 24)
        btn_min_up.setFixedSize(24, 24)
        btn_min_down.clicked.connect(lambda: self._adjust_limit("min", -1))
        btn_min_up.clicked.connect(lambda: self._adjust_limit("min", 1))
        grid_range.addWidget(btn_min_down, 0, 2)
        grid_range.addWidget(btn_min_up, 0, 3)
        
        # Max
        grid_range.addWidget(QLabel("Max:"), 1, 0)
        self._max_input = QLineEdit()
        self._max_input.setValidator(QDoubleValidator())
        self._max_input.textChanged.connect(self._on_limits_changed)
        grid_range.addWidget(self._max_input, 1, 1)
        
        btn_max_down = QPushButton("−")
        btn_max_up = QPushButton("+")
        self._style_button(btn_max_down)
        self._style_button(btn_max_up)
        btn_max_down.setFixedSize(24, 24)
        btn_max_up.setFixedSize(24, 24)
        btn_max_down.clicked.connect(lambda: self._adjust_limit("max", -1))
        btn_max_up.clicked.connect(lambda: self._adjust_limit("max", 1))
        grid_range.addWidget(btn_max_down, 1, 2)
        grid_range.addWidget(btn_max_up, 1, 3)
        
        range_layout.addLayout(grid_range)
        layout.addWidget(range_box)
        
        self._add_separator(layout)
        
        # ── Biexponential Parameters (Logicle) ────────────────────────
        self._logicle_box = QWidget()
        logicle_layout = QVBoxLayout(self._logicle_box)
        logicle_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_logicle = QLabel("Biexponential Parameters")
        lbl_logicle.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-weight: bold;")
        logicle_layout.addWidget(lbl_logicle)
        
        form_logicle = QFormLayout()
        form_logicle.setContentsMargins(0, 8, 0, 0)
        
        # Top (T)
        self._top_input = QLineEdit()
        self._top_input.setValidator(QDoubleValidator())
        self._top_input.textChanged.connect(self._on_logicle_changed)
        form_logicle.addRow("Top (T):", self._top_input)
        
        # Width Basis (W) slider
        self._slider_w, self._lbl_w = self._add_slider_row(
            form_logicle, "Width Basis (W):", 0, 50, self._on_w_slider
        )
        
        # Positive Decades (M) slider
        self._slider_m, self._lbl_m = self._add_slider_row(
            form_logicle, "Positive (M):", 20, 60, self._on_m_slider
        )
        
        # Extra Negative Decades (A) slider
        self._slider_a, self._lbl_a = self._add_slider_row(
            form_logicle, "Extra Negative (A):", 0, 30, self._on_a_slider
        )
        
        logicle_layout.addLayout(form_logicle)
        layout.addWidget(self._logicle_box)
        
        layout.addStretch()

    def _add_slider_row(
        self, form: QFormLayout, label: str, min_val: int, max_val: int, callback
    ) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.valueChanged.connect(callback)
        
        val_label = QLabel("0.0")
        val_label.setFixedWidth(30)
        
        hbox = QHBoxLayout()
        hbox.addWidget(slider)
        hbox.addWidget(val_label)
        
        form.addRow(label, hbox)
        return slider, val_label

    def _add_separator(self, layout: QVBoxLayout) -> None:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        layout.addWidget(sep)

    def _style_button(self, btn: QPushButton) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_MEDIUM}; color: {Colors.FG_PRIMARY};"
            f" border: 1px solid {Colors.BORDER}; border-radius: 4px;"
            f" padding: 4px 8px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST}; }}"
        )

    # ── State Sync ────────────────────────────────────────────────────

    def _load_from_scale(self) -> None:
        self._updating_ui = True
        
        idx = {
            TransformType.LINEAR: 0,
            TransformType.LOG: 1,
            TransformType.BIEXPONENTIAL: 2,
        }.get(self._scale.transform_type, 0)
        self._type_group.button(idx).setChecked(True)
        
        if self._scale.min_val is not None:
            self._min_input.setText(f"{self._scale.min_val:.1f}")
        else:
            self._min_input.setText("")
            
        if self._scale.max_val is not None:
            self._max_input.setText(f"{self._scale.max_val:.1f}")
        else:
            self._max_input.setText("")

        self._top_input.setText(str(self._scale.logicle_t))
        
        self._slider_w.setValue(int(self._scale.logicle_w * 10))
        self._lbl_w.setText(f"{self._scale.logicle_w:.1f}")
        
        self._slider_m.setValue(int(self._scale.logicle_m * 10))
        self._lbl_m.setText(f"{self._scale.logicle_m:.1f}")
        
        self._slider_a.setValue(int(self._scale.logicle_a * 10))
        self._lbl_a.setText(f"{self._scale.logicle_a:.1f}")
        
        self._logicle_box.setVisible(self._scale.transform_type == TransformType.BIEXPONENTIAL)
        
        self._updating_ui = False

    def _emit_change(self) -> None:
        if not self._updating_ui:
            self.scale_changed.emit()

    # ── Event Handlers ────────────────────────────────────────────────

    def _on_type_changed(self, btn_id: int) -> None:
        types = {
            0: TransformType.LINEAR,
            1: TransformType.LOG,
            2: TransformType.BIEXPONENTIAL,
        }
        self._scale.transform_type = types[btn_id]
        self._logicle_box.setVisible(btn_id == 2)
        self._emit_change()

    def _on_auto_range(self) -> None:
        rng = self._auto_range_callback()
        if rng:
            self._scale.min_val = rng[0]
            self._scale.max_val = rng[1]
            self._load_from_scale()
            self._emit_change()

    def _on_limits_changed(self) -> None:
        if self._updating_ui:
            return
            
        t_min = self._min_input.text()
        t_max = self._max_input.text()
        
        try:
            self._scale.min_val = float(t_min) if t_min else None
        except ValueError:
            pass
            
        try:
            self._scale.max_val = float(t_max) if t_max else None
        except ValueError:
            pass
            
        self._emit_change()

    def _adjust_limit(self, limit_type: str, direction: int) -> None:
        if self._scale.min_val is None or self._scale.max_val is None:
            self._on_auto_range()
            return

        current_range = self._scale.max_val - self._scale.min_val
        if current_range <= 0:
            return
            
        factor = 0.1 * direction
        delta = current_range * factor
        
        if limit_type == "min":
            self._scale.min_val -= delta
        else:
            self._scale.max_val += delta
            
        self._load_from_scale()
        self._emit_change()

    def _on_logicle_changed(self) -> None:
        if self._updating_ui:
            return
        t_val = self._top_input.text()
        try:
            self._scale.logicle_t = float(t_val)
            self._emit_change()
        except ValueError:
            pass

    def _on_w_slider(self, val: int) -> None:
        float_val = val / 10.0
        self._lbl_w.setText(f"{float_val:.1f}")
        if not self._updating_ui:
            self._scale.logicle_w = float_val
            self._emit_change()

    def _on_m_slider(self, val: int) -> None:
        float_val = val / 10.0
        self._lbl_m.setText(f"{float_val:.1f}")
        if not self._updating_ui:
            self._scale.logicle_m = float_val
            self._emit_change()

    def _on_a_slider(self, val: int) -> None:
        float_val = val / 10.0
        self._lbl_a.setText(f"{float_val:.1f}")
        if not self._updating_ui:
            self._scale.logicle_a = float_val
            self._emit_change()


class TransformDialog(QDialog):
    """Dialog housing multi-axis scaling configuration panels.
    
    Signals:
        scale_changed(str, AxisScale): emitted when either axis is modified locally.
        apply_to_all_requested(str, AxisScale): emitted when user hits Apply to All perfectly.
    """

    scale_changed = pyqtSignal(str, object)  # axis: 'x' or 'y', AxisScale
    apply_to_all_requested = pyqtSignal(str, object)  # axis: 'x' or 'y', AxisScale

    def __init__(
        self,
        x_name: str,
        y_name: str,
        x_scale: AxisScale,
        y_scale: AxisScale,
        auto_range_x_callback: Callable[[], tuple[float, float]],
        auto_range_y_callback: Callable[[], tuple[float, float]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Axis Scaling & Transforms")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)
        self.resize(380, 520)
        self.setStyleSheet(
            f"QDialog {{ background: {Colors.BG_DARKEST}; }}"
            f"QTabWidget::pane {{ border: 1px solid {Colors.BORDER}; background: {Colors.BG_DARK}; border-radius: 4px; }}"
            f"QTabBar::tab {{ background: {Colors.BG_MEDIUM}; color: {Colors.FG_SECONDARY}; padding: 6px 12px; }}"
            f"QTabBar::tab:selected {{ background: {Colors.BG_DARK}; color: {Colors.FG_PRIMARY}; border-top: 2px solid {Colors.ACCENT_PRIMARY}; }}"
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        self._tabs = QTabWidget()
        
        self._x_panel = AxisTransformPanel(x_name, x_scale, auto_range_x_callback, self)
        self._y_panel = AxisTransformPanel(y_name, y_scale, auto_range_y_callback, self)
        
        self._x_panel.scale_changed.connect(lambda: self.scale_changed.emit('x', self._x_panel.scale))
        self._y_panel.scale_changed.connect(lambda: self.scale_changed.emit('y', self._y_panel.scale))
        
        self._tabs.addTab(self._x_panel, f"X-Axis: {x_name}")
        self._tabs.addTab(self._y_panel, f"Y-Axis: {y_name}")
        layout.addWidget(self._tabs)
        
        # ── Apply to All ──────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        layout.addWidget(sep)
        
        lbl_hint = QLabel("Note: Scale changes instantly update the active plot.")
        lbl_hint.setStyleSheet(f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_SMALL}px; font-style: italic;")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_hint)
        
        btn_apply = QPushButton("Sync Active Tab to Entire Group")
        btn_apply.setToolTip("Pushes the currently active tab's settings to ALL other samples.")
        btn_apply.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST};"
            f" border: none; border-radius: 4px; padding: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #58a6ff; }}"
        )
        btn_apply.clicked.connect(self._on_apply_all)
        layout.addWidget(btn_apply)

    @property
    def x_scale(self) -> AxisScale:
        return self._x_panel.scale

    @property
    def y_scale(self) -> AxisScale:
        return self._y_panel.scale

    def _on_apply_all(self) -> None:
        active_idx = self._tabs.currentIndex()
        if active_idx == 0:
            self.apply_to_all_requested.emit('x', self.x_scale)
        else:
            self.apply_to_all_requested.emit('y', self.y_scale)
