"""Gate hierarchy widget — displays gating strategy independent of a full sample tree."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QHeaderView,
    QMenu,
    QButtonGroup,
    QPushButton,
)

from biopro.ui.theme import Colors, Fonts

from ...analysis.state import FlowState
from ...analysis.gating import GateNode
from biopro.sdk.core.events import CentralEventBus
from ...analysis import events


_POPULATION_ICONS = ["◆", "◇", "▸", "▹", "›"]

# Colors for different depth levels
_GATE_DEPTH_COLORS = [
    Colors.ACCENT_PRIMARY,
    "#FFB74D",
    "#4DD0E1",
    "#BA68C8",
    "#81C784",
]


class GateHierarchy(QWidget):
    """Tree view specifically for Gate Hierarchies.
    
    Signals:
        gate_double_clicked(node_id): Emitted on double clicking a population node
        selection_changed(node_id): Emitted on selection change
        gate_rename_requested(sample_id, node_id, new_name): User requests rename
        gate_delete_requested(sample_id, node_id): User requests delete
        copy_gates_requested(sample_id): User attempts to apply globally
    """

    gate_double_clicked = pyqtSignal(str)
    selection_changed = pyqtSignal(str)
    gate_rename_requested = pyqtSignal(str, str, str)
    gate_delete_requested = pyqtSignal(str, str)
    copy_gates_requested = pyqtSignal(str)

    def __init__(self, state: FlowState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._active_sample_id: str | None = None
        self._is_global_mode = True
        
        self._gate_item_map: dict[str, QTreeWidgetItem] = {}
        self._setup_ui()
        self._setup_events()

    def _setup_events(self) -> None:
        """Subscribe to relevant state events."""
        CentralEventBus.subscribe(events.GATE_CREATED, self._on_gate_change)
        CentralEventBus.subscribe(events.GATE_RENAMED, self._on_gate_change)
        CentralEventBus.subscribe(events.GATE_DELETED, self._on_gate_change)

    def _on_gate_change(self, data: dict) -> None:
        """Handle incoming gate change events."""
        # For simplicity in this phase, any gate change triggers a full refresh.
        # In a high-performance scenario, we'd update only the affected nodes.
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header / Mode Toggle ──
        header_widget = QWidget()
        header_widget.setStyleSheet(f"background: {Colors.BG_DARK}; border-bottom: 1px solid {Colors.BORDER};")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(8)

        # Toggle Button Group
        toggle_layout = QHBoxLayout()
        self._btn_current = QPushButton("Current Sample")
        self._btn_global = QPushButton("Global Strategy")
        
        for btn in (self._btn_current, self._btn_global):
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.BG_MEDIUM};
                    color: {Colors.FG_SECONDARY};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: 500;
                }}
                QPushButton:checked {{
                    background: {Colors.ACCENT_PRIMARY};
                    color: {Colors.BG_DARKEST};
                    font-weight: bold;
                    border: none;
                }}
            """)
        
        self._btn_global.setChecked(True)
        self._toggle_group = QButtonGroup(self)
        self._toggle_group.addButton(self._btn_current, 0)
        self._toggle_group.addButton(self._btn_global, 1)
        self._toggle_group.idToggled.connect(self._on_mode_toggled)

        toggle_layout.addWidget(self._btn_current)
        toggle_layout.addWidget(self._btn_global)
        header_layout.addLayout(toggle_layout)
        
        layout.addWidget(header_widget)

        # ── Tree ──
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Population", "Events", "%Parent"])
        self._tree.setColumnCount(3)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setRootIsDecorated(True)

        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.resizeSection(1, 65)
        header_view.resizeSection(2, 55)

        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {Colors.BG_DARKEST};"
            f" border: none; outline: none;"
            f" color: {Colors.FG_PRIMARY};"
            f" font-size: {Fonts.SIZE_SMALL}px; }}"
            f"QTreeWidget::item {{ padding: 3px 0;"
            f" border-bottom: 1px solid {Colors.BG_DARK}; }}"
            f"QTreeWidget::item:selected {{ background: {Colors.BG_MEDIUM};"
            f" color: {Colors.ACCENT_PRIMARY}; }}"
            f"QTreeWidget::item:hover {{ background: {Colors.BG_DARK}; }}"
            f"QTreeWidget::branch {{ background: {Colors.BG_DARKEST}; }}"
            f"QTreeWidget::branch:has-children:!has-siblings:closed,"
            f"QTreeWidget::branch:closed:has-children:has-siblings {{"
            f" border-image: none; image: none; }}"
            f"QTreeWidget::branch:open:has-children:!has-siblings,"
            f"QTreeWidget::branch:open:has-children:has-siblings {{"
            f" border-image: none; image: none; }}"
            f"QHeaderView::section {{ background: {Colors.BG_DARK};"
            f" color: {Colors.FG_SECONDARY}; border: none;"
            f" border-bottom: 1px solid {Colors.BORDER};"
            f" padding: 4px 6px; font-size: 10px; font-weight: 600; }}"
        )

        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree, stretch=1)
        
        # ── Bottom Action ──
        self._btn_apply_all = QPushButton("⇶ Apply Gates to All Samples")
        self._btn_apply_all.setFixedHeight(32)
        self._btn_apply_all.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_DARK};
                color: {Colors.FG_PRIMARY};
                border-top: 1px solid {Colors.BORDER};
                border-bottom: 1px solid {Colors.BORDER};
                border-left: none; border-right: none;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {Colors.BG_MEDIUM};
                color: {Colors.ACCENT_PRIMARY};
            }}
        """)
        self._btn_apply_all.clicked.connect(self._on_apply_all_clicked)
        layout.addWidget(self._btn_apply_all)

        # Empty state
        self._empty_label = QLabel(
            "No gates applied.\n\n"
            "Select a sample and use the\n"
            "toolbar to draw a gate."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            f"color: {Colors.FG_DISABLED}; font-size: {Fonts.SIZE_SMALL}px;"
            f" background: transparent; padding: 24px;"
        )
        layout.addWidget(self._empty_label)

    def set_active_sample(self, sample_id: str | None) -> None:
        """Update the active sample context to display its gates."""
        self._active_sample_id = sample_id
        self.refresh()

    def _on_mode_toggled(self, id: int, checked: bool) -> None:
        if checked:
            self._is_global_mode = (id == 1)
            # In purely global mode without an active sample selected, 
            # maybe find the first sample to render a template tree.
            if self._is_global_mode and not self._active_sample_id:
                for sid in self._state.experiment.samples:
                    self._active_sample_id = sid
                    break
            self.refresh()
            
    def _on_apply_all_clicked(self) -> None:
        if self._active_sample_id:
            self.copy_gates_requested.emit(self._active_sample_id)

    def refresh(self) -> None:
        self._tree.clear()
        self._gate_item_map.clear()

        # Robustness: if no active sample is set, try to use the global state's current sample
        sid = self._active_sample_id or self._state.current_sample_id
        if not sid:
            self._update_empty_state()
            return
            
        sample = self._state.experiment.samples.get(sid)
        if sample:
            self._add_gate_children(self._tree.invisibleRootItem(), sample.gate_tree, depth=0)
            
        self._tree.expandAll()
        self._update_empty_state()

    def update_gate_stats(self, sample_id: str, node_id: str = "") -> None:
        if sample_id != self._active_sample_id:
            return
            
        if not node_id:
            self.refresh()
            return

        item = self._gate_item_map.get(node_id)
        if item is None:
            self.refresh()
            return

        sample = self._state.experiment.samples.get(sample_id)
        if sample is None:
            return

        node = sample.gate_tree.find_node_by_id(node_id)
        if node is None:
            return

        # Update name (column 0)
        depth = 0
        curr = node
        while curr.parent:
            depth += 1
            curr = curr.parent
        icon = "⊘" if node.negated else _POPULATION_ICONS[min(depth, len(_POPULATION_ICONS) - 1)]
        item.setText(0, f"{icon} {node.name}")

        # Update stats
        if "count" in node.statistics:
            item.setText(1, f"{int(node.statistics['count']):,}")
        if "pct_parent" in node.statistics:
            item.setText(2, f"{node.statistics['pct_parent']:.1f}%")

    def update_all_sample_stats(self, sample_id: str) -> None:
        if sample_id == self._active_sample_id:
            self.refresh()

    def _add_gate_children(self, parent_item, gate_node: GateNode, depth: int = 0) -> None:
        for child in gate_node.children:
            if child.gate is None:
                continue

            icon = "⊘" if child.negated else _POPULATION_ICONS[min(depth, len(_POPULATION_ICONS) - 1)]
            color = Colors.ACCENT_NEGATIVE if child.negated else _GATE_DEPTH_COLORS[min(depth, len(_GATE_DEPTH_COLORS) - 1)]

            name = f"{icon} {child.name}"
            events_str = ""
            pct_str = ""

            if "count" in child.statistics:
                events_str = f"{int(child.statistics['count']):,}"
            if "pct_parent" in child.statistics:
                pct_str = f"{child.statistics['pct_parent']:.1f}%"

            item = QTreeWidgetItem([name, events_str, pct_str])
            item.setData(0, Qt.ItemDataRole.UserRole, child.node_id)

            item.setForeground(0, QColor(color))
            
            gate_type = type(child.gate).__name__
            tooltip = f"{child.name}\nType: {gate_type}"
            if child.statistics:
                tooltip += f"\n%Total: {child.statistics.get('pct_total', 0.0):.1f}%"
            item.setToolTip(0, tooltip)

            item.setForeground(1, QColor(Colors.FG_SECONDARY))
            item.setForeground(2, QColor(Colors.FG_SECONDARY))

            if isinstance(parent_item, QTreeWidget):
                parent_item.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            self._gate_item_map[child.node_id] = item
            self._add_gate_children(item, child, depth + 1)

    def _update_empty_state(self) -> None:
        is_empty = self._tree.topLevelItemCount() == 0
        self._tree.setVisible(not is_empty)
        self._empty_label.setVisible(is_empty)

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        gate_id = item.data(0, Qt.ItemDataRole.UserRole)
        if gate_id and self._active_sample_id:
            self.gate_double_clicked.emit(gate_id)

    def _on_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        if current is None:
            return
        gate_id = current.data(0, Qt.ItemDataRole.UserRole)
        if gate_id and self._active_sample_id:
            self.selection_changed.emit(gate_id)

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return

        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not node_id or not self._active_sample_id:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {Colors.BG_DARK}; color: {Colors.FG_PRIMARY};"
            f" border: 1px solid {Colors.BORDER}; font-size: {Fonts.SIZE_SMALL}px; }}"
            f"QMenu::item:selected {{ background: {Colors.BG_MEDIUM}; }}"
            f"QMenu::separator {{ background: {Colors.BORDER}; height: 1px; }}"
        )

        rename_act = QAction("✏️  Rename Population", self)
        rename_act.triggered.connect(lambda: self._prompt_rename(node_id))
        menu.addAction(rename_act)

        menu.addSeparator()

        del_act = QAction("🗑️  Delete Population", self)
        del_act.triggered.connect(lambda: self.gate_delete_requested.emit(self._active_sample_id, node_id))
        menu.addAction(del_act)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _prompt_rename(self, node_id: str) -> None:
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        
        # Get current name
        current_name = ""
        sample = self._state.experiment.samples.get(self._active_sample_id)
        if sample:
            node = sample.gate_tree.find_node_by_id(node_id)
            if node:
                current_name = node.name

        new_name, ok = QInputDialog.getText(
            self, "Rename Population", "Enter new name:",
            QLineEdit.EchoMode.Normal, current_name
        )
        if ok and new_name and self._active_sample_id:
            self.gate_rename_requested.emit(self._active_sample_id, node_id, new_name)


