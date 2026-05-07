# 🧬 (Archived) BioPro Plugin Ecosystem

**This repo is no longer in use. It is here for archival purposes only. Please refer to the core GitHub.**
Welcome to the official plugin repository for **BioPro**, the extensible, open-source bio-image analysis ecosystem. 

This repository is a **Monorepo** containing all official analysis modules (e.g., Western Blot, Protein Analyzer). BioPro's built-in `NetworkUpdater` fetches modules directly from this repository, allowing users to install only the tools they need.

---

## 🛠️ How to Build a BioPro Module

BioPro modules are fully decoupled from the Core application. They provide the mathematical analysis and a custom UI panel, while the BioPro Core handles file management, project states, theming, and the main window loop.

### 1. Module Folder Structure
Every new module must reside in its own folder at the root of this repository and follow this exact structure:

    biopro-plugins/
    └── your_module_name/          # Must be snake_case
        ├── manifest.json          # REQUIRED: Tells BioPro how to load the module
        ├── __init__.py            
        ├── analysis/              # Core scientific math/logic (Decoupled from UI)
        │   └── engine.py
        └── ui/                    # PyQt6 User Interface components
            └── main_panel.py      # The Entry Point referenced in manifest.json

### 2. The `manifest.json` (Required)
BioPro parses this file to display your module in the Store and to know which Python class to instantiate when the user clicks "Start Analysis".

Create a `manifest.json` in your module's root folder:

{
  "id": "your_module_name",
  "name": "Your Module Display Name",
  "version": "1.0.0",
  "description": "A brief description of what this analysis tool does.",
  "author": "Your Name/Lab",
  "icon": "🔬",
  "entry_point": "ui.main_panel.YourMainPanelClass",
  "tags": ["imaging", "quantification"]
}

*Note: The `entry_point` must be formatted as `relative.path.to.module.ClassName`.*

### 3. The Entry Point Class
The class defined in your `entry_point` must inherit from PyQt6's `QWidget` (or a BioPro shared UI class like `WizardPanel`). 

**Crucial Requirement:** The `__init__` method of your main class must accept a `project_manager` argument. BioPro Core injects this so your module can safely read/write to the user's active workspace.

**Example `ui/main_panel.py`:**

    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
    from biopro.ui.theme import Colors

    class YourMainPanelClass(QWidget):
        def __init__(self, project_manager, parent=None):
            super().__init__(parent)
            self.project_manager = project_manager # Save the injected core manager
            self._setup_ui()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            
            # Use BioPro's global theme variables
            title = QLabel("My Custom Analysis")
            title.setStyleSheet(f"color: {Colors.FG_PRIMARY}; font-size: 24px; font-weight: bold;")
            
            btn = QPushButton("Process Image")
            btn.setStyleSheet(f"background-color: {Colors.ACCENT_PRIMARY}; color: {Colors.BG_DARKEST};")
            btn.clicked.connect(self._run_analysis)
            
            layout.addWidget(title)
            layout.addWidget(btn)
            layout.addStretch()

        def _run_analysis(self):
            # Example of using the project_manager to get the workspace path
            workspace_path = self.project_manager.project_dir
            print(f"Saving results to {workspace_path}")

---

## ⚠️ The BioPro Import Contract

Because plugins are downloaded at runtime and injected into the compiled BioPro application, **you must obey strict import rules** to avoid `ModuleNotFoundError` crashes.

### Rule 1: Never use relative imports to access the Core.
If you need a BioPro Core component (like a dialog or theme), import it exactly as if BioPro were an installed PyPI library.

❌ **BAD (Will crash in production):**

    from ...ui.theme import Colors
    from ..core.project_manager import ProjectManager

✅ **GOOD:**

    from biopro.ui.theme import Colors
    from biopro.ui.dialogs import SaveWorkflowDialog

### Rule 2: Decouple Math from GUI
Do not put heavy scientific analysis (like Pandas DataFrame manipulation or OpenCV image processing) inside your PyQt button clicks. 
* Keep math in the `analysis/` folder.
* Keep PyQt in the `ui/` folder.
* *Why?* This allows BioPro to eventually be ported to a Web/Server environment without rewriting your scientific logic.

---

## 🎨 Utilizing the Core API

To ensure your module feels like a native part of BioPro, utilize the core resources exposed to plugins:

### Theming
Always use `biopro.ui.theme.Colors` instead of hardcoded hex codes. This ensures your plugin instantly adapts if the user switches to Dark Mode or the Star Wars theme.

    from biopro.ui.theme import Colors

    # Colors.BG_DARKEST (Main background)
    # Colors.FG_PRIMARY (Main text)
    # Colors.ACCENT_PRIMARY (Buttons, active states)

### Shared Dialogs
Need to save a workflow? Don't build a new popup. Use the core dialogs:

    from biopro.ui.dialogs import SaveWorkflowDialog

    dialog = SaveWorkflowDialog(self)
    if dialog.exec():
        metadata = dialog.get_data()

---

## 🧪 Testing Your Module Locally

You do not need to push to GitHub to test your module! 

1. Copy your module folder (e.g., `your_module_name/`) into your local BioPro installation's plugin directory:
   * **Mac/Linux:** `~/.biopro/plugins/`
   * **Windows:** `C:\Users\YourName\.biopro\plugins\`
2. Launch the BioPro desktop app.
3. BioPro will automatically parse the local `manifest.json` and display your module on the Home Screen. Check the terminal output for any syntax or import errors during loading.
