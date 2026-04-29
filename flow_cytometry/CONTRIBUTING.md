# Flow Cytometry Module Contributing Guidelines

Welcome to the Flow Cytometry module for BioPro! To maintain a high quality, readable, and maintainable codebase, please adhere to the following conventions when contributing to this module.

## 1. Naming Conventions

### Files and Directories
*   **Modules:** `snake_case.py` (e.g., `gate_factory.py`, `fcs_io.py`)
*   **Directories:** `snake_case/` (e.g., `analysis/`, `renderers/`)

### Code Elements
*   **Classes:** `PascalCase` (e.g., `GateController`, `RectangleGate`). Do not use redundant suffixes unless the class represents a specific architectural pattern (e.g., `PopulationService` is fine, but avoid `CoordinateMapperService` if it's just a utility class).
*   **Functions and Methods:** `snake_case` (e.g., `compute_statistic`, `apply_hierarchy`).
*   **Variables and Parameters:** `snake_case` (e.g., `total_events`, `sample_id`).
*   **Constants:** `UPPER_SNAKE_CASE` (e.g., `MAIN_PLOT_MAX_EVENTS`). **All constants must be defined in `analysis/constants.py`**; do not hardcode magic numbers inline or as class-level attributes.
*   **Private/Internal Elements:** Prefix with a single underscore `_` (e.g., `_walk_tree`, `_pending_gate_id`).

## 2. Docstrings

We use **Google-style docstrings** for all public modules, classes, and functions.

*   **Modules:** Every `.py` file must start with a module-level docstring explaining its purpose.
*   **Classes:** Describe what the class represents and list its public attributes.
*   **Functions/Methods:** Briefly describe what the function does. Include `Args:` and `Returns:` (and `Raises:` if applicable) sections for anything non-trivial.

Example:
```python
def compute_statistic(
    events: pd.DataFrame,
    param: Optional[str],
    stat_type: StatType
) -> float:
    """Compute a single statistic on a population.

    Args:
        events: Gated event DataFrame.
        param: Channel name (ignored for COUNT and % stats).
        stat_type: Which statistic to compute.

    Returns:
        The computed statistic as a float.
    """
```

## 3. Inline Comments

*   Add comments to complex algorithmic sections (e.g., density computations, Logicle transform fallback chains, complex UI coordinate mappings).
*   Avoid redundant comments that just restate the code. Focus on the *why*, not the *what*.

## 4. Import Ordering

Organize imports into the following groups, separated by a blank line:
1.  **Standard Library Imports** (e.g., `import os`, `import logging`, `from typing import Optional`)
2.  **Third-Party Imports** (e.g., `import numpy as np`, `import pandas as pd`, `from PyQt6.QtCore import QObject`)
3.  **BioPro SDK/Core Imports** (e.g., `from biopro.sdk.core import PluginState`)
4.  **Flow Cytometry Internal Imports** (e.g., `from .state import FlowState`, `from ..gating import GateNode`)

Always use `from __future__ import annotations` at the very top of the file (after the module docstring) to ensure forward-compatible type hinting.

## 5. Type Hinting

*   Use type hints for all function arguments and return values.
*   Since we use `from __future__ import annotations`, you can use built-in types for generics (e.g., `list[str]`, `dict[str, Any]`) instead of importing from `typing` (e.g., `List`, `Dict`).

## 6. Architecture & SOLID Principles

*   **Separation of Concerns:** The `analysis/` package must not contain any UI or PyQt dependencies. The `ui/` package must only contain UI presentation logic and connect to analysis objects.
*   **Single Responsibility Principle:** Keep classes and files focused on a single job.
*   **Dependency Inversion:** Depend on abstractions (like `DisplayStrategy` or `Gate`) rather than concrete implementations where possible.
