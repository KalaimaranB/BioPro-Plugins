"""Shared UI utilities for render settings panels."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox, QSpinBox, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from biopro.ui.theme import Colors, Fonts


# ── Color picker button ───────────────────────────────────────────────────────

class ColorPickerButton(QPushButton):
    """A button that shows the current color and opens QColorDialog on click."""

    color_changed = pyqtSignal(str)  # emits hex string

    def __init__(self, initial_color: str = "#2196F3", parent=None):
        super().__init__(parent)
        self._color = initial_color
        self.setFixedSize(36, 24)
        self._refresh_style()
        self.clicked.connect(self._open_picker)

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, hex_color: str) -> None:
        self._color = hex_color
        self._refresh_style()

    def _refresh_style(self) -> None:
        self.setStyleSheet(
            f"QPushButton {{ background: {self._color}; border: 1px solid {Colors.BORDER};"
            f" border-radius: 3px; }}"
            f"QPushButton:hover {{ border: 1px solid {Colors.ACCENT_PRIMARY}; }}"
        )

    def _open_picker(self) -> None:
        from PyQt6.QtWidgets import QColorDialog
        dlg = QColorDialog(QColor(self._color), self)
        if dlg.exec():
            new_color = dlg.selectedColor().name()
            self.set_color(new_color)
            self.color_changed.emit(new_color)


# ── Slider + spin helper ──────────────────────────────────────────────────────

def make_float_row(
    form_layout,
    label: str,
    tooltip: str,
    min_val: float,
    max_val: float,
    step: float,
    current: float,
    precision: int = 100,
) -> QDoubleSpinBox:
    """Add a float slider+spinbox row to a QFormLayout. Returns the spinbox."""
    spin = QDoubleSpinBox()
    spin.setRange(min_val, max_val)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setValue(current)
    spin.setFixedWidth(70)
    spin.setToolTip(tooltip)
    spin.setStyleSheet(f"color: {Colors.FG_PRIMARY}; background: {Colors.BG_MEDIUM};"
                       f" border: 1px solid {Colors.BORDER}; border-radius: 3px;")

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(int(min_val * precision), int(max_val * precision))
    slider.setValue(int(current * precision))
    slider.setToolTip(tooltip)
    slider.valueChanged.connect(lambda v: spin.setValue(v / precision))
    spin.valueChanged.connect(lambda v: slider.setValue(int(v * precision)))

    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.addWidget(slider)
    rl.addWidget(spin)

    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;")
    lbl.setToolTip(tooltip)
    form_layout.addRow(lbl, row)
    return spin


def make_int_row(
    form_layout,
    label: str,
    tooltip: str,
    min_val: int,
    max_val: int,
    step: int,
    current: int,
) -> QSpinBox:
    """Add an int slider+spinbox row to a QFormLayout. Returns the spinbox."""
    spin = QSpinBox()
    spin.setRange(min_val, max_val)
    spin.setSingleStep(step)
    spin.setValue(current)
    spin.setFixedWidth(70)
    spin.setToolTip(tooltip)
    spin.setStyleSheet(f"color: {Colors.FG_PRIMARY}; background: {Colors.BG_MEDIUM};"
                       f" border: 1px solid {Colors.BORDER}; border-radius: 3px;")

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(min_val, max_val)
    slider.setSingleStep(step)
    slider.setValue(current)
    slider.setToolTip(tooltip)
    slider.valueChanged.connect(spin.setValue)
    spin.valueChanged.connect(slider.setValue)

    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.addWidget(slider)
    rl.addWidget(spin)

    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;")
    lbl.setToolTip(tooltip)
    form_layout.addRow(lbl, row)
    return spin


def section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 12px; font-weight: 700; color: {Colors.FG_PRIMARY};"
        f" padding-top: 4px; padding-bottom: 2px;"
    )
    return lbl


PANEL_STYLE = f"background: {Colors.BG_DARKEST};"
