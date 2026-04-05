# BioPro Module Author Guide

BioPro's core strength is its extensible plugin architecture, allowing researchers and developers to build specialized analysis pipelines without touching the foundational codebase. Anyone can write an analysis module (a "plugin"), and it will seamlessly integrate into the BioPro Hub. 

By building a BioPro plugin, your code automatically inherits the core's built-in file management, non-destructive history tracking (Undo/Redo), global theming engine, and workflow serialization.

---

## 1. File Structure Requirements

When creating a new module, you must strictly follow this folder hierarchy. BioPro's `ModuleManager` expects this exact layout to validate and hot-load your plugin.

```text
my_awesome_plugin/
├── manifest.json         # Required metadata for the Hub
├── __init__.py           # The entry point
├── README.md             # Required documentation explaining the module
├── ui/                   # All PyQt6 user interface code
│   ├── main_panel.py     # Your primary QWidget/Wizard
│   └── widgets/
└── analysis/             # All scientific/backend logic
    └── core_math.py      # Agnostic python classes
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
The dynamic loader will directly import this file. It **MUST** export a single function `get_panel_class()`:
```python
"""My Awesome Plugin entry point."""

def get_panel_class():
    """Returns the main QWidget class that should be injected into the UI."""
    # Ensure this import is RELATIVE
    from .ui.main_panel import MyMainPanel 
    return MyMainPanel
```

---

## 2. API & Interface Requirements

When BioPro launches your plugin, it instances the class returned by `get_panel_class()`. This class MUST inherit from `QWidget` (or `QFrame`, `QWizard`, etc.) and adhere to the strict protocol defined below.

### Standardized Methods

Implementation of these methods is mandatory to allow the Core Application to manage your data state. Note that your class is placed directly into the main workspace as a single unified widget; if you require an image canvas, sidebars, or splitters, you must create and arrange them yourself inside your panel class.

- `export_state(self) -> dict`
  Packages your entire UI and scientific state into a deep-copyable Python dictionary. This is heavily utilized by the Core's `HistoryManager` to capture invisible snapshots of your tool.

- `load_state(self, state_dict: dict) -> None`
  Takes a dictionary previously produced by `export_state` and instantly redraws your UI and calculations to match it. **If you implement this correctly, BioPro automatically grants your plugin full native CTRL+Z (Undo/Redo) support.**

- `export_workflow(self) -> dict`
  Similar to state extraction, but explicitly returns a JSON-serializable dictionary. This is triggered when a user desires to save out the session to disk.

- `load_workflow(self, payload: dict) -> None`
  Reconstructs the full analysis pipeline from a saved JSON payload, refreshing images and recalculating output arrays.

### Required Signals (PyQt6)

To communicate with the host window without creating hard dependencies, your panel **MUST** define and arbitrarily emit the following `pyqtSignal` objects:

```python
from PyQt6.QtCore import pyqtSignal

class MyMainPanel(QWidget):
    state_changed = pyqtSignal()
    status_message = pyqtSignal(str)
    results_ready = pyqtSignal(object)
```

1. **`state_changed`**: Emit this ANY time the user makes a destructive/structural edit (drawing a box, changing a threshold, moving an anchor). BioPro will instantly call your `export_state()` and record it to the Undo stack.
2. **`status_message(message: str)`**: Emit text to this signal to cleanly pipe tool tips and updates to the user's primary status bar at the bottom of the screen.
3. **`results_ready(payload: object)`**: Optionally emit this to pass final analysis data back to the core host if you are integrating with global reporting systems.

---

## 3. Core UI Integration & Theming

To maintain the illusion of a single, coherent application, you must use BioPro's standard styling framework instead of writing custom CSS rules.

### Colors & Fonts
Import `Colors` and `Fonts` directly from the central theme manager. Because BioPro supports dynamic hot-swapping of themes, you must interpolate these variables into your stylesheets.

```python
from biopro.ui.theme import Colors, Fonts

my_label = QLabel("Analysis Setup")
my_label.setStyleSheet(
    f"color: {Colors.FG_PRIMARY}; "
    f"font-size: {Fonts.SIZE_LARGE}px; "
    f"font-weight: bold;"
)

my_panel.setStyleSheet(f"background-color: {Colors.BG_DARKEST}; border: 1px solid {Colors.BORDER};")
```

### BioPro SDK Widgets
Do not use raw `QPushButton` for forms! Import the semantic buttons provided by the core SDK. They automatically handle edge cases, disabled states, and hover animations based on the active Theme.

```python
from biopro.shared.ui.ui_components import PrimaryButton, SecondaryButton, DangerButton

btn_compute = PrimaryButton("Compute Density")
btn_cancel = SecondaryButton("Cancel")
btn_delete = DangerButton("Remove Outlier")
```

---

## 4. Code Style Requirements

We ask module authors to respect strict software engineering standards so the ecosystem remains clean.

1. **Separation of Concerns (SOLID)**: 
   You must strictly decouple your PyQt interface from your scientific calculations. A `QPushButton.clicked` should not loop over numpy arrays; it should hand the data to an object in your `analysis/` folder, wait for the return, and then update the UI.
2. **Import Rules**: 
   - You MUST use **relative imports** when referencing your own plugin's files (e.g. `from .ui.my_panel import MyPanel`). Do not use absolute imports (e.g. `from biopro.plugins.my_awesome_plugin...`), as the namespace path may change depending on how the Core dynamically maps user folders.
   - You MUST use **absolute imports** when requesting tools from the core application (e.g. `from biopro.core.history_manager import HistoryManager`).
3. **Type Hinting**: All public methods in the plugin should include standard Python type hints.
4. **Docstrings**: Adhere to PEP 8 docstring formats. Describe the parameters, behavior, and return values of your scientific algorithms so other researchers can audit them.

---

## 5. Documentation Requirements

A BioPro module is useless if a scientist doesn't understand the underlying mathematics.

Your plugin folder **MUST** contain a `README.md`. It must actively cover:
1. **The Biological Problem**: What does this module measure or characterize?
2. **Usage Guide**: A 1-2-3 step workflow explaining how to click through your Wizard or interface.
3. **Algorithmic Transparency**: Be explicit about the operations destroying/mutating pixel data. (e.g., "Lane detection uses `scipy.signal.find_peaks` with a prominence threshold of X... Background subtraction utilizes the rolling ball method...").
4. **Citations**: If you are implementing a published methodology, provide the DOI string and authors so users can cite the primary literature alongside your tool.
