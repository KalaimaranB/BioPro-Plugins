# Flow Cytometry Module - Implementation Plan

**Date:** April 21, 2026  
**Scope:** 8 major UX/architecture improvements + 1 critical bug fix

---

## Overview

This plan addresses 8 user-facing improvements and architectural enhancements to the flow cytometry module, plus resolves a critical `NoneType` crash when bulk-gating samples. The plan is structured by priority and architectural impact.

---

## Issue Breakdown & Solutions

### **[CRITICAL BUG] #6: Sample List NoneType Crash**

**Problem:**  
When bulk-gating gates from 'Specimen_001_Sample C' to 9 samples via TaskScheduler, the app crashes with:
```
AttributeError: 'NoneType' object has no attribute 'data'
  File ".../flow_cytometry/ui/widgets/sample_list.py", line 182, in _on_selection_changed
    sample_id = current.data(0, Qt.ItemDataRole.UserRole)
```

**Root Cause:**  
The `_on_selection_changed` callback from `QTreeWidget.itemSelectionChanged` signal is called with `current=None` when:
- Clearing selection during bulk gate operations
- Rapid multi-selection changes during TaskScheduler propagation
- Signal fires but no valid item is selected

**Fix:**
```python
def _on_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
    if current is None:  # ← Guard clause
        return
    sample_id = current.data(0, Qt.ItemDataRole.UserRole)
    if sample_id:
        self.selection_changed.emit(sample_id)
```

**File:** [flow_cytometry/ui/widgets/sample_list.py](flow_cytometry/ui/widgets/sample_list.py#L182)  
**Complexity:** Trivial (1 line)  
**Risk:** Minimal — just defensive programming  

---

### **#1: Default Gating to "Global Strategy"**

**Problem:**  
UI defaults to "Current Sample" mode. Researchers typically want to define a global gating strategy once, then apply it uniformly across groups.

**Current State:**  
- `GateHierarchy._is_global_mode = False` (hardcoded)
- Toggle buttons exist but "Current Sample" is selected by default
- User must manually click "Global Strategy" each session

**Solution:**

#### 1.1 Change Default State
**File:** [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py#L75)
```python
# Line 75, __init__
self._is_global_mode = True  # Change from False
```

#### 1.2 Update Toggle Button Default
**File:** [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py#L100-L110)
```python
# After creating buttons, set default:
self._btn_global.setChecked(True)
self._btn_current.setChecked(False)
```

#### 1.3 Persist User Preference
Update state management to save the last-used mode:
- Store `gating_mode: str` in `FlowState` (global strategy | current sample)
- Load on plugin initialization
- Emit signal when toggled so main_panel can update preferences

**Files:**
- [flow_cytometry/analysis/state.py](flow_cytometry/analysis/state.py) — Add `gating_mode` field
- [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py) — Emit `gating_mode_changed` signal
- [flow_cytometry/ui/main_panel.py](flow_cytometry/ui/main_panel.py) — Connect mode changes to state persistence

**Complexity:** Low (state management + signal wiring)  
**Risk:** Low — no behavioral change, just UX defaults  

---

### **#2: Render Quality Toggle (Optimized vs Transparent)**

**Problem:**  
Currently, right-clicking a plot prompts "Render Full Quality" (waits for all ~5M events @ 2x resolution). No visual indicator of current mode. Users can't switch modes mid-workflow.

**Desired UX:**
- Toggle button near Transform dropdown: **[◆ Optimized] [◆ Transparent]**
- Optimized (default): 100K events subsampled, 1x resolution, hybrid cache (fast interactive)
- Transparent (full): All events, 2x resolution, no cache (slower but publication-ready)
- Toggle applies immediately to current plot + all future renders in session

**Current Architecture:**
- `FlowCanvas._max_events` and `_quality_multiplier` control quality
- `_render_data_layer()` checks these flags
- Right-click via context menu directly calls `_render_full_quality()`

**Solution:**

#### 2.1 Add Quality Mode Toggle to Flow Canvas
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L100)
```python
class FlowCanvas:
    def __init__(self, ...):
        self._render_quality: str = "optimized"  # or "transparent"
        self._setup_quality_controls()
    
    def _setup_quality_controls(self):
        """Add horizontal button group to canvas toolbar."""
        # Two buttons: "◆ Optimized" and "◆ Transparent"
        # Default: Optimized
        # Connected to self._on_quality_mode_changed()
```

#### 2.2 Implement Quality Mode Switching
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L800)
```python
def _on_quality_mode_changed(self, mode: str) -> None:
    """Switch between optimized and transparent rendering."""
    self._render_quality = mode
    
    if mode == "optimized":
        self._max_events = 100_000
        self._quality_multiplier = 1.0
        self._use_cache = True
    elif mode == "transparent":
        self._max_events = None
        self._quality_multiplier = 2.0
        self._use_cache = False
    
    # Redraw immediately
    self._redraw()
    self.quality_mode_changed.emit(mode)
```

#### 2.3 Persist Mode Preference
- Add `render_quality: str` to `FlowState`
- Load on session start
- Expose as setting in UI preferences

#### 2.4 Remove Right-Click Full Quality Option
- Delete the "Render Full Quality" context menu item
- Update help text: "Use the Optimized/Transparent toggle to control render quality"

**Files:**
- [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py)
- [flow_cytometry/analysis/state.py](flow_cytometry/analysis/state.py)
- [flow_cytometry/ui/graph/graph_window.py](flow_cytometry/ui/graph/graph_window.py) — Remove context menu item

**Complexity:** Medium (new controls + state management + redraw coordination)  
**Risk:** Medium — must ensure both quality modes produce correct results  
**Testing:** Unit test both modes; visual inspection of optimized vs full output  

---

### **#3: Right-Click Image → Copy or Download**

**Problem:**  
Currently right-click only has "Render Full Quality" option. No way to quickly save/share a plot.

**Desired UX:**
```
Right-click on plot:
├─ Copy to Clipboard (PNG)
├─ Download as PNG...
├─ Download as PDF...
└─ Download as SVG...
```

**Current Architecture:**
- `FlowCanvas` already has export machinery in `_save_figure()`
- Context menu built in `_setup_context_menu()` 

**Solution:**

#### 3.1 Expand Context Menu
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L600)
```python
def _setup_context_menu(self):
    menu = QMenu()
    
    # Copy to clipboard
    copy_action = QAction("Copy to Clipboard (PNG)", self)
    copy_action.triggered.connect(self._copy_to_clipboard)
    menu.addAction(copy_action)
    
    menu.addSeparator()
    
    # Download submenu
    download_menu = menu.addMenu("Download")
    for fmt in ["PNG", "PDF", "SVG"]:
        action = QAction(fmt, self)
        action.triggered.connect(lambda checked, f=fmt: self._on_download(f))
        download_menu.addAction(action)
    
    self._context_menu = menu
```

#### 3.2 Implement Clipboard Copy
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L650)
```python
def _copy_to_clipboard(self) -> None:
    """Render figure to PNG in memory and copy to system clipboard."""
    from PyQt6.QtGui import QImage, QClipboard
    from PyQt6.QtWidgets import QApplication
    import io
    
    buf = io.BytesIO()
    self._figure.savefig(buf, format='png', dpi=96)
    buf.seek(0)
    image = QImage()
    image.loadFromData(buf.read())
    
    clipboard = QApplication.clipboard()
    clipboard.setImage(image)
    self.status_message.emit("Plot copied to clipboard")
```

#### 3.3 Implement Download
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L670)
```python
def _on_download(self, fmt: str) -> None:
    """Download plot in specified format."""
    from PyQt6.QtWidgets import QFileDialog
    
    suffix = fmt.lower()
    file_path, _ = QFileDialog.getSaveFileName(
        self, f"Save as {fmt}", "", f"{fmt} (*.{suffix})"
    )
    if file_path:
        dpi = 300 if fmt == "PDF" else 150
        self._figure.savefig(file_path, format=suffix, dpi=dpi, bbox_inches='tight')
        self.status_message.emit(f"Plot saved to {file_path}")
```

**Files:**
- [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py)

**Complexity:** Low (straightforward matplotlib export methods)  
**Risk:** Minimal — leverages existing export machinery  

---

### **#4: Visible Exit Button for Sample View**

**Problem:**  
No visual "X" or "Back" button to exit a single sample view and return to the sample list.

**Current UX:**
- Selecting a sample opens it in the graph
- No clear way to unselect and return to list view
- Users must click elsewhere or restart workflow

**Architecture:**
- `GraphManager` is a tabbed container
- Each tab = one sample's plots
- When sample is deselected, its tab should close or "Back" button should appear

**Solution:**

#### 4.1 Add Close Button to Tab Bar
**File:** [flow_cytometry/ui/graph/graph_manager.py](flow_cytometry/ui/graph/graph_manager.py#L100)
```python
class GraphManager(QTabWidget):
    def _setup_tabs(self):
        # Enable close buttons on tabs
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self._on_tab_closed)
    
    def _on_tab_closed(self, index: int) -> None:
        """Close a sample's graph tab."""
        graph_window = self.widget(index)
        sample_id = graph_window.sample_id
        self.removeTab(index)
        # Emit signal to deselect sample
        self.sample_closed.emit(sample_id)
```

#### 4.2 Add "Back" Button in Graph Window Header (Alternative)
**File:** [flow_cytometry/ui/graph/graph_window.py](flow_cytometry/ui/graph/graph_window.py#L80)
```python
class GraphWindow(QWidget):
    def _setup_header(self):
        header = QHBoxLayout()
        
        # Back button
        back_btn = QPushButton("← Back to Samples")
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        
        # Sample name label
        header.addWidget(QLabel(f"Sample: {self.sample_id}"))
        header.addStretch()
```

**Recommendation:** **Option 1 (Tab Close Button)** — More intuitive, standard pattern, already familiar to users from browsers/IDEs.

**Files:**
- [flow_cytometry/ui/graph/graph_manager.py](flow_cytometry/ui/graph/graph_manager.py)
- [flow_cytometry/ui/graph/graph_window.py](flow_cytometry/ui/graph/graph_window.py)
- [flow_cytometry/ui/main_panel.py](flow_cytometry/ui/main_panel.py) — Connect close signal

**Complexity:** Low (standard PyQt6 tab close pattern)  
**Risk:** Minimal — leverages standard UI patterns  

---

### **#5: Gate Naming Propagation**

**Problem:**  
When renaming a gate, the change doesn't immediately reflect across all dependent samples and UI elements.

**Current Behavior:**
1. User renames gate "P1" → "Live Cells" on Sample A
2. UI updates for Sample A
3. But Sample B (which has the same gate) still shows "P1"
4. User must refresh or navigate away/back to see the change

**Root Cause:**
- `GateController._on_gate_renamed()` updates the gate in `sample.gate_tree`
- But it doesn't broadcast the change to other samples that share the same gate template
- UI doesn't subscribe to individual gate rename events

**Solution:**

#### 5.1 Emit Gate Rename Signal
**File:** [flow_cytometry/analysis/gate_controller.py](flow_cytometry/analysis/gate_controller.py#L400)
```python
class GateController:
    gate_renamed = pyqtSignal(str, str, str)  # (sample_id, node_id, new_name)
    
    def _on_gate_renamed(self, sample_id: str, node_id: str, new_name: str) -> None:
        """Handle gate rename request."""
        sample = self._state.get_sample(sample_id)
        node = sample.gate_tree.find_node(node_id)
        
        if node:
            old_name = node.name
            node.name = new_name
            
            # Emit immediately
            self.gate_renamed.emit(sample_id, node_id, new_name)
            
            # Propagate to dependent samples (same group)
            self._propagate_gate_rename(sample_id, node_id, new_name)
            
            # Mark state changed for undo/redo
            self.state_changed.emit()
```

#### 5.2 Implement Cross-Sample Propagation
**File:** [flow_cytometry/analysis/gate_controller.py](flow_cytometry/analysis/gate_controller.py#L420)
```python
def _propagate_gate_rename(self, source_sample_id: str, node_id: str, new_name: str) -> None:
    """Rename the same gate node in all samples in the same group."""
    source_sample = self._state.get_sample(source_sample_id)
    group_id = source_sample.group_id
    
    for sample_id, sample in self._state.samples.items():
        if sample.group_id == group_id and sample_id != source_sample_id:
            node = sample.gate_tree.find_node(node_id)
            if node:
                node.name = new_name
                # Emit signal so UI updates
                self.gate_renamed.emit(sample_id, node_id, new_name)
```

#### 5.3 Connect UI to Gate Rename Signal
**File:** [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py#L200)
```python
class GateHierarchy(QWidget):
    def connect_gate_controller(self, controller: GateController) -> None:
        controller.gate_renamed.connect(self._on_gate_renamed_update)
    
    def _on_gate_renamed_update(self, sample_id: str, node_id: str, new_name: str) -> None:
        """Update gate tree item when rename completes."""
        if sample_id == self._active_sample_id:
            item = self._gate_item_map.get(node_id)
            if item:
                item.setText(0, new_name)
```

#### 5.4 Update Properties Panel Immediately
**File:** [flow_cytometry/ui/widgets/properties_panel.py](flow_cytometry/ui/widgets/properties_panel.py)
```python
def connect_gate_controller(self, controller: GateController) -> None:
    controller.gate_renamed.connect(self._on_gate_name_changed)

def _on_gate_name_changed(self, sample_id: str, node_id: str, new_name: str) -> None:
    if self._current_sample_id == sample_id:
        # Update displayed gate info
        self._update_gate_display(node_id, new_name)
```

**Files:**
- [flow_cytometry/analysis/gate_controller.py](flow_cytometry/analysis/gate_controller.py)
- [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py)
- [flow_cytometry/ui/widgets/properties_panel.py](flow_cytometry/ui/widgets/properties_panel.py)
- [flow_cytometry/ui/main_panel.py](flow_cytometry/ui/main_panel.py) — Wire up all connections

**Complexity:** Medium (signal propagation + cross-sample coordination)  
**Risk:** Low — leverages existing signal architecture  
**Testing:** Rename gate on Sample A, verify immediately visible on Samples B, C, D in same group  

---

### **#7: Auto-Update Axis on Render Mode Change**

**Problem:**  
When toggling between Optimized and Transparent render modes, axis ranges don't auto-adjust. User might see a drastically different plot (some outliers now visible) but axis labels don't update.

**Current Behavior:**
1. Plot in Optimized mode (100K events, axis range computed from sample)
2. User switches to Transparent (5M events, now shows outliers)
3. Axis still shows old range → data appears compressed or clipped
4. User must manually invoke "Auto Range" button

**Solution:**

#### 7.1 Trigger Auto-Range on Quality Mode Change
**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L800)
```python
def _on_quality_mode_changed(self, mode: str) -> None:
    """Switch between optimized and transparent rendering."""
    self._render_quality = mode
    
    if mode == "optimized":
        self._max_events = 100_000
        self._quality_multiplier = 1.0
    elif mode == "transparent":
        self._max_events = None
        self._quality_multiplier = 2.0
    
    # Auto-update axis range based on new event set
    self._auto_range_axes()
    
    # Redraw immediately
    self._redraw()
```

#### 7.2 Make Auto-Range Default
**File:** [flow_cytometry/analysis/scaling.py](flow_cytometry/analysis/scaling.py)
- Add `auto_range_on_mode_change: bool = True` to `AxisScale` dataclass

**File:** [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py#L200)
```python
def __init__(self, ...):
    self._x_scale = AxisScale(auto_range=True)  # Default: auto
    self._y_scale = AxisScale(auto_range=True)
```

#### 7.3 Provide User Control
Add checkbox in properties panel: "🔗 Auto-range axes on mode change"  
- Default: ON
- Allows power users to disable if they prefer manual control

**Files:**
- [flow_cytometry/ui/graph/flow_canvas.py](flow_cytometry/ui/graph/flow_canvas.py)
- [flow_cytometry/analysis/scaling.py](flow_cytometry/analysis/scaling.py)
- [flow_cytometry/ui/widgets/properties_panel.py](flow_cytometry/ui/widgets/properties_panel.py)

**Complexity:** Low (existing auto-range logic + flag)  
**Risk:** Minimal — users can disable if unwanted  

---

### **#8: Event-Based Architecture for Long-Term Stability**

**Problem:**
Current architecture relies on:
- Direct method calls (tightly coupled)
- Signal/slot chains (can miss events if receiver isn't connected early)
- Manual state propagation (error-prone)

This makes it hard to:
- Add new features without spaghetti wiring
- Debug state mismatches
- Test components in isolation

**Desired Outcome:**
- Decouple components via **Event Bus**
- All state changes published as events
- UI/analysis logic subscribes to relevant events
- Easier testing, debugging, and future feature development

**Solution: Event-Based Architecture**

#### 8.1 Create Event System
**New File:** [flow_cytometry/analysis/event_bus.py](flow_cytometry/analysis/event_bus.py)
```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any
from PyQt6.QtCore import QObject, pyqtSignal

class EventType(Enum):
    """All possible events in the flow cytometry system."""
    # Gate events
    GATE_CREATED = "gate.created"
    GATE_RENAMED = "gate.renamed"
    GATE_DELETED = "gate.deleted"
    GATE_MODIFIED = "gate.modified"
    GATE_PROPAGATED = "gate.propagated"
    
    # Sample events
    SAMPLE_SELECTED = "sample.selected"
    SAMPLE_DESELECTED = "sample.deselected"
    SAMPLE_LOADED = "sample.loaded"
    
    # Canvas events
    RENDER_MODE_CHANGED = "render.mode_changed"
    AXIS_RANGE_CHANGED = "axis.range_changed"
    TRANSFORM_CHANGED = "transform.changed"
    
    # Statistics events
    STATS_COMPUTED = "stats.computed"
    STATS_INVALIDATED = "stats.invalidated"

@dataclass
class Event:
    """Base event object."""
    type: EventType
    data: dict[str, Any]
    source: str  # Component that emitted

class EventBus(QObject):
    """Central event dispatcher."""
    
    _event_signal = pyqtSignal(Event)
    
    def __init__(self):
        super().__init__()
        self._subscribers: dict[EventType, list[Callable]] = {}
    
    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Register handler for event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    def publish(self, event: Event) -> None:
        """Broadcast event to all subscribers."""
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")
    
    def clear(self) -> None:
        """Clear all subscriptions (for testing)."""
        self._subscribers.clear()
```

#### 8.2 Integrate EventBus into State
**File:** [flow_cytometry/analysis/state.py](flow_cytometry/analysis/state.py)
```python
@dataclass
class FlowState(PluginState):
    # ... existing fields ...
    event_bus: EventBus = field(default_factory=EventBus)
    
    def notify_gate_created(self, sample_id: str, node_id: str, gate_type: str) -> None:
        self.event_bus.publish(Event(
            type=EventType.GATE_CREATED,
            data={"sample_id": sample_id, "node_id": node_id, "gate_type": gate_type},
            source="state"
        ))
```

#### 8.3 Update GateController to Emit Events
**File:** [flow_cytometry/analysis/gate_controller.py](flow_cytometry/analysis/gate_controller.py)
```python
class GateController:
    def __init__(self, state: FlowState):
        self._state = state
        self._event_bus = state.event_bus
    
    def add_gate(self, sample_id: str, gate: Gate, parent_id: Optional[str] = None) -> None:
        # ... existing logic ...
        
        # Publish event instead of just signal
        self._event_bus.publish(Event(
            type=EventType.GATE_CREATED,
            data={
                "sample_id": sample_id,
                "node_id": node.id,
                "gate_type": type(gate).__name__,
                "gate_name": node.name
            },
            source="gate_controller"
        ))
```

#### 8.4 Subscribe UI Components to Events
**File:** [flow_cytometry/ui/widgets/gate_hierarchy.py](flow_cytometry/ui/widgets/gate_hierarchy.py)
```python
class GateHierarchy(QWidget):
    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        
        # Subscribe to relevant events
        state.event_bus.subscribe(EventType.GATE_CREATED, self._on_gate_created)
        state.event_bus.subscribe(EventType.GATE_RENAMED, self._on_gate_renamed)
        state.event_bus.subscribe(EventType.GATE_DELETED, self._on_gate_deleted)
    
    def _on_gate_created(self, event: Event) -> None:
        """Auto-update when gate is created."""
        if event.data["sample_id"] == self._active_sample_id:
            self._rebuild_tree()
```

#### 8.5 Benefits & Future-Proofing
- **Debugging:** Log all events → understand exact state transitions
- **Testing:** Mock EventBus, inject events, verify UI responses
- **New Features:** Add handlers without modifying existing code
- **Undo/Redo:** Replay events from history
- **Analytics:** Track user workflows

**Complexity:** High (architectural refactor)  
**Risk:** Medium — must integrate carefully to avoid breaking existing signals  
**Rollout:** Phase over multiple commits:
  1. Add EventBus alongside existing signals
  2. Gradually migrate one component at a time
  3. Remove old signals once complete

**Files to Create:**
- [flow_cytometry/analysis/event_bus.py](flow_cytometry/analysis/event_bus.py) — New

**Files to Modify (Phase 1):**
- [flow_cytometry/analysis/state.py](flow_cytometry/analysis/state.py)
- [flow_cytometry/analysis/gate_controller.py](flow_cytometry/analysis/gate_controller.py)

**Files to Modify (Phase 2+):**
- All UI components in [flow_cytometry/ui/widgets/](flow_cytometry/ui/widgets/)
- [flow_cytometry/ui/graph/](flow_cytometry/ui/graph/)

---

## Implementation Priority & Timeline

### **Phase 1: Crash Fix + Quick Wins** (1-2 hours)
- ✅ **#6:** Sample list NoneType crash → ~2 min
- ✅ **#1:** Default to Global Strategy → ~10 min
- ✅ **#4:** Tab close button for samples → ~20 min
- ✅ **#3:** Right-click copy/download → ~30 min

### **Phase 2: Feature Improvements** (3-4 hours)
- ✅ **#2:** Render quality toggle → ~60 min (includes testing)
- ✅ **#5:** Gate naming propagation → ~45 min
- ✅ **#7:** Auto-range on mode change → ~20 min

### **Phase 3: Architecture (Ongoing)** (2-3 sprints)
- ✅ **#8:** Event-based system → Design in sprint 1, implement over 2-3 sprints

### **Total Estimated Effort:**
- **Phase 1:** ~1 hour (critical fixes)
- **Phase 2:** ~2.5 hours (features)
- **Phase 3:** ~2-3 sprints (architecture, can be parallelized with other work)

---

## Risk Mitigation

| Issue | Risk | Mitigation |
|-------|------|-----------|
| NoneType crash (#6) | Minimal | Guard clause is safe, non-breaking |
| Global Strategy default (#1) | Low | Store preference, easy to revert |
| Render quality toggle (#2) | Medium | Requires testing both modes; phantom events possible | Test with real FCS files; validate cache invalidation |
| Gate naming (#5) | Medium | Cross-sample updates might miss subscribers | Verify all dependent UI updates; add logging |
| Event bus (#8) | Medium-High | Large refactor; must not break existing signals | Phase migration; keep signals during transition |

---

## Testing Checklist

- [ ] **#6:** Bulk-gate 1 sample to 9 others without crash
- [ ] **#1:** Verify Global Strategy is default; toggle persists across sessions
- [ ] **#2:** Optimized mode renders fast; Transparent shows all events; toggle doesn't corrupt data
- [ ] **#3:** Copy/download buttons work; file formats are correct
- [ ] **#4:** Tab close button removes tab; sample is deselected
- [ ] **#5:** Rename gate on Sample A → appears immediately on Samples B, C
- [ ] **#7:** Switch render mode → axis auto-updates; option to disable works
- [ ] **#8:** All events logged; subscribers receive events in correct order

---

## Questions for Approval

1. **Timeline:** Is Phase 1 (1 hour crash fixes + quick wins) acceptable to land first, before features?
2. **Event Bus:** Should we phase the architecture refactor, or integrate it all at once?
3. **Render Quality Default:** Should "Optimized" be default, or should we remember last-used mode per plot type?
4. **Gate Propagation:** Should renamed gates update globally, or only within the same sample group?

---

**Status:** ⏳ **Awaiting Approval**

Please review and provide feedback. Once approved, I'll create individual PRs for each phase.
