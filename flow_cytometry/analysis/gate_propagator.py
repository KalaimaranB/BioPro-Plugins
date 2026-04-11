"""Gate propagator — background worker for cross-sample gate updates.

When a gate is drawn or modified on one sample, the ``GatePropagator``
re-applies the full gate tree to every other sample in the same group,
recomputing statistics (count, %parent, %total) for each population.

This runs on a ``QThread`` so the UI stays responsive during batch
computation.  A 200ms debounce timer prevents redundant recalculations
while the user is still dragging a gate handle.

Phase 4 deliverable:
    Move a gate on sample A → samples B, C, D update their event counts
    and %parent in the tree and properties panel within ~200ms.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import (
    QMutex,
    QObject,
    QThread,
    QTimer,
    pyqtSignal,
)

import numpy as np
import pandas as pd

from .experiment import Experiment, Sample
from .gating import Gate, GateNode, gate_from_dict
from .state import FlowState

logger = logging.getLogger(__name__)


class _PropagationWorker(QObject):
    """Worker that runs on a background QThread.

    Receives a gate tree snapshot and a list of target samples,
    then re-applies the tree to each sample and emits progress signals.
    """

    # Emitted after each sample finishes (sample_id, stats_dict, new_gate_tree)
    sample_updated = pyqtSignal(str, dict, object)
    # Emitted when all samples are done
    finished = pyqtSignal()
    # Emitted on error
    error = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._gate_tree_dict: Optional[dict] = None
        self._target_samples: list[Sample] = []

    def configure(
        self,
        gate_tree_dict: dict,
        target_samples: list[Sample],
    ) -> None:
        """Set the work payload before starting the thread.

        Args:
            gate_tree_dict: Serialized gate tree from the source sample.
            target_samples: List of samples to propagate to.
        """
        self._gate_tree_dict = gate_tree_dict
        self._target_samples = list(target_samples)

    def run(self) -> None:
        """Execute the propagation — called when the thread starts."""
        if self._gate_tree_dict is None:
            self.finished.emit()
            return

        for sample in self._target_samples:
            try:
                stats, new_tree = self._apply_tree_to_sample(
                    self._gate_tree_dict, sample
                )
                self.sample_updated.emit(sample.sample_id, stats, new_tree)
            except Exception as exc:
                logger.warning(
                    "Propagation failed for '%s': %s",
                    sample.display_name, exc,
                )
                self.error.emit(
                    f"{sample.display_name}: {exc}"
                )

        self.finished.emit()

    def _apply_tree_to_sample(
        self, tree_dict: dict, sample: Sample
    ) -> tuple[dict, GateNode]:
        """Reconstruct and apply the gate tree to a single sample.

        Returns:
            Tuple of ({gate_id: {count, pct...}}, new_GateNode)
        """
        if sample.fcs_data is None or sample.fcs_data.events is None:
            return {}, GateNode()

        events = sample.fcs_data.events
        total_count = len(events)

        # Rebuild the gate tree for this sample detached
        new_tree = GateNode()
        self._rebuild_children(
            tree_dict.get("children", []),
            new_tree,
        )

        # Walk and compute stats
        all_stats: dict[str, dict] = {}
        self._walk_tree(
            new_tree, events, total_count, total_count, all_stats
        )

        return all_stats, new_tree

    def _rebuild_children(
        self, children_dicts: list[dict], parent_node: GateNode
    ) -> None:
        """Recursively rebuild gate children from serialized data."""
        for child_dict in children_dicts:
            gate_data = child_dict.get("gate")
            if gate_data is None:
                continue

            try:
                gate = gate_from_dict(gate_data)
                name = child_dict.get("name", "Unknown")
                negated = child_dict.get("negated", False)
                node_id = child_dict.get("node_id")

                child_node = parent_node.add_child(gate, name=name)
                child_node.negated = negated
                if node_id:
                    child_node.node_id = node_id

                self._rebuild_children(
                    child_dict.get("children", []), child_node
                )
            except (ValueError, KeyError) as exc:
                logger.warning("Failed to deserialize gate during propagation: %s", exc)
                continue

    def _walk_tree(
        self,
        node: GateNode,
        parent_events: pd.DataFrame,
        parent_count: int,
        total_count: int,
        stats_out: dict,
    ) -> None:
        """Depth-first walk computing stats for each gate."""
        for child in node.children:
            if child.gate is None:
                continue

            try:
                # Use node logic which respects negation
                mask = child.gate.contains(parent_events)
                if child.negated:
                    mask = ~mask
                gated = parent_events.loc[mask].copy()
            except (KeyError, ValueError) as exc:
                logger.debug(
                    "Gate '%s' skipped on this sample: %s",
                    child.name, exc,
                )
                child.statistics = {
                    "count": 0, "pct_parent": 0.0, "pct_total": 0.0,
                }
                stats_out[child.node_id] = child.statistics
                continue

            count = len(gated)
            pct_parent = (
                (count / parent_count * 100.0) if parent_count > 0 else 0.0
            )
            pct_total = (
                (count / total_count * 100.0) if total_count > 0 else 0.0
            )

            child.statistics = {
                "count": count,
                "pct_parent": round(pct_parent, 2),
                "pct_total": round(pct_total, 2),
            }
            stats_out[child.node_id] = child.statistics

            self._walk_tree(
                child, gated, count, total_count, stats_out
            )


class GatePropagator(QObject):
    """Debounced gate propagation manager.

    Usage from ``FlowCytometryPanel``::

        propagator = GatePropagator(state)
        gate_controller.propagation_requested.connect(
            propagator.request_propagation
        )
        propagator.sample_updated.connect(sample_tree.update_gate_stats)
        propagator.propagation_complete.connect(on_done)

    Signals:
        sample_updated(sample_id, stats_dict, new_tree):
            Emitted after a single sample's stats are recomputed.
        propagation_complete:
            Emitted when all samples have been updated.
    """

    sample_updated = pyqtSignal(str, dict, object)
    propagation_complete = pyqtSignal()

    DEBOUNCE_MS = 200

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._mutex = QMutex()

        # Debounce timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self._execute_propagation)

        # Pending request
        self._pending_gate_id: Optional[str] = None
        self._pending_source_id: Optional[str] = None

        # Background thread
        self._thread: Optional[QThread] = None
        self._worker: Optional[_PropagationWorker] = None

    def request_propagation(
        self, gate_id: str, source_sample_id: str
    ) -> None:
        """Request gate propagation with debouncing.

        Multiple rapid calls (e.g., during gate dragging) are coalesced
        into a single execution after ``DEBOUNCE_MS`` milliseconds of
        inactivity.

        Args:
            gate_id:           The gate that changed.
            source_sample_id:  The sample the gate was changed on.
        """
        self._mutex.lock()
        self._pending_gate_id = gate_id
        self._pending_source_id = source_sample_id
        self._mutex.unlock()

        # Reset the debounce timer
        self._timer.start()

    def _execute_propagation(self) -> None:
        """Execute the pending propagation (called after debounce)."""
        self._mutex.lock()
        source_id = self._pending_source_id
        self._pending_gate_id = None
        self._pending_source_id = None
        self._mutex.unlock()

        if source_id is None:
            return

        source = self._state.experiment.samples.get(source_id)
        if source is None:
            return

        # Serialize the source gate tree
        tree_dict = source.gate_tree.to_dict()

        # Find target samples (same group, or all if no group)
        targets = self._find_targets(source_id)
        if not targets:
            self.propagation_complete.emit()
            return

        # Stop any previous thread
        self._stop_thread()

        # Create worker + thread
        self._thread = QThread()
        self._worker = _PropagationWorker()
        self._worker.configure(tree_dict, targets)
        self._worker.moveToThread(self._thread)

        # Wire signals
        self._thread.started.connect(self._worker.run)
        self._worker.sample_updated.connect(self._on_sample_updated)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)

        self._thread.start()

        logger.info(
            "Propagating gates from '%s' to %d samples.",
            source.display_name, len(targets),
        )

    def _find_targets(self, source_id: str) -> list[Sample]:
        """Find all target samples for propagation.

        Targets are samples in the same group(s) as the source,
        excluding the source itself.
        """
        source = self._state.experiment.samples.get(source_id)
        if source is None:
            return []

        target_ids: set[str] = set()

        # Check groups
        for group in self._state.experiment.groups.values():
            if source_id in group.sample_ids:
                target_ids.update(group.sample_ids)

        # If not in any group, propagate to all samples
        if not target_ids:
            target_ids = set(self._state.experiment.samples.keys())

        target_ids.discard(source_id)

        return [
            self._state.experiment.samples[sid]
            for sid in target_ids
            if sid in self._state.experiment.samples
            and self._state.experiment.samples[sid].fcs_data is not None
        ]

    def _on_sample_updated(self, sample_id: str, stats: dict, new_tree: GateNode) -> None:
        """Swap the new tree into the sample on the main thread and forward."""
        sample = self._state.experiment.samples.get(sample_id)
        if sample is not None:
            sample.gate_tree = new_tree
        self.sample_updated.emit(sample_id, stats, new_tree)

    def _on_finished(self) -> None:
        """Clean up after propagation completes."""
        self.propagation_complete.emit()
        logger.debug("Gate propagation complete.")

    def _stop_thread(self) -> None:
        """Stop any running propagation thread."""
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)

    def cleanup(self) -> None:
        """Clean up resources. Call before destruction."""
        self._timer.stop()
        self._stop_thread()
