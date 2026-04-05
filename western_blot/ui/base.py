"""Wizard infrastructure — step base class and panel shell.

Every analysis wizard in BioPro is built from the same two primitives:

``WizardStep``
    A self-contained unit of UI + logic for one stage of analysis.
    Subclasses override :meth:`build_page` to create their widgets and
    :meth:`on_next` to run their analysis action when the user advances.

``WizardPanel``
    A thin runtime that holds an ordered list of ``WizardStep`` objects,
    renders their pages in a ``FadingStackedWidget``, drives the
    ``StepIndicator``, and owns Back / Next navigation.

Adding a new step (e.g. a Ponceau stain step) means:
    1. Create a ``WizardStep`` subclass in ``biopro/ui/wizard/steps/``.
    2. Pass an instance to ``WizardPanel`` at construction time.
    That's it — no index arithmetic, no ``if step == 3`` scattered around.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts

logger = logging.getLogger(__name__)


# ── Step indicator ────────────────────────────────────────────────────────────

class StepIndicator(QWidget):
    """Vertical stepper — numbered circles with full labels beside them."""

    step_clicked = pyqtSignal(int)  # <--- NEW: Emit when a user clicks a step

    def __init__(self, steps: list[str], parent=None) -> None:
        super().__init__(parent)
        self._steps = steps
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._circles: list[QLabel] = []
        self._texts: list[QLabel] = []
        self._build()
        self.set_current(0)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        for i, label in enumerate(self._steps):
            # --- NEW: Clickable Row Wrapper ---
            row_widget = QWidget()
            row_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            row_widget.mousePressEvent = lambda e, idx=i: self.step_clicked.emit(idx)

            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            # ----------------------------------

            circle = QLabel(str(i + 1))
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            circle.setFixedSize(22, 22)

            text = QLabel(label)
            text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            row.addWidget(circle)
            row.addWidget(text, stretch=1)

            self._circles.append(circle)
            self._texts.append(text)

            layout.addWidget(row_widget)  # Add the clickable widget to the layout

            # Thin connector line between steps
            if i < len(self._steps) - 1:
                line_wrap = QHBoxLayout()
                line_wrap.setContentsMargins(10, 0, 0, 0)
                connector = QLabel()
                connector.setFixedSize(2, 8)
                connector.setStyleSheet(
                    f"background: {Colors.BORDER}; border-radius: 1px;"
                )
                line_wrap.addWidget(connector)
                line_wrap.addStretch()
                layout.addLayout(line_wrap)

    @staticmethod
    def _circle_css(active: bool, done: bool) -> str:
        if done:
            return (
                f"background: {Colors.SUCCESS}; color: {Colors.BG_DARKEST};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700; border: none;"
            )
        if active:
            return (
                f"background: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST};"
                f" border-radius: 12px; font-size: 11px; font-weight: 700; border: none;"
            )
        return (
            f"background: {Colors.BG_MEDIUM}; color: {Colors.FG_DISABLED};"
            f" border-radius: 12px; font-size: 11px; font-weight: 600;"
            f" border: 1px solid {Colors.BORDER};"
        )

    def set_current(self, idx: int) -> None:
        """Update visual state for the given step index."""
        for i, (circle, text) in enumerate(zip(self._circles, self._texts)):
            if i < idx:
                circle.setText("✓")
                circle.setStyleSheet(self._circle_css(False, True))
                text.setStyleSheet(
                    f"font-size: {Fonts.SIZE_SMALL}px; color: {Colors.SUCCESS};"
                    f" background: transparent;"
                )
            elif i == idx:
                circle.setText(str(i + 1))
                circle.setStyleSheet(self._circle_css(True, False))
                text.setStyleSheet(
                    f"font-size: {Fonts.SIZE_SMALL}px; font-weight: 700;"
                    f" color: {Colors.ACCENT_PRIMARY}; background: transparent;"
                )
            else:
                circle.setText(str(i + 1))
                circle.setStyleSheet(self._circle_css(False, False))
                text.setStyleSheet(
                    f"font-size: {Fonts.SIZE_SMALL}px; color: {Colors.FG_DISABLED};"
                    f" background: transparent;"
                )
        # Resize to fit content after rebuild
        self.adjustSize()


# ── Fading stacked widget ─────────────────────────────────────────────────────

class FadingStackedWidget(QStackedWidget):
    """QStackedWidget with a smooth cross-fade transition between pages."""

    def __init__(self, parent=None, fade_ms: int = 300) -> None:
        super().__init__(parent)
        self.fade_ms = fade_ms

    def sizeHint(self) -> QSize:
        # Modest hint so the parent layout never over-allocates height and
        # pushes the Back/Next buttons off screen.
        return QSize(300, 200)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 120)

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return
        current = self.currentWidget()
        nxt = self.widget(index)
        if current is None or nxt is None:
            super().setCurrentIndex(index)
            return

        effect = QGraphicsOpacityEffect(nxt)
        nxt.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        super().setCurrentIndex(index)

        self._anim = QPropertyAnimation(effect, b"opacity")
        self._anim.setDuration(self.fade_ms)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.finished.connect(lambda: nxt.setGraphicsEffect(None))
        self._anim.start()


# ── WizardStep abstract base ──────────────────────────────────────────────────

class WizardStep(ABC):
    """Abstract base for a single wizard step.

    Each step owns:
    - Its display label (shown in ``StepIndicator``).
    - Its page widget (built once by :meth:`build_page`).
    - Its action logic (:meth:`on_next`).

    Steps communicate with the rest of the UI exclusively through the
    ``panel`` reference passed to :meth:`build_page`.  They never hold
    a direct reference to ``WizardPanel`` — they receive it so they can
    emit signals via ``panel.status_message.emit(...)`` etc.

    Attributes:
        label:       Short display name shown in the step indicator.
        is_terminal: If True the wizard shows "Done ✓" instead of "Next →"
                     and navigation stops here.
    """

    label: str = "Step"
    is_terminal: bool = False

    @abstractmethod
    def build_page(self, panel: "WizardPanel") -> QWidget:
        """Create and return the page widget for this step.

        Called once during ``WizardPanel`` construction.  Store any
        widget references you need later as instance attributes here.

        Args:
            panel: The parent ``WizardPanel``.  Use it to emit signals.

        Returns:
            The page widget to display when this step is active.
        """

    def on_enter(self) -> None:
        """Called when this step becomes the active step.

        Override to refresh UI state, e.g. update a lane-count spinbox
        to reflect a previously auto-detected value.  Default is no-op.
        """

    @abstractmethod
    def on_next(self, panel: "WizardPanel") -> bool:
        """Run this step's analysis action when the user clicks Next.

        Args:
            panel: The parent ``WizardPanel``.

        Returns:
            True  — navigation may proceed to the next step.
            False — block navigation (e.g. no image loaded yet).
        """

    @staticmethod
    def _scroll(page: QWidget) -> QScrollArea:
        """Wrap *page* in a frameless, resizable scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _row(
        label_text: str,
        widget: QWidget,
        *,
        label_width: int = 130,
    ) -> QHBoxLayout:
        """Return a QHBoxLayout with a fixed-width label and a widget."""
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(label_width)
        row.addWidget(lbl)
        row.addWidget(widget)
        return row


# ── WizardPanel ───────────────────────────────────────────────────────────────

class WizardPanel(QWidget):
    """Thin wizard shell that drives a list of ``WizardStep`` objects.

    Responsibilities:
    - Build the ``StepIndicator`` from the step labels.
    - Instantiate each step's page widget into a ``FadingStackedWidget``.
    - Own Back / Next navigation, delegating action logic to steps.
    - Expose signals so ``MainWindow`` can react to analysis events.

    It deliberately contains *no analysis logic* — that all lives in the
    individual step classes.

    Signals:
        status_message:        Short string for the status bar.
        image_changed:         Emitted when processed image changes.
        lanes_detected:        Emitted when lanes are detected.
        bands_detected:        Emitted when bands are detected (bands, lanes).
        results_ready:         Emitted when densitometry is computed.
        selected_bands_changed: Emitted when band selection changes.
        peak_picking_enabled:  Emitted when manual peak pick mode toggles.
        crop_mode_toggled:     Emitted when crop draw mode toggles.
        profile_hovered:       Emitted when profile dialog mouse moves (lane, y).
    """

    # ── Signals (identical names to old WesternBlotPanel for drop-in compat) ──
    status_message = pyqtSignal(str)
    image_changed = pyqtSignal(object)
    lanes_detected = pyqtSignal(object)
    bands_detected = pyqtSignal(object, object)
    results_ready = pyqtSignal(object)
    selected_bands_changed = pyqtSignal(list)
    peak_picking_enabled = pyqtSignal(bool)
    crop_mode_toggled = pyqtSignal(bool)
    profile_hovered = pyqtSignal(int, float)
    state_changed = pyqtSignal()

    def __init__(self, steps: list[WizardStep], title: str = "", parent=None) -> None:
        """
        Args:
            steps: Ordered list of steps to execute.  Built externally so
                   the caller decides which steps (and how many) are active
                   for this run — e.g. with or without Ponceau.
            title: Optional panel title displayed above the step indicator.
        """
        super().__init__(parent)
        self._steps = steps
        self._idx = 0
        self._max_idx = 0
        self._canvas = None

        self._setup_ui(title)

        # Give each step a chance to set up after the panel exists
        for step in self._steps:
            if hasattr(step, "on_panel_ready"):
                step.on_panel_ready(self)

    # ── Public API (used by MainWindow and step classes) ──────────────

    def set_canvas(self, canvas) -> None:
        """Pass the image canvas reference to steps that need it."""
        self._canvas = canvas
        for step in self._steps:
            if hasattr(step, "set_canvas"):
                step.set_canvas(canvas)
        # If the current step uses lane edit mode, re-enter to set it up
        cur = self._steps[self._idx]
        if hasattr(cur, "on_enter"):
            cur.on_enter()

    @property
    def canvas(self):
        return self._canvas

    @property
    def current_step(self) -> WizardStep:
        return self._steps[self._idx]

    # ── Slots wired by MainWindow ─────────────────────────────────────

    def on_band_clicked(self, band) -> None:
        step = self._steps[self._idx]
        if hasattr(step, "on_band_clicked"):
            step.on_band_clicked(band, self)

    def on_peak_pick_requested(self, x: float, y: float) -> None:
        step = self._steps[self._idx]
        if hasattr(step, "on_peak_pick_requested"):
            step.on_peak_pick_requested(x, y, self)

    def on_crop_requested(self, rect) -> None:
        step = self._steps[self._idx]
        if hasattr(step, "on_crop_requested"):
            step.on_crop_requested(rect, self)

    # ── UI construction ───────────────────────────────────────────────

    def _setup_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Title
        if title:
            lbl = QLabel(f"🧬  {title}")
            lbl.setObjectName("stepTitle")
            lbl.setMinimumHeight(28)
            layout.addWidget(lbl)

        # Step indicator — built from step labels
        labels = [s.label for s in self._steps]
        self._indicator = StepIndicator(labels)
        self._indicator.step_clicked.connect(self.go_to_step)
        layout.addWidget(self._indicator)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        layout.addWidget(sep)

        # Pages
        self._pages = FadingStackedWidget(fade_ms=350)
        self._pages.setMinimumHeight(120)
        for step in self._steps:
            self._pages.addWidget(step.build_page(self))
        layout.addWidget(self._pages, stretch=1)

        # Navigation
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 6, 0, 0)
        nav.setSpacing(8)

        self._btn_back = QPushButton("← Back")
        self._btn_back.setMinimumHeight(36)
        self._btn_back.setMinimumWidth(80)

        self._btn_next = QPushButton("Next →")
        self._btn_next.setStyleSheet(
            f"QPushButton {{ background-color: {Colors.ACCENT_PRIMARY};"
            f" color: {Colors.BG_DARKEST}; border: none; border-radius: 6px;"
            f" padding: 8px 16px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {Colors.ACCENT_PRIMARY_HOVER}; }}"
            f"QPushButton:pressed {{ background-color: {Colors.ACCENT_PRIMARY_PRESSED}; }}"
            f"QPushButton:disabled {{ background-color: {Colors.BG_MEDIUM};"
            f" color: {Colors.FG_DISABLED}; }}"
        )
        self._btn_next.setMinimumHeight(36)
        self._btn_next.setMinimumWidth(90)

        self._btn_back.clicked.connect(self._go_back)
        self._btn_next.clicked.connect(self._go_next)

        nav.addWidget(self._btn_back)
        nav.addStretch()
        nav.addWidget(self._btn_next)
        layout.addLayout(nav)

        self._refresh_nav()

    # ── Navigation ────────────────────────────────────────────────────

    def _go_next(self) -> None:
        step = self._steps[self._idx]
        if not step.on_next(self):
            return  # step blocked navigation

        if hasattr(step, "on_leave"):
            step.on_leave()

        if self._idx < len(self._steps) - 1:
            self._idx += 1
            self._max_idx = max(self._max_idx, self._idx)  # <--- NEW: Update max reached!

            self._pages.setCurrentIndex(self._idx)
            self._indicator.set_current(self._idx)
            self._refresh_nav()
            self._steps[self._idx].on_enter()

    def _go_back(self) -> None:
        if self._idx > 0:
            # Notify current step it is losing focus
            cur = self._steps[self._idx]
            if hasattr(cur, "on_leave"):
                cur.on_leave()
            self._idx -= 1
            self._pages.setCurrentIndex(self._idx)
            self._indicator.set_current(self._idx)
            self._refresh_nav()
            self._steps[self._idx].on_enter()

    def _refresh_nav(self) -> None:
        self._btn_back.setEnabled(self._idx > 0)
        if self._steps[self._idx].is_terminal:
            self._btn_next.setText("✅ Done")
            self._btn_next.setEnabled(False)
        else:
            self._btn_next.setText("Next →")
            self._btn_next.setEnabled(True)

    def go_to_step(self, target_idx: int) -> None:
        """Jump to a specific step, used by Time Machine and clickable indicator."""
        # Block jumping ahead of what the user has legitimately reached
        if target_idx < 0 or target_idx > self._max_idx:
            return
        if target_idx == self._idx:
            return

        # Notify current step it is losing focus
        cur = self._steps[self._idx]
        if hasattr(cur, "on_leave"):
            cur.on_leave()

        self._idx = target_idx
        self._pages.setCurrentIndex(self._idx)
        self._indicator.set_current(self._idx)
        self._refresh_nav()
        self._steps[self._idx].on_enter()