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

from biopro.sdk.utils.logging import get_logger
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

logger = get_logger(__name__, "flow_cytometry")


from biopro.sdk.core import AnalysisBase, PluginState
from biopro.core.task_scheduler import task_scheduler

class _PropagationWorker(AnalysisBase):
    """Worker that runs via TaskScheduler in the background.

    Receives a gate tree snapshot and a list of target samples,
    then re-applies the tree to each sample and returns progress statistics.
    """

    def __init__(self, plugin_id: str = "flow_cytometry") -> None:
        super().__init__(plugin_id)
        self._gate_tree_dict: Optional[dict] = None
        self._target_samples: list[Sample] = []

    def configure(
        self,
        gate_tree_dict: dict,
        target_samples: list[Sample],
    ) -> None:
        """Set the work payload before submitting to the scheduler."""
        self._gate_tree_dict = gate_tree_dict
        self._target_samples = list(target_samples)

    def run(self, state: PluginState) -> dict:
        """Execute the propagation — called by the TaskScheduler."""
        if self._gate_tree_dict is None:
            return {}

        results = {}
        for sample in self._target_samples:
            try:
                stats, new_tree = self._apply_tree_to_sample(
                    self._gate_tree_dict, sample
                )
                # Store sample results by ID
                results[sample.sample_id] = {
                    "stats": stats,
                    "tree": new_tree
                }
            except Exception as exc:
                logger.warning(
                    "Propagation failed for '%s': %s",
                    sample.display_name, exc,
                )
                # Fail hard if a sample fails, or continue? 
                # Let's collect successes and report errors in return dict.
                results[sample.sample_id] = {"error": str(exc)}

        return {"propagation_results": results}

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


class _PropagationHandler(QObject):
    """Helper to route TaskScheduler signals back to the propagator.
    
    Prevents listener leaks by disconnecting on first call and ensuring 
    only the relevant task_id is processed.
    """
    def __init__(self, task_id: str, propagator: 'GatePropagator', parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self._propagator = propagator

    def on_finished(self, tid: str, results: dict):
        if tid == self._task_id:
            task_scheduler.task_finished.disconnect(self.on_finished)
            task_scheduler.task_error.disconnect(self.on_error)
            self._propagator._on_propagation_finished(tid, results)
            self.deleteLater()

    def on_error(self, tid: str, error_msg: str):
        if tid == self._task_id:
            task_scheduler.task_finished.disconnect(self.on_finished)
            task_scheduler.task_error.disconnect(self.on_error)
            self._propagator._on_propagation_error(tid, error_msg)
            self.deleteLater()


class GatePropagator(QObject):
    """Debounced gate propagation manager using TaskScheduler.

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

        self._active_task_id: Optional[str] = None

    def request_propagation(
        self, gate_id: str, source_sample_id: str
    ) -> None:
        """Request gate propagation with debouncing."""
        self._mutex.lock()
        self._pending_gate_id = gate_id
        self._pending_source_id = source_sample_id
        self._mutex.unlock()

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

        tree_dict = source.gate_tree.to_dict()
        targets = self._find_targets(source_id)
        if not targets:
            self.propagation_complete.emit()
            return

        # Cancel previous if still running? Better to let scheduler manage.
        
        worker = _PropagationWorker()
        worker.configure(tree_dict, targets)
        
        task_id = task_scheduler.submit(worker, self._state)
        self._active_task_id = task_id
        
        # Use a dedicated handler object to avoid listener leaks and stale closures
        handler = _PropagationHandler(task_id, self, parent=self)
        task_scheduler.task_finished.connect(handler.on_finished)
        task_scheduler.task_error.connect(handler.on_error)

        logger.info(
            "Propagating gates from '%s' to %d samples via TaskScheduler.",
            source.display_name, len(targets),
        )

    def _on_propagation_finished(self, task_id: str, results: dict) -> None:
        """Internal callback for propagation completion."""
        propagation_results = results.get("propagation_results", {})
        for sid, res in propagation_results.items():
            if "error" in res:
                logger.warning(f"Propagator error for {sid}: {res['error']}")
                continue
            self._on_sample_updated(sid, res["stats"], res["tree"])
        
        self.propagation_complete.emit()
        logger.debug("Gate propagation complete.")

    def _on_propagation_error(self, task_id: str, error_msg: str) -> None:
        """Internal callback for propagation error."""
        logger.error(f"Gate propagation task failed: {error_msg}")
        self.propagation_complete.emit()

    def _find_targets(self, source_id: str) -> list[Sample]:
        """Find all target samples for propagation."""
        source = self._state.experiment.samples.get(source_id)
        if source is None:
            return []

        target_ids: set[str] = set()

        for group in self._state.experiment.groups.values():
            if source_id in group.sample_ids:
                target_ids.update(group.sample_ids)

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

    def cleanup(self) -> None:
        """Clean up resources."""
        self._timer.stop()
        # Active tasks will be managed by TaskScheduler on shutdown
