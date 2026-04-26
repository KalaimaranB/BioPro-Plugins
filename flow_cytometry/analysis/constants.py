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
