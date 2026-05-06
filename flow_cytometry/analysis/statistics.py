"""Statistical computations for flow cytometry populations.

Provides a unified interface for computing standard flow cytometry
statistics (Mean, Median, MFI, CV, %Parent, etc.) on gated populations.

All functions operate on pandas DataFrames — no GUI dependencies.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = get_logger(__name__, "flow_cytometry")


class StatType(Enum):
    """Supported statistic types."""

    COUNT = "count"
    MEAN = "mean"
    MEDIAN = "median"
    GEOMETRIC_MEAN = "geometric_mean"
    MODE = "mode"
    SD = "sd"
    CV = "cv"
    MFI = "mfi"                           # Median Fluorescence Intensity
    PERCENT_PARENT = "percent_parent"
    PERCENT_GRANDPARENT = "percent_grandparent"
    PERCENT_TOTAL = "percent_total"
    MIN = "min"
    MAX = "max"


@dataclass
class StatDefinition:
    """Specification for a single statistic to compute.

    Attributes:
        stat_type:  The type of statistic.
        parameter:  Channel/parameter name to compute on (None for Count).
        population: Gate name or ID this stat applies to.
    """

    stat_type: StatType
    parameter: Optional[str] = None
    population: Optional[str] = None


@dataclass
class StatResult:
    """Result of a single statistic computation.

    Attributes:
        definition: The :class:`StatDefinition` that produced this result.
        value:      The computed value (float or int).
        formatted:  Human-readable formatted string.
    """

    definition: StatDefinition
    value: float
    formatted: str = ""

    def __post_init__(self) -> None:
        if not self.formatted:
            if self.definition.stat_type == StatType.COUNT:
                self.formatted = f"{int(self.value):,}"
            elif self.definition.stat_type in (
                StatType.PERCENT_PARENT,
                StatType.PERCENT_GRANDPARENT,
                StatType.PERCENT_TOTAL,
                StatType.CV,
            ):
                self.formatted = f"{self.value:.2f}%"
            else:
                self.formatted = f"{self.value:.2f}"


def compute_statistic(
    events: pd.DataFrame,
    param: Optional[str],
    stat_type: StatType,
    *,
    parent_count: Optional[int] = None,
    grandparent_count: Optional[int] = None,
    total_count: Optional[int] = None,
) -> float:
    """Compute a single statistic on a population.

    Args:
        events:            Gated event DataFrame.
        param:             Channel name (ignored for COUNT and % stats).
        stat_type:         Which statistic to compute.
        parent_count:      Event count of the parent population
                           (required for PERCENT_PARENT).
        grandparent_count: Event count of grandparent (for PERCENT_GRANDPARENT).
        total_count:       Total ungated event count (for PERCENT_TOTAL).

    Returns:
        The computed statistic as a float.

    Raises:
        ValueError: If the parameter is missing from the DataFrame.
    """
    n = len(events)

    if stat_type == StatType.COUNT:
        return float(n)

    if stat_type == StatType.PERCENT_PARENT:
        if parent_count and parent_count > 0:
            return (n / parent_count) * 100.0
        return 0.0

    if stat_type == StatType.PERCENT_GRANDPARENT:
        if grandparent_count and grandparent_count > 0:
            return (n / grandparent_count) * 100.0
        return 0.0

    if stat_type == StatType.PERCENT_TOTAL:
        if total_count and total_count > 0:
            return (n / total_count) * 100.0
        return 0.0

    # Parameter-dependent stats
    if param is None:
        raise ValueError(f"Parameter required for {stat_type.value}")
    if param not in events.columns:
        raise ValueError(f"Parameter '{param}' not found in events")

    values = events[param].dropna().values

    if len(values) == 0:
        return 0.0

    if stat_type == StatType.MEAN:
        return float(np.mean(values))
    elif stat_type == StatType.MEDIAN or stat_type == StatType.MFI:
        return float(np.median(values))
    elif stat_type == StatType.GEOMETRIC_MEAN:
        positive = values[values > 0]
        if len(positive) == 0:
            return 0.0
        return float(np.exp(np.mean(np.log(positive))))
    elif stat_type == StatType.MODE:
        # Approximate mode using histogram
        hist, bin_edges = np.histogram(values, bins="auto")
        max_idx = np.argmax(hist)
        return float((bin_edges[max_idx] + bin_edges[max_idx + 1]) / 2.0)
    elif stat_type == StatType.SD:
        return float(np.std(values, ddof=1))
    elif stat_type == StatType.CV:
        mean = np.mean(values)
        if mean == 0:
            return 0.0
        return float((np.std(values, ddof=1) / abs(mean)) * 100.0)
    elif stat_type == StatType.MIN:
        return float(np.min(values))
    elif stat_type == StatType.MAX:
        return float(np.max(values))
    else:
        raise ValueError(f"Unsupported stat type: {stat_type}")


def compute_population_stats(
    events: pd.DataFrame,
    definitions: list[StatDefinition],
    *,
    parent_count: Optional[int] = None,
    grandparent_count: Optional[int] = None,
    total_count: Optional[int] = None,
) -> list[StatResult]:
    """Compute multiple statistics on a population.

    Args:
        events:      Gated event DataFrame.
        definitions: List of :class:`StatDefinition` to compute.
        parent_count, grandparent_count, total_count:
                     Counts for percentage calculations.

    Returns:
        List of :class:`StatResult` instances.
    """
    results = []
    for defn in definitions:
        try:
            value = compute_statistic(
                events, defn.parameter, defn.stat_type,
                parent_count=parent_count,
                grandparent_count=grandparent_count,
                total_count=total_count,
            )
            results.append(StatResult(definition=defn, value=value))
        except (ValueError, KeyError) as exc:
            logger.warning("Stat computation failed for %s: %s", defn, exc)
            results.append(StatResult(
                definition=defn, value=0.0,
                formatted=f"Error: {exc}",
            ))
    return results
