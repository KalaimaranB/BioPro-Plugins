"""Service for splitting populations (Inside/Outside sibling creation)."""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..experiment import Experiment


class PopulationSplitter:
    """Service for splitting populations (Inside/Outside sibling creation)."""

    @staticmethod
    def split_population(experiment: Experiment, sample_id: str, node_id: str) -> Optional[tuple[str, str, str]]:
        """Creates a sibling population that is the inverse of the target node.

        Allows a single gate geometry to drive two complementary populations.

        Args:
            experiment: The active experiment model.
            sample_id:  Target sample ID.
            node_id:    ID of the node to split.

        Returns:
            Tuple of (new_node_id, new_name, gate_id) or None if splitting fails.
        """
        sample = experiment.samples.get(sample_id)
        if sample is None:
            return None

        node = sample.gate_tree.find_node_by_id(node_id)
        if node is None or node.gate is None or node.parent is None:
            return None

        # Create sibling using the same gate instance
        new_name = f"{node.name} (Outside)" if not node.negated else f"{node.name} (Inside)"
        sibling = node.parent.add_child(node.gate, name=new_name)
        sibling.negated = not node.negated

        return sibling.node_id, sibling.name, node.gate.gate_id
