"""Quick Start overlay — optional guided onboarding.

A non-blocking overlay that helps first-time users get started.
Can be dismissed at any time and re-opened from the Help menu.
Not a wizard — the workspace is fully interactive underneath.

Steps:
1. Choose or create a workflow template
2. Load FCS files and map to sample slots
3. Calculate and apply compensation
4. Draw gates (with FMO auto-suggest)
5. View results and export
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from biopro.ui.theme import Colors, Fonts
from biopro.shared.ui.ui_components import PrimaryButton, SecondaryButton

logger = get_logger(__name__, "flow_cytometry")


_STEPS = [
    {
        "title": "1. Choose a Workflow Template",
        "description": (
            "Select a pre-built workflow (FMO, Viability, Custom) "
            "or create your own.  Templates define which markers, "
            "tubes, and controls you need."
        ),
        "icon": "📋",
    },
    {
        "title": "2. Load & Map Samples",
        "description": (
            "Drag-and-drop your FCS files and assign each to its "
            "role in the workflow (Unstained, Single Stain, FMO, "
            "Full Panel).  Missing controls are highlighted."
        ),
        "icon": "📂",
    },
    {
        "title": "3. Compensate",
        "description": (
            "Auto-compute the spillover matrix from your single-stain "
            "controls, or import one from your cytometer."
        ),
        "icon": "🔬",
    },
    {
        "title": "4. Gate Your Populations",
        "description": (
            "Draw gates interactively or use FMO Auto-Gate for "
            "automatic boundary detection.  Enable Adaptive mode "
            "to auto-adjust gates across samples."
        ),
        "icon": "🎯",
    },
    {
        "title": "5. Analyze & Export",
        "description": (
            "View population statistics, generate tabular reports, "
            "and export publication-ready figures."
        ),
        "icon": "📊",
    },
]


class QuickStart(QFrame):
    """Dismissible onboarding overlay with step-by-step guidance.

    Signals:
        dismissed: Emitted when the user closes the overlay.
    """

    dismissed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_step = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QuickStart {{ background: {Colors.BG_DARK};"
            f" border: 1px solid {Colors.BORDER};"
            f" border-radius: 12px; }}"
        )
        self.setObjectName("QuickStart")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("🚀  Quick Start")
        title.setStyleSheet(
            f"color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_LARGE}px;"
            f" font-weight: 700; background: transparent;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        btn_dismiss = QPushButton("✕")
        btn_dismiss.setFixedSize(28, 28)
        btn_dismiss.setStyleSheet(
            f"QPushButton {{ background: transparent;"
            f" color: {Colors.FG_SECONDARY}; border: none;"
            f" font-size: 16px; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.FG_PRIMARY}; }}"
        )
        btn_dismiss.clicked.connect(self._on_dismiss)
        header_row.addWidget(btn_dismiss)
        layout.addLayout(header_row)

        # Step content area
        self._step_icon = QLabel()
        self._step_icon.setStyleSheet(
            f"font-size: 32px; background: transparent;"
        )
        self._step_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._step_icon)

        self._step_title = QLabel()
        self._step_title.setStyleSheet(
            f"color: {Colors.ACCENT_PRIMARY}; font-size: {Fonts.SIZE_NORMAL}px;"
            f" font-weight: 700; background: transparent;"
        )
        self._step_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._step_title)

        self._step_desc = QLabel()
        self._step_desc.setWordWrap(True)
        self._step_desc.setStyleSheet(
            f"color: {Colors.FG_SECONDARY}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; line-height: 1.5;"
        )
        self._step_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._step_desc)

        # Navigation
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self._btn_prev = SecondaryButton("← Previous")
        self._btn_prev.clicked.connect(self._go_prev)
        nav_row.addWidget(self._btn_prev)

        nav_row.addStretch()

        # Step indicator dots
        self._dots_label = QLabel()
        self._dots_label.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: 14px;"
            f" background: transparent; letter-spacing: 4px;"
        )
        self._dots_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self._dots_label)

        nav_row.addStretch()

        self._btn_next = PrimaryButton("Next →")
        self._btn_next.clicked.connect(self._go_next)
        nav_row.addWidget(self._btn_next)

        layout.addLayout(nav_row)

        # Show first step
        self._update_step()

    def _update_step(self) -> None:
        """Refresh the display for the current step."""
        step = _STEPS[self._current_step]
        self._step_icon.setText(step["icon"])
        self._step_title.setText(step["title"])
        self._step_desc.setText(step["description"])

        # Navigation state
        self._btn_prev.setEnabled(self._current_step > 0)
        is_last = self._current_step >= len(_STEPS) - 1
        self._btn_next.setText("Get Started! ✨" if is_last else "Next →")

        # Dots
        dots = ""
        for i in range(len(_STEPS)):
            dots += "●" if i == self._current_step else "○"
        self._dots_label.setText(dots)

    def _go_next(self) -> None:
        if self._current_step >= len(_STEPS) - 1:
            self._on_dismiss()
        else:
            self._current_step += 1
            self._update_step()

    def _go_prev(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._update_step()

    def _on_dismiss(self) -> None:
        self.dismissed.emit()
        self.hide()
