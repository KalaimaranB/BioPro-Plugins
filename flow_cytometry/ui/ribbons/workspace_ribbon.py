"""Workspace ribbon — sample and group management actions.

Actions: Add Samples, Create Group, Load Template, Save Template.

File import follows the same pattern as Western Blot: if an FCS file
is outside the project folder, the user is asked whether to copy it
into the project's ``assets`` directory for portability.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
import uuid
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QWidget

from biopro.ui.theme import Colors, Fonts
from biopro.shared.ui.ui_components import PrimaryButton, SecondaryButton

from ...analysis.state import FlowState
from ...analysis.fcs_io import load_fcs
from biopro.sdk.core.events import CentralEventBus
from ...analysis import events
from ...analysis.experiment import (
    Experiment,
    Sample,
    SampleRole,
    Group,
    GroupRole,
    WorkflowTemplate,
)

logger = get_logger(__name__, "flow_cytometry")


class WorkspaceRibbon(QWidget):
    """Toolbar ribbon for workspace-level actions.

    Signals:
        samples_loaded:         Emitted after FCS files are loaded.
        group_requested:        Emitted to create a new group.
        template_load_requested: Emitted to load a workflow template.
        template_save_requested: Emitted to save as template.
    """

    samples_loaded = pyqtSignal()
    group_requested = pyqtSignal()
    template_load_requested = pyqtSignal()
    template_save_requested = pyqtSignal()
    workflow_save_requested = pyqtSignal()

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        btn_add = PrimaryButton("➕ Add Samples")
        btn_add.setToolTip("Load FCS files into the workspace")
        btn_add.clicked.connect(self._on_add_samples)
        layout.addWidget(btn_add)

        btn_group = SecondaryButton("📁 Create Group")
        btn_group.setToolTip("Create a new sample group")
        btn_group.clicked.connect(self.group_requested)
        layout.addWidget(btn_group)



        btn_save_wf = PrimaryButton("💾 Save Workflow")
        btn_save_wf.setToolTip("Save all gates, axes, and loaded files as a complete session")
        btn_save_wf.clicked.connect(self._on_save_workflow)
        layout.addWidget(btn_save_wf)

        layout.addStretch()

    # ── Helpers: Project Manager integration ──────────────────────────

    def _get_project_manager(self):
        """Retrieve the BioPro ProjectManager from the main window."""
        try:
            main_win = self.window()
            return getattr(main_win, "project_manager", None)
        except Exception:
            return None

    def _resolve_fcs_path(self, path: Path) -> Path:
        """Resolve an FCS file path, optionally copying into the project.

        If the file is outside the project's ``assets`` directory, ask
        the user whether to copy it in (same pattern as Western Blot).

        Args:
            path: The raw file path from the file dialog.

        Returns:
            The resolved path (either original or the copied asset path).
        """
        pm = self._get_project_manager()
        if pm is None:
            return path

        try:
            is_in_workspace = pm.assets_dir.resolve() in path.resolve().parents

            if not is_in_workspace:
                reply = QMessageBox.question(
                    self,
                    "Copy to Workspace?",
                    f"The file '{path.name}' is outside the project folder.\n\n"
                    "Would you like to copy it into the project's 'assets' "
                    "folder for safe keeping and portability?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                copy_to_workspace = (reply == QMessageBox.StandardButton.Yes)
            else:
                copy_to_workspace = False

            file_hash = pm.add_image(path, copy_to_workspace)
            resolved = pm.get_asset_path(file_hash)
            if resolved:
                return resolved

        except Exception as exc:
            QMessageBox.warning(
                self, "Asset Error",
                f"Failed to register asset with project:\n{exc}"
            )
            logger.exception("Asset registration error")

        return path

    # ── Actions ───────────────────────────────────────────────────────

    def _on_add_samples(self) -> None:
        """Open a file dialog, load FCS files, and add them to the state."""
        pm = self._get_project_manager()
        default_dir = str(pm.project_dir) if pm else ""

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select FCS Files",
            default_dir,
            "FCS Files (*.fcs);;All Files (*)",
        )
        if not files:
            return

        loaded_count = 0
        for fpath in files:
            try:
                final_path = self._resolve_fcs_path(Path(fpath))
                fcs_data = load_fcs(final_path)
                sample = Sample(
                    sample_id=str(uuid.uuid4()),
                    display_name=final_path.stem,
                    fcs_data=fcs_data,
                    role=SampleRole.OTHER,
                    markers=[m for m in fcs_data.markers if m],
                    is_compensated=fcs_data.is_compensated,
                )
                self._state.experiment.add_sample(sample)
                loaded_count += 1
                logger.info("Loaded sample: %s (%d events)",
                            sample.display_name, fcs_data.num_events)
            except Exception as exc:
                logger.error("Failed to load %s: %s", fpath, exc)
                QMessageBox.warning(
                    self, "Load Error",
                    f"Failed to load:\n{Path(fpath).name}\n\n{exc}"
                )

        if loaded_count > 0:
            self.samples_loaded.emit()
            CentralEventBus.publish(events.SAMPLE_LOADED, {
                "count": loaded_count,
                "source": "WorkspaceRibbon"
            })
            logger.info("Loaded %d FCS files.", loaded_count)

    def _on_load_template(self) -> None:
        """Open a template file and apply it to the workspace."""
        # Default to the built-in workflows directory
        workflows_dir = Path(__file__).resolve().parent.parent.parent / "workflows"
        default_dir = str(workflows_dir) if workflows_dir.exists() else ""

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Workflow Template",
            default_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            template = WorkflowTemplate.load(Path(path))
            self._state.experiment.apply_template(template)
            self.template_load_requested.emit()
            
            # Publish event
            CentralEventBus.publish(events.SAMPLE_LOADED, {
                "template_name": template.name,
                "source": "WorkspaceRibbon"
            })
            logger.info("Applied template: %s", template.name)
        except Exception as exc:
            logger.error("Failed to load template %s: %s", path, exc)
            QMessageBox.warning(
                self, "Template Error",
                f"Failed to load template:\n{Path(path).name}\n\n{exc}"
            )

    def _on_save_template(self) -> None:
        """Save the current workspace configuration as a reusable template."""
        exp = self._state.experiment

        # Build a WorkflowTemplate from the current experiment state
        from ...analysis.experiment import (
            GroupTemplate,
            TubeDefinition,
            MarkerMapping,
        )

        group_templates = []
        for group in exp.groups.values():
            tubes = []
            for sid in group.sample_ids:
                sample = exp.samples.get(sid)
                if sample:
                    tubes.append(TubeDefinition(
                        markers=list(sample.markers),
                        fmo_minus=sample.fmo_minus,
                    ))
            if tubes:
                group_templates.append(GroupTemplate(
                    name=group.name,
                    role=SampleRole.OTHER,
                    tubes=tubes,
                ))

        template = WorkflowTemplate(
            name=exp.name or "Untitled Template",
            description="Saved from active workspace.",
            markers=list({m for mm in exp.marker_mappings for m in [mm.marker_name]}),
            marker_mappings=list(exp.marker_mappings),
            groups=group_templates,
        )

        # Save dialog
        pm = self._get_project_manager()
        default_dir = ""
        if pm:
            wf_dir = pm.project_dir / "workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            default_dir = str(wf_dir)
        else:
            default_dir = str(
                Path(__file__).resolve().parent.parent.parent / "workflows"
            )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workflow Template",
            default_dir,
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            template.save(Path(path))
            QMessageBox.information(
                self, "Template Saved",
                f"Workflow template saved:\n{Path(path).name}"
            )
            self.template_save_requested.emit()
        except Exception as exc:
            logger.error("Failed to save template: %s", exc)
            QMessageBox.warning(
                self, "Save Error",
                f"Failed to save template:\n{exc}"
            )

    def _on_save_workflow(self) -> None:
        """Save the entire workspace state as a workflow using BioPro SDK services."""
        from biopro.ui.dialogs import SaveWorkflowDialog
        
        main_win = self.window()
        pm = self._get_project_manager()
        
        if pm is None:
            QMessageBox.critical(self, "Error", "Project Manager not found. Cannot save workflow.")
            return

        # 1. Pop the dialog to get metadata
        dialog = SaveWorkflowDialog(self)
        if not dialog.exec():
            return

        metadata = dialog.get_metadata()

        try:
            # 2. Get the payload from the main panel
            # We assume the parent/window of this ribbon is or contains the FlowCytometryPanel
            # In our architecture, FlowCytometryPanel is the PluginBase.
            # We can also just use self._state.to_workflow_dict() directly since we have it!
            payload = self._state.to_workflow_dict()

            # 3. Save via ProjectManager
            # We need the current module ID
            module_id = getattr(main_win, "current_module_id", "flow_cytometry")

            filename = pm.save_workflow(
                module_id=module_id,
                payload=payload,
                metadata=metadata
            )

            QMessageBox.information(
                self, "Workflow Saved",
                f"Workflow saved successfully:\n{filename}"
            )
            self.workflow_save_requested.emit()

        except Exception as exc:
            logger.error("Failed to save workflow: %s", exc)
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save workflow:\n{exc}"
            )
