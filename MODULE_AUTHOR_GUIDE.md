# BioPro Module Author Guide

BioPro's core strength is its extensible plugin architecture, allowing researchers and developers to build specialized analysis pipelines without touching the foundational codebase. The **BioPro SDK** provides everything you need to build plugins that automatically integrate with file management, undo/redo history, theming, and workflow persistence.

This guide clarifies:
- **What you MUST implement** (your domain-specific logic and UI)
- **What the SDK provides for you** (core infrastructure and utilities)

---

## Quick Start

```python
from biopro.sdk.core import PluginBase, PluginState, AnalysisBase
from biopro.sdk.ui import PrimaryButton, WizardStep, WizardPanel
from dataclasses import dataclass

# 1. Define your state
@dataclass
class MyState(PluginState):
    image_path: str = ""
    threshold: float = 0.5

# 2. Define your analysis
class MyAnalyzer(AnalysisBase):
    def run(self, state: MyState) -> dict:
        # Your analysis logic here
        return {"result": compute_something(state)}

# 3. Define your UI
class MyPlugin(PluginBase):
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.state = MyState()
        self.analyzer = MyAnalyzer(plugin_id)
        # Build UI with PrimaryButton, WizardPanel, etc.
    
    def get_state(self) -> PluginState:
        return self.state
    
    def set_state(self, state: PluginState) -> None:
        self.state = state
        # Update UI from state
```

---

## 1. File Structure Requirements

When creating a new module, follow this folder hierarchy. BioPro's `ModuleManager` expects this layout to validate and hot-load your plugin.

```text
my_awesome_plugin/
├── manifest.json         # Required: Plugin metadata (signed)
├── signature.bin         # Required: Ed25519 signature
├── dev_cert.bin          # Required: Developer trust certificate
├── __init__.py           # Required: Entry point with get_panel_class()
├── README.md             # Required: Documentation
├── ui/                   # Your PyQt6 UI code
│   ├── main_panel.py     # Your main plugin class (inherit from PluginBase)
│   └── widgets/          # Optional: Custom UI components
└── analysis/             # Your domain-specific logic (NO PyQt6 here!)
    └── analyzer.py       # Analysis classes (inherit from AnalysisBase)
```

### `manifest.json`
Every module must have a manifest for the BioPro Plugin Store and Hub to discover it:
```json
{
    "id": "my_awesome_plugin",
    "name": "My Awesome Plugin",
    "description": "A robust module for analyzing cellular structures.",
    "version": "1.0.0",
    "min_core_version": "1.0.0",
    "icon": "🔬"
}
```

### `__init__.py`
The dynamic loader will import this file. It **MUST** satisfy the **BioProPlugin Interface Contract** by exporting these attributes:

```python
"""My Awesome Plugin entry point."""

__version__ = "1.0.0"          # MUST match manifest.json
__plugin_id__ = "my_awesome_plugin"  # MUST match manifest.json

def get_panel_class():
    """Returns the main QWidget class to inject into the UI."""
    from .ui.main_panel import MyMainPanel 
    return MyMainPanel
```

---

## 2. SDK Components: What the Framework Provides

### 2.1 Core Module (`biopro.sdk.core`)

The SDK provides these base classes and utilities that handle all the infrastructure:

#### PluginSignals
Standard signals for plugin-to-host communication. **You don't inherit this directly—PluginBase does it for you.**

```python
from biopro.sdk.core import PluginSignals

# Automatically available as properties on your PluginBase subclass:
# - status_message(str)     → Updates UI status bar
# - state_changed()         → Triggers undo/redo capture
# - log_message(str)        → Logs detailed messages
# - analysis_started()      → Analysis began
# - analysis_progress(int)  → Progress 0-100
# - analysis_complete()     → Analysis finished
# - analysis_error(str)     → Error occurred
# - data_changed()          → Some data changed
```

#### PluginState
Base class for serializable state objects. Use `@dataclass` for automatic serialization.

```python
from biopro.sdk.core import PluginState
from dataclasses import dataclass

@dataclass
class MyAnalysisState(PluginState):
    """Your state definition—keep it simple!"""
    image_path: str = ""
    threshold: float = 0.5
    results: list = None
    
    # to_dict() and from_dict() are auto-implemented by PluginState
    # This enables automatic undo/redo and workflow persistence
```

**Key constraint:** State fields should be JSON-serializable (strings, numbers, lists, dicts). Store paths as strings, not Path objects.

#### AnalysisBase
Abstract base for your analysis logic. **This is domain-specific—you MUST subclass it.**

```python
from biopro.sdk.core import AnalysisBase, PluginState

class MyAnalyzer(AnalysisBase):
    """Your analysis logic goes here. NO UI code!"""
    
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
    
    def run(self, state: PluginState) -> dict:
        """Implement your analysis algorithm.
        
        Args:
            state: Your PluginState subclass with parameters
            
        Returns:
            Dict with results to merge back into state
        """
        # Your algorithm here
        results = process_image(state.image_path)
        return {"results": results, "error_count": 0}
    
    def validate(self, state: PluginState) -> tuple[bool, str]:
        """Optional: Validate state before running analysis.
        
        Returns:
            (is_valid, error_message)
        """
        if not state.image_path:
            return False, "Image path is required"
        return True, ""
```

#### AnalysisWorker & TaskScheduler
The SDK manages background execution via a centralized `TaskScheduler`. This prevents individual plugins from exhausting system resources by spawning too many threads.

```python
from biopro.core import task_scheduler

# Create analyzer and state
analyzer = MyAnalyzer("my_plugin")
state = MyState(...)

# Submit to the global pool
task_id = task_scheduler.submit(analyzer, state)
```

#### FunctionalTask (for Utility Operations)
If you need to run a task that doesn't follow the full `AnalysisBase` lifecycle (e.g., downloading a reference file, cleaning up a directory), use the `FunctionalTask` wrapper:

```python
from biopro.sdk.core import FunctionalTask
from biopro.core import task_scheduler

def my_network_task():
    # Do some I/O or networking...
    return {"status": "Complete"}

# Wrap and submit
task = FunctionalTask("my_plugin", my_network_task, name="Download Params")
task_id = task_scheduler.submit(task, None) # No state required
```

> [!TIP]
> The `TaskScheduler` uses a global thread pool. You don't need to create `QThread` objects manually anymore!

#### PluginBase
**You MUST subclass this for your main plugin UI class.** It provides state management and undo/redo integration.

```python
from biopro.sdk.core import PluginBase, PluginState

class MyPlugin(PluginBase):
    """Your main plugin panel."""
    
    def __init__(self, plugin_id: str, parent=None):
        super().__init__(plugin_id, parent)
        self.state = MyAnalysisState()
        self.analyzer = MyAnalyzer(plugin_id)
        # Build your UI here
    
    def get_state(self) -> PluginState:
        """MUST IMPLEMENT: Return your current state."""
        return self.state
    
    def set_state(self, state: PluginState) -> None:
        """MUST IMPLEMENT: Restore UI from state during undo/redo."""
        self.state = state
        self._update_ui()
    
    def _on_user_edits_something(self):
        """When user makes destructive changes, capture state for undo."""
        self.push_state()  # Inherited from PluginBase
        # BioPro automatically captures the state for undo/redo
```

### 2.2 UI Module (`biopro.sdk.ui`)

Semantic UI components that respect the active theme automatically.

#### Buttons

```python
from biopro.sdk.ui import PrimaryButton, SecondaryButton, DangerButton

btn_run = PrimaryButton("Run Analysis")      # Main action (accent color)
btn_cancel = SecondaryButton("Cancel")       # Secondary action (outline)
btn_delete = DangerButton("Delete Results")  # Destructive action (red)
```

#### Labels & Cards

```python
from biopro.sdk.ui import HeaderLabel, SubtitleLabel, ModuleCard

title = HeaderLabel("Analysis Results")      # H1 header
subtitle = SubtitleLabel("Lane Detection")   # H2 subtitle
card = ModuleCard()                          # Styled card for lists
```

#### Wizard Framework

Create multi-step interfaces without boilerplate:

```python
from biopro.sdk.ui import WizardStep, WizardPanel

class InputStep(WizardStep):
    label = "Input Parameters"
    
    def build_page(self, panel: WizardPanel):
        """Build the UI for this step."""
        page = QWidget()
        layout = QVBoxLayout(page)
        # Add your controls here
        return page
    
    def on_next(self, panel: WizardPanel) -> bool:
        """Validate and advance. Return False to block navigation."""
        # Validate user input
        if not self.validate():
            self.show_error("Invalid input")
            return False
        return True

class AnalysisStep(WizardStep):
    label = "Running Analysis"
    is_terminal = True  # Final step
    
    def build_page(self, panel: WizardPanel):
        return QLabel("Processing...")
    
    def on_next(self, panel: WizardPanel) -> bool:
        # Run analysis
        panel.analyzer.run(panel.state)
        return True

# Create wizard UI
steps = [InputStep(), AnalysisStep()]
wizard = WizardPanel(steps, title="My Analysis Workflow")
```

### 2.3 Utils Module (`biopro.sdk.utils`)

Utilities for common tasks: dialogs, I/O, validation.

#### Dialogs

```python
from biopro.sdk.utils import (
    get_image_path,
    get_save_path,
    get_directory,
    show_info,
    show_error,
    ask_yes_no,
)

image_path = get_image_path(self, "Select Image")
save_path = get_save_path(self, "Save Results", file_filter="CSV (*.csv)")
dir_path = get_directory(self, "Select Directory")

if ask_yes_no(self, "Confirm", "Proceed with analysis?"):
    show_info(self, "Success", "Analysis complete!")
else:
    show_error(self, "Cancelled", "Operation aborted")
```

#### Configuration Management

```python
from biopro.sdk.utils import PluginConfig

config = PluginConfig("my_awesome_plugin")
config.set("threshold", 0.5)
config.set("last_image_dir", "/path/to/images")
config.save()

# Later...
config.load()
threshold = config.get("threshold", default=0.3)
```

#### Validation

```python
from biopro.sdk.utils import (
    validate_file_exists,
    validate_value_range,
    validate_not_empty,
)

is_valid, error_msg = validate_file_exists(path)
is_valid, error_msg = validate_value_range(value, min=0.0, max=1.0, name="threshold")
is_valid, error_msg = validate_not_empty(user_input)

if not is_valid:
    show_error(self, "Invalid Input", error_msg)
```

### 2.4 Contrib Module (`biopro.sdk.contrib`)

Optional utilities for common analysis tasks. Currently includes image processing:

```python
from biopro.sdk.contrib import (
    load_and_convert,
    adjust_contrast,
    auto_detect_inversion,
    invert_image,
    enhance_for_band_detection,
    rotate_image,
)

# Load and normalize image to float64 [0.0, 1.0]
image = load_and_convert("blot.tiff", as_grayscale=True)

# Auto-detect if image needs inversion
if auto_detect_inversion(image):
    image = invert_image(image)

# Enhance for detection
image = enhance_for_band_detection(
    image,
    apply_clahe=True,
    clahe_clip_limit=2.0,
    denoise_median_ksize=5,
)
```

---

## 3. What You MUST Implement

### 3.1 Your Main Plugin Class

Inherit from `PluginBase` and implement the two abstract methods:

```python
from biopro.sdk.core import PluginBase, PluginState
from PyQt6.QtWidgets import QWidget, QVBoxLayout

class MyPlugin(PluginBase):
    """Entry point for your plugin."""
    
    def __init__(self, plugin_id: str, parent=None):
        super().__init__(plugin_id, parent)
        self.state = MyState()
        self.analyzer = MyAnalyzer(plugin_id)
        self._build_ui()
    
    def _build_ui(self):
        """Build your user interface."""
        layout = QVBoxLayout(self)
        # Add your widgets here
    
    def get_state(self) -> PluginState:
        """Return current state for undo/redo."""
        # Sync UI values into state
        self.state.threshold = self.threshold_spinbox.value()
        return self.state
    
    def set_state(self, state: PluginState) -> None:
        """Restore state during undo/redo."""
        self.state = state
        # Update all UI elements from state
        self.threshold_spinbox.setValue(self.state.threshold)
```

### 3.2 Your Analysis Class

Inherit from `AnalysisBase` and implement `run()`:

```python
from biopro.sdk.core import AnalysisBase, PluginState
import numpy as np

class MyAnalyzer(AnalysisBase):
    """Your domain-specific analysis logic."""
    
    def run(self, state: PluginState) -> dict:
        """Implement your algorithm. NO UI CODE HERE!"""
        # Load data from paths in state
        image = np.load(state.image_path)
        
        # Run your analysis
        results = my_algorithm(image, state.threshold)
        
        # Return results to merge back into state
        return {
            "results": results,
            "num_peaks": len(results),
            "processing_time_ms": 1234,
        }
    
    def validate(self, state: PluginState) -> tuple[bool, str]:
        """Optional: Validate state before analysis."""
        if not state.image_path:
            return False, "Image path not set"
        if state.threshold < 0 or state.threshold > 1:
            return False, "Threshold must be 0-1"
        return True, ""
```

### 3.3 Your State Class

Use `@dataclass` with `PluginState` for automatic serialization:

```python
from biopro.sdk.core import PluginState
from dataclasses import dataclass

@dataclass
class MyState(PluginState):
    """Immutable state snapshot for one analysis session."""
    image_path: str = ""
    threshold: float = 0.5
    results: list = None
    
    # PluginState provides:
    # - to_dict() → serializable dict
    # - from_dict(dict) → reconstruct instance
    # These enable automatic undo/redo!
```

### 3.4 The Interface Contract (Track 1 Solidification)

BioPro now enforces a strict structural protocol for all plugins using PEP 544 Protocols. This ensures that the `ModuleManager` can safely load and interact with your code without runtime attribute errors.

Your plugin's entry point (`__init__.py`) **must** satisfy the `BioProPlugin` protocol:

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `__version__` | `str` | The semantic version of the plugin. |
| `__plugin_id__` | `str` | Unique identifier (must match folder name and manifest). |
| `get_panel_class()` | `Callable` | Function returning the main `QWidget` class. |

> [!IMPORTANT]
> Failure to implement these three components will cause the `ModuleManager` to raise a `TypeError` during loading, and your plugin will not appear in the BioPro UI.
```

---

## 4. Theming & UI Integration

Always use BioPro's theme system to stay visually consistent:

```python
from biopro.ui.theme import Colors, Fonts
from biopro.sdk.ui import PrimaryButton

# Use theme colors in stylesheets
label = QLabel("Status")
label.setStyleSheet(f"color: {Colors.FG_PRIMARY}; font-size: {Fonts.SIZE_LARGE}px;")

# Use semantic components (they handle theming automatically)
btn = PrimaryButton("Run")  # Respects active theme
```

---

## 5. SOLID Principles in Your Plugin

### Single Responsibility
- **UI layer** (`ui/main_panel.py`): Only handle PyQt6 widgets and display
- **Analysis layer** (`analysis/analyzer.py`): Only handle algorithm logic

### Dependency Inversion
Depend on abstractions, not concrete implementations:

```python
# ✗ BAD: Tightly coupled
class MyPlugin(QWidget):
    def __init__(self):
        self.analyzer = MyConcreteAnalyzer()  # Hard dependency

# ✓ GOOD: Abstracted
class MyPlugin(PluginBase):
    def __init__(self, plugin_id: str, analyzer: AnalysisBase = None):
        super().__init__(plugin_id)
        self.analyzer = analyzer or MyAnalyzer(plugin_id)
```

### Separation of Concerns
Never mix UI and analysis:

```python
# ✗ BAD: Analysis in UI event handler
def on_button_clicked(self):
    results = run_my_algorithm(self.image)  # Processing in UI thread
    self.results_label.setText(str(results))

# ✓ GOOD: Use background worker
def on_button_clicked(self):
    worker = AnalysisWorker(self.analyzer, self.state)
    thread = QThread()
    worker.moveToThread(thread)
    worker.finished.connect(self._on_analysis_done)
    thread.started.connect(worker.run)
    thread.start()

def _on_analysis_done(self, results):
    self.results_label.setText(str(results))
```

---

## 6. Documentation Requirements

Your plugin folder **MUST** contain a `README.md`. Document:

1. **The Biological Problem**: What does this module measure or characterize?
2. **Usage Guide**: 1-2-3 workflow explaining how to use your interface
3. **Algorithmic Transparency**: Be explicit about operations on data:
   - "Lane detection uses `scipy.signal.find_peaks` with prominence threshold X"
   - "Background subtraction uses rolling ball method from Y paper"
4. **Citations**: If implementing published methodology, provide DOI and authors

Example structure:
```markdown
# My Awesome Plugin

## What It Does
Detects and characterizes protein bands in Western blot images using...

## Usage
1. Click "Load Image" and select your blot image
2. Adjust lane detection sensitivity with the slider
3. Click "Run Analysis" to detect bands
4. Review results and export as CSV

## Algorithm
Lane detection: scipy.signal.find_peaks with prominence=2.0
Band detection: Custom convolution-based method
Intensity quantification: Integrated pixel intensity within ROI

## References
- Smith et al. (2020) "Advanced Band Detection" DOI:10.1234/example
```

---

## 7. Common Patterns & Examples

### Pattern: Loading & Displaying an Image

```python
from biopro.sdk.utils import get_image_path, show_error
from biopro.sdk.contrib import load_and_convert
from biopro.sdk.core import PluginBase

class MyPlugin(PluginBase):
    def __init__(self, plugin_id: str, parent=None):
        super().__init__(plugin_id, parent)
        btn_load = PrimaryButton("Load Image")
        btn_load.clicked.connect(self._on_load_image)
    
    def _on_load_image(self):
        path = get_image_path(self, "Select Image")
        if path:
            try:
                self.state.image_path = path
                self.push_state()  # Capture for undo/redo
            except Exception as e:
                show_error(self, "Error", str(e))
```

### Pattern: Long-Running Analysis (Recommended)

Use the `task_scheduler` to run heavy computation without blocking the UI thread.

```python
from biopro.core import task_scheduler
from biopro.sdk.utils import show_error

def _on_run_analysis(self):
    # 1. Validate state
    is_valid, error = self.analyzer.validate(self.state)
    if not is_valid:
        show_error(self, "Invalid Input", error)
        return
    
    # 2. Submit to central scheduler
    self.status_message.emit("Analyzing...")
    
    # The scheduler handles thread creation and lifecycle
    self.current_task_id = task_scheduler.submit(self.analyzer, self.state)
    
    # 3. Connect to scheduler signals (filtered by task_id if needed)
    task_scheduler.task_finished.connect(self._on_analysis_done)
    task_scheduler.task_error.connect(self._on_analysis_error)

def _on_analysis_done(self, task_id, results):
    if task_id != self.current_task_id:
        return
    self.state.results = results
    self.push_state()
    self.status_message.emit("Analysis complete!")

def _on_analysis_error(self, task_id, error_msg):
    if task_id != self.current_task_id:
        return
    show_error(self, "Analysis Failed", error_msg)
```

### Pattern: Manual Threading (Legacy)

> [!WARNING]
> This pattern is deprecated. Use `TaskScheduler` for better resource management.

```python
# Legacy QThread pattern
worker = AnalysisWorker(self.analyzer, self.state)
self.thread = QThread()
worker.moveToThread(self.thread)
self.thread.started.connect(worker.run)
self.thread.start()
```

---

## 8. Security & Trust Architecture (Phase 4)

To protect users from malicious code and ensure scientific integrity, BioPro enforces a **Chain of Trust**. Plugins that are not cryptographically signed or have been tampered with will not be loaded.

### 8.1 Filesystem Integrity

BioPro uses **Merkle-Integrity Hashing**. Every file in your plugin (scripts, assets, configurations) is hashed and recorded in the `manifest.json`.

- **Strict Mode**: If any `.py` file is added, removed, or modified after signing, the plugin is rejected.
- **Smart Leeway**: Common system files (like `__pycache__` or `.DS_Store`) are automatically ignored to avoid false negatives.
- **Handling Runtime Data**: By default, BioPro ignores folders named `cache/`, `results/`, `output/`, `temp/`, and `logs/`. If your plugin generates data at runtime, ensure it is stored within one of these directories.

### 8.2 Custom Integrity Exclusions

If your plugin needs to generate data in a non-standard directory, you must declare it in your `manifest.json` before signing:

```json
{
    "id": "my_plugin",
    "integrity": {
        "exclusions": ["custom_data_dir/"]
    }
}
```

> [!WARNING]
> Never exclude directories containing executable code (`.py` files). Exclusions are intended for scientific data, logs, and temporary caches only.

### 8.3 Signing Your Plugin

Once your plugin is ready for distribution, use the BioPro SDK utility to sign it:

```bash
# Generate hashes and sign the manifest
biopro sdk sign path/to/your_plugin path/to/your_private_key.pem path/to/your_cert.bin
```

This will create:
1. `signature.bin`: The Ed25519 signature of your manifest.
2. `dev_cert.bin`: Your developer certificate (signed by the BioPro Root).

> [!IMPORTANT]
> Never share your Private Key. Anyone with access to your key can sign malicious code in your name.

---

## 10. Memory Management & RAII (Phase 5)

BioPro is designed to handle massive scientific datasets (large TIFs, multi-GB multi-dimensional arrays) without exhausting system RAM. As a developer, the framework handles most of this for you automatically.

### 10.1 Transparent Deduplication

When you call `self.push_state()`, BioPro's **HistoryManager** automatically inspects your state for "heavy" objects (like Numpy arrays or Torch tensors).

- **Structural Sharing**: If a large array hasn't changed between two history steps, BioPro only stores a single reference to it.
- **Impact**: You can allow users to perform 100+ undo/redo steps on a 100MB image without consuming 10GB of RAM. It just works.

### 10.2 Lifecycle Hooks (`cleanup` & `shutdown`)

If your plugin manages extremely specialized resources (like GPU-resident models or network sockets), you can override the lifecycle hooks:

```python
class MyPlugin(PluginBase):
    def cleanup(self) -> None:
        """Called when this specific tab is closed."""
        # 1. Core-led cleanup (automatic)
        super().cleanup() 
        
        # 2. Your custom cleanup
        self.my_local_cache.clear()

    def shutdown(self) -> None:
        """Called when the plugin is uninstalled or app exits."""
        # Release global resources like GPU-resident models
        if hasattr(self, 'model'):
            self.model.to('cpu')
            del self.model
```

### 10.3 Automatic "Self-Cleansing"

Even if you don't implement `cleanup()`, BioPro's **ResourceInspector** will scan your plugin instance and its state when the tab is closed. It will automatically null-out large arrays, unclosed file handles, and Matplotlib figures to ensure the Python Garbage Collector can reclaim memory immediately.

---

## Summary

### You Write
- Your `PluginBase` subclass with `get_state()` and `set_state()`
- Your `AnalysisBase` subclass with `run()` method
- Your `PluginState` dataclass definition
- Your UI using PyQt6 and SDK components
- Your `README.md` documentation

### The SDK Provides
- State management and undo/redo integration
- Serialization and workflow persistence
- Semantic UI components with automatic theming
- Dialog and file I/O utilities
- Validation helpers
- Background worker support
- Image processing utilities (contrib)
- All standard PyQt6 signals and lifecycle

Start with the Quick Start example above and expand from there!
