"""FCS file I/O — wraps FlowKit for robust FCS loading.

Uses ``flowkit.Sample`` for FCS 2.0/3.0/3.1 parsing, metadata
extraction, and channel naming.  Falls back to ``fcsparser`` if
FlowKit is unavailable.

Reference:
    FlowKit: https://github.com/whitews/FlowKit
    FCS standard: https://www.isac-net.org/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FCSData:
    """Container for a loaded FCS dataset.

    Attributes:
        file_path:  Path to the source ``.fcs`` file.
        channels:   Ordered list of channel short names (e.g., ``FSC-A``).
        markers:    Ordered list of marker labels (e.g., ``CD4``).
                    May be empty if no staining annotations are present.
        events:     (N, C) DataFrame of raw event data.
        metadata:   FCS keyword dictionary (TEXT segment).
        _fk_sample: The underlying ``flowkit.Sample`` object, if loaded
                    via FlowKit.  Retained for downstream transform
                    and compensation operations.
    """

    file_path: Path
    channels: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    events: Optional[pd.DataFrame] = None
    metadata: dict[str, str] = field(default_factory=dict)
    _fk_sample: object = field(default=None, repr=False)

    @property
    def num_events(self) -> int:
        """Total number of events."""
        return len(self.events) if self.events is not None else 0

    @property
    def num_channels(self) -> int:
        return len(self.channels)


def load_fcs(path: str | Path) -> FCSData:
    """Load an FCS file and return an :class:`FCSData` container.

    Attempts to use ``flowkit.Sample`` first.  If FlowKit is not
    installed, falls back to ``fcsparser``.

    Args:
        path: Path to the ``.fcs`` file.

    Returns:
        A populated :class:`FCSData` with events and metadata.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If both FlowKit and fcsparser are unavailable.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"FCS file not found: {path}")

    # ── Try FlowKit first ────────────────────────────────────────────
    try:
        return _load_with_flowkit(path)
    except ImportError:
        logger.info("FlowKit not available, falling back to fcsparser.")
    except Exception as exc:
        logger.warning("FlowKit failed to load %s: %s", path, exc)

    # ── Fallback: fcsparser ──────────────────────────────────────────
    try:
        return _load_with_fcsparser(path)
    except ImportError:
        raise RuntimeError(
            "Neither flowkit nor fcsparser is installed. "
            "Install at least one: pip install flowkit"
        )


def _load_with_flowkit(path: Path) -> FCSData:
    """Load using flowkit.Sample — the preferred path."""
    import flowkit as fk

    sample = fk.Sample(path)

    # Channel short names (PnN) and marker labels (PnS)
    channel_info = sample.channels
    channels = list(channel_info["pnn"])
    markers = list(channel_info.get("pns", [""]*len(channels)))
    # Replace empty marker strings with empty
    markers = [m if m and m.strip() else "" for m in markers]

    # Raw events as DataFrame
    raw_events = sample.get_events(source="raw")
    events_df = pd.DataFrame(raw_events, columns=channels)

    # Metadata
    metadata = dict(sample.metadata) if hasattr(sample, "metadata") else {}

    logger.info(
        "Loaded %s via FlowKit: %d events × %d channels",
        path.name, len(events_df), len(channels),
    )

    return FCSData(
        file_path=path,
        channels=channels,
        markers=markers,
        events=events_df,
        metadata=metadata,
        _fk_sample=sample,
    )


def _load_with_fcsparser(path: Path) -> FCSData:
    """Fallback loader using fcsparser."""
    import fcsparser

    meta, data = fcsparser.parse(str(path), reformat_meta=True)

    channels = list(data.columns)
    events_df = data.copy()

    # Try to extract marker names from metadata
    markers = []
    for i, ch in enumerate(channels, start=1):
        pns_key = f"$P{i}S"
        marker = meta.get(pns_key, "")
        markers.append(marker)

    logger.info(
        "Loaded %s via fcsparser: %d events × %d channels",
        path.name, len(events_df), len(channels),
    )

    return FCSData(
        file_path=path,
        channels=channels,
        markers=markers,
        events=events_df,
        metadata=meta,
    )


def get_fluorescence_channels(data: FCSData) -> list[str]:
    """Return channel names that are likely fluorescence (not scatter/time).

    Heuristic: exclude names starting with FSC, SSC, Time.

    Args:
        data: A loaded :class:`FCSData`.

    Returns:
        List of fluorescence channel names.
    """
    exclude = ("FSC", "SSC", "Time", "time")
    return [ch for ch in data.channels if not ch.startswith(exclude)]


def get_channel_marker_label(data: FCSData, channel: str) -> str:
    """Return the display label for a channel.

    If a marker is mapped to this channel, returns ``"Marker (Channel)"``,
    otherwise returns just the channel name.

    Args:
        data:    A loaded :class:`FCSData`.
        channel: The channel short name.

    Returns:
        A human-readable label.
    """
    try:
        idx = data.channels.index(channel)
        marker = data.markers[idx] if idx < len(data.markers) else ""
        if marker:
            return f"{marker} ({channel})"
    except ValueError:
        pass
    return channel
