"""Constants for the Flow Cytometry module."""

# ── Group Preview / Thumbnail Rendering ──────────────────────────────
# Default number of events for main plot (Optimized mode)
MAIN_PLOT_MAX_EVENTS_OPTIMIZED = 100_000

# Default number of events for thumbnails (Single pass)
PREVIEW_LIMIT_DEFAULT = 100_000

# Visual size of the thumbnail in pixels (width, height)
PREVIEW_THUMBNAIL_SIZE = (160, 160)

# Colors for the preview
PREVIEW_GATE_EDGE_COLOR = "#000000"  # Black as requested
PREVIEW_GATE_LINEWIDTH = 1.2
PREVIEW_BG_COLOR = "#FFFFFF"
PREVIEW_THROTTLE_MS = 300 # Throttle real-time previews to ~3 FPS for stability

# ── Rendering Constraints ────────────────────────────────────────────
DEFAULT_NBINS_MIN = 512
DEFAULT_NBINS_MAX = 8192
NBINS_SCALING_FACTOR = 1.5
SIGMA_MIN = 0.1
SIGMA_SCALING_FACTOR = 2.2

DENSITY_THRESHOLD_MIN = 0.05
DENSITY_THRESHOLD_PCT = 0.02

VIBRANCY_MIN = 0.15
VIBRANCY_RANGE = 0.85

DEFAULT_DENSITY_FACTOR = 0.1
PSEUDOCOLOR_MAX_EVENTS = 150_000

# ── Overlay Colors ───────────────────────────────────────────────────
OVERLAY_COLORS = {
    "default": "#000000",   # Black
    "selected": "#2188FF",  # GitHub Blue for selection
    "inactive": "#888888",  # Gray
}

# ── Logicle Defaults ─────────────────────────────────────────────────
LOGICLE_T_DEFAULT = 262144.0
LOGICLE_W_DEFAULT = 1.0
LOGICLE_M_DEFAULT = 4.5
LOGICLE_A_DEFAULT = 0.0
