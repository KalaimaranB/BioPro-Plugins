"""Experiment model — samples, groups, roles, and workflow templates.

This is the scientist-centric data model that distinguishes BioPro's
flow module from traditional data-centric tools.  Instead of treating
FCS files as undifferentiated data, the experiment model captures the
scientist's intent: which samples are controls, what markers are on
each tube, and what analysis steps should be applied.

Workflow templates capture the full experimental protocol and analysis
pipeline so that a scientist can re-run the same assay on new data
with one click.
"""

from __future__ import annotations

import json
from biopro.sdk.utils.logging import get_logger
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .fcs_io import FCSData
from .gating import GateNode
from .scaling import AxisScale

logger = get_logger(__name__, "flow_cytometry")


# ── Enums ────────────────────────────────────────────────────────────────────


class SampleRole(Enum):
    """Role of a sample in the experimental design."""

    UNSTAINED = "unstained"
    SINGLE_STAIN = "single_stain"
    FMO_CONTROL = "fmo_control"
    ISOTYPE_CONTROL = "isotype_control"
    FULL_PANEL = "full_panel"
    OTHER = "other"


class GroupRole(Enum):
    """Role of a sample group."""

    COMPENSATION = "compensation"
    CONTROL = "control"
    TEST = "test"
    ALL_SAMPLES = "all_samples"
    CUSTOM = "custom"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class MarkerMapping:
    """Mapping of a biological marker to its fluorophore and channel.

    Attributes:
        marker_name:  Biological target (e.g., ``"CD4"``).
        fluorophore:  Dye/conjugate name (e.g., ``"FITC"``).
        channel:      Cytometer channel (e.g., ``"FL1-A"``).
        color:        Display color for plots (hex string).
    """

    marker_name: str
    fluorophore: str = ""
    channel: str = ""
    color: str = "#00FF00"

    def to_dict(self) -> dict:
        return {
            "marker_name": self.marker_name,
            "fluorophore": self.fluorophore,
            "channel": self.channel,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarkerMapping":
        return cls(**data)


@dataclass
class Sample:
    """A single sample in the experiment.

    Attributes:
        sample_id:     Unique identifier.
        display_name:  Human-readable name shown in the sample tree.
        fcs_data:      Loaded FCS data (None if not yet loaded).
        role:          The role this sample plays (unstained, FMO, etc.).
        markers:       Which markers are present on this sample.
        fmo_minus:     If this is an FMO control, which marker is excluded.
        group_ids:     Groups this sample belongs to.
        gate_tree:     Hierarchical gating tree rooted at this sample.
        keywords:      Annotation keywords (from FCS metadata or user).
        is_compensated: Whether compensation has been applied.
    """

    sample_id: str
    display_name: str
    fcs_data: Optional[FCSData] = None
    role: SampleRole = SampleRole.OTHER
    markers: list[str] = field(default_factory=list)
    fmo_minus: Optional[str] = None
    group_ids: list[str] = field(default_factory=list)
    gate_tree: GateNode = field(default_factory=GateNode)
    keywords: dict[str, str] = field(default_factory=dict)
    is_compensated: bool = False
    last_viewed_axes: dict[str, dict] = field(default_factory=dict)

    @property
    def has_data(self) -> bool:
        """Return True if FCS data has been loaded for this sample."""
        return self.fcs_data is not None

    @property
    def event_count(self) -> int:
        """Total number of events (0 if no data loaded)."""
        return self.fcs_data.num_events if self.fcs_data else 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize sample metadata (not the raw events)."""
        return {
            "sample_id": self.sample_id,
            "display_name": self.display_name,
            "file_path": str(self.fcs_data.file_path) if self.fcs_data else None,
            "role": self.role.value,
            "markers": self.markers,
            "fmo_minus": self.fmo_minus,
            "group_ids": self.group_ids,
            "keywords": self.keywords,
            "is_compensated": self.is_compensated,
            "last_viewed_axes": self.last_viewed_axes,
            "gate_tree": self.gate_tree.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Sample":
        """Reconstruct a Sample from a serialized dictionary.

        Note: ``fcs_data`` is NOT restored here — it is reloaded
        separately by ``FlowState._reload_fcs_data()``.
        """
        sample = cls(
            sample_id=data["sample_id"],
            display_name=data["display_name"],
            role=SampleRole(data.get("role", "other")),
            markers=data.get("markers", []),
            fmo_minus=data.get("fmo_minus"),
            group_ids=data.get("group_ids", []),
            keywords=data.get("keywords", {}),
            is_compensated=data.get("is_compensated", False),
        )
        sample.last_viewed_axes = data.get("last_viewed_axes", {})
        if "gate_tree" in data:
            sample.gate_tree = GateNode.from_dict(data["gate_tree"])
        return sample


@dataclass
class Group:
    """A named collection of samples with a role.

    Attributes:
        group_id:    Unique identifier.
        name:        Display name (e.g., ``"FMO Controls"``).
        role:        The group's functional role.
        color:       Display color (hex string).
        sample_ids:  IDs of samples in this group.
    """

    group_id: str
    name: str
    role: GroupRole = GroupRole.CUSTOM
    color: str = "#4A90D9"
    sample_ids: list[str] = field(default_factory=list)
    channel_scales: dict[str, AxisScale] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.sample_ids)

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "role": self.role.value,
            "color": self.color,
            "sample_ids": self.sample_ids,
            "channel_scales": {ch: sc.to_dict() for ch, sc in self.channel_scales.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Group":
        return cls(
            group_id=data["group_id"],
            name=data["name"],
            role=GroupRole(data.get("role", "custom")),
            color=data.get("color", "#4A90D9"),
            sample_ids=data.get("sample_ids", []),
        )
        group.channel_scales = {
            ch: AxisScale.from_dict(sc) 
            for ch, sc in data.get("channel_scales", {}).items()
        }
        return group


# ── Workflow Template ────────────────────────────────────────────────────────


@dataclass
class TubeDefinition:
    """Defines one tube in a workflow template.

    Attributes:
        markers:    List of marker names present in this tube.
        fmo_minus:  If this is an FMO tube, the marker that was excluded.
    """

    markers: list[str] = field(default_factory=list)
    fmo_minus: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"markers": self.markers}
        if self.fmo_minus:
            d["fmo_minus"] = self.fmo_minus
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TubeDefinition":
        return cls(
            markers=data.get("markers", []),
            fmo_minus=data.get("fmo_minus"),
        )


@dataclass
class GroupTemplate:
    """Defines a group of tubes in a workflow template.

    Attributes:
        name:   Group name (e.g., ``"FMO Controls"``).
        role:   Sample role for tubes in this group.
        tubes:  List of tube specifications.
    """

    name: str
    role: SampleRole
    tubes: list[TubeDefinition] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role.value,
            "tubes": [t.to_dict() for t in self.tubes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroupTemplate":
        return cls(
            name=data["name"],
            role=SampleRole(data.get("role", "other")),
            tubes=[TubeDefinition.from_dict(t) for t in data.get("tubes", [])],
        )


@dataclass
class WorkflowTemplate:
    """A reusable experiment protocol and analysis pipeline.

    Captures the complete experimental design: which markers, which tube
    groups (unstained, single stains, FMOs, full panel), and optionally
    a saved gating strategy that can be adapted to new data.

    Attributes:
        name:            Template display name.
        description:     What this template is for.
        markers:         The full marker panel.
        marker_mappings: Marker → fluorophore → channel mappings.
        groups:          Group definitions with tube layouts.
        gate_template:   Optional saved gating tree (serialized).
        protocol_notes:  Free-text protocol instructions.
    """

    name: str
    description: str = ""
    markers: list[str] = field(default_factory=list)
    marker_mappings: list[MarkerMapping] = field(default_factory=list)
    groups: list[GroupTemplate] = field(default_factory=list)
    gate_template: Optional[dict] = None
    protocol_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "markers": self.markers,
            "marker_mappings": [m.to_dict() for m in self.marker_mappings],
            "groups": [g.to_dict() for g in self.groups],
            "gate_template": self.gate_template,
            "protocol_notes": self.protocol_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowTemplate":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            markers=data.get("markers", []),
            marker_mappings=[
                MarkerMapping.from_dict(m)
                for m in data.get("marker_mappings", [])
            ],
            groups=[
                GroupTemplate.from_dict(g) for g in data.get("groups", [])
            ],
            gate_template=data.get("gate_template"),
            protocol_notes=data.get("protocol_notes", ""),
        )

    def save(self, path: Path) -> None:
        """Save the template to a JSON file.

        Args:
            path: File path to write to.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Saved workflow template to %s", path)

    @classmethod
    def load(cls, path: Path) -> "WorkflowTemplate":
        """Load a template from a JSON file.

        Args:
            path: File path to read from.

        Returns:
            A :class:`WorkflowTemplate` instance.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# ── Experiment ───────────────────────────────────────────────────────────────


@dataclass
class Experiment:
    """Top-level container for the entire workspace state.

    Holds all samples, groups, marker mappings, and the active workflow
    template.

    Attributes:
        name:             Experiment/workspace name.
        samples:          All loaded samples, keyed by sample_id.
        groups:           All defined groups, keyed by group_id.
        marker_mappings:  The panel's marker-to-channel mappings.
        active_template:  The workflow template currently in use.
    """

    name: str = "Untitled Experiment"
    samples: dict[str, Sample] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)
    marker_mappings: list[MarkerMapping] = field(default_factory=list)
    active_template: Optional[WorkflowTemplate] = None

    def add_sample(self, sample: Sample) -> None:
        """Add a sample to the experiment.

        Args:
            sample: The sample to add.
        """
        self.samples[sample.sample_id] = sample

    def remove_sample(self, sample_id: str) -> None:
        """Remove a sample and clean up its group memberships.

        Args:
            sample_id: The ID of the sample to remove.
        """
        self.samples.pop(sample_id, None)
        for group in self.groups.values():
            if sample_id in group.sample_ids:
                group.sample_ids.remove(sample_id)

    def add_group(self, group: Group) -> None:
        """Add a group to the experiment.

        Args:
            group: The group to add.
        """
        self.groups[group.group_id] = group

    def get_samples_in_group(self, group_id: str) -> list[Sample]:
        """Return all samples belonging to a group.

        Args:
            group_id: The group identifier.

        Returns:
            List of :class:`Sample` instances.
        """
        group = self.groups.get(group_id)
        if not group:
            return []
        return [
            self.samples[sid]
            for sid in group.sample_ids
            if sid in self.samples
        ]

    def get_samples_by_role(self, role: SampleRole) -> list[Sample]:
        """Return all samples with a specific role.

        Args:
            role: The :class:`SampleRole` to filter by.

        Returns:
            List of matching samples.
        """
        return [s for s in self.samples.values() if s.role == role]

    def apply_template(self, template: WorkflowTemplate) -> None:
        """Apply a workflow template — creates groups and sample slots.

        This sets up the expected structure from the template but does
        NOT load any FCS data.  The scientist then maps FCS files into
        the pre-created slots.

        Args:
            template: The workflow template to apply.
        """
        import uuid

        self.active_template = template
        self.marker_mappings = list(template.marker_mappings)

        for gt in template.groups:
            group = Group(
                group_id=str(uuid.uuid4()),
                name=gt.name,
                role=_sample_role_to_group_role(gt.role),
            )

            for tube in gt.tubes:
                sample = Sample(
                    sample_id=str(uuid.uuid4()),
                    display_name=_tube_display_name(gt, tube),
                    role=gt.role,
                    markers=list(tube.markers),
                    fmo_minus=tube.fmo_minus,
                )
                sample.group_ids.append(group.group_id)
                group.sample_ids.append(sample.sample_id)
                self.add_sample(sample)

            self.add_group(group)

        logger.info(
            "Applied workflow template '%s': %d groups, %d sample slots.",
            template.name, len(template.groups),
            sum(len(gt.tubes) for gt in template.groups),
        )

    def to_dict(self) -> dict:
        """Serialize the experiment for workflow save."""
        return {
            "name": self.name,
            "samples": {
                sid: s.to_dict() for sid, s in self.samples.items()
            },
            "groups": {
                gid: g.to_dict() for gid, g in self.groups.items()
            },
            "marker_mappings": [m.to_dict() for m in self.marker_mappings],
            "active_template": (
                self.active_template.to_dict()
                if self.active_template
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Experiment":
        """Reconstruct an Experiment from a serialized dictionary.

        Note: ``fcs_data`` for samples is NOT loaded here.
        """
        exp = cls(
            name=data.get("name", "Untitled Experiment"),
        )

        logger.info(f"Reconstructing Experiment '{exp.name}' from dict...")
        
        # Restore samples
        sample_count = 0
        for sid, sdata in data.get("samples", {}).items():
            sample = Sample.from_dict(sdata)
            exp.samples[sid] = sample
            sample_count += 1

        logger.info(f"Restored {sample_count} samples.")

        # Restore groups
        for gid, gdata in data.get("groups", {}).items():
            exp.groups[gid] = Group.from_dict(gdata)

        # Restore marker mappings
        exp.marker_mappings = [
            MarkerMapping.from_dict(m)
            for m in data.get("marker_mappings", [])
        ]

        # Restore template
        tmpl_data = data.get("active_template")
        if tmpl_data:
            exp.active_template = WorkflowTemplate.from_dict(tmpl_data)

        return exp


# ── Helpers ──────────────────────────────────────────────────────────────────


def _sample_role_to_group_role(role: SampleRole) -> GroupRole:
    """Map a sample role to a group role."""
    mapping = {
        SampleRole.UNSTAINED: GroupRole.CONTROL,
        SampleRole.SINGLE_STAIN: GroupRole.COMPENSATION,
        SampleRole.FMO_CONTROL: GroupRole.CONTROL,
        SampleRole.ISOTYPE_CONTROL: GroupRole.CONTROL,
        SampleRole.FULL_PANEL: GroupRole.TEST,
        SampleRole.OTHER: GroupRole.CUSTOM,
    }
    return mapping.get(role, GroupRole.CUSTOM)


def _tube_display_name(group: GroupTemplate, tube: TubeDefinition) -> str:
    """Generate a human-readable name for a tube slot."""
    if not tube.markers:
        return f"{group.name} (no markers)"
    if tube.fmo_minus:
        return f"FMO minus {tube.fmo_minus}"
    if len(tube.markers) == 1:
        return f"{tube.markers[0]} only"
    return ", ".join(tube.markers)
