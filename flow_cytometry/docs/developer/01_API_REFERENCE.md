# Developer API Reference — Gating & Analysis

This document provides a technical reference for the core analysis engine of the BioPro Flow Cytometry module.

## 1. Gating Engine (`analysis/gating.py`)

The gating engine implements hierarchical point-in-polygon tests. All gates inherit from the `Gate` base class and provide a `contains(events: pd.DataFrame) -> np.ndarray[bool]` method.

### `RectangleGate`
Defines a 1D or 2D rectangular region in raw data space.
```python
RectangleGate(
    x_param: str,
    y_param: str,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    name: str = "",
    adaptive: bool = False
)
```

### `PolygonGate`
Defines an arbitrary shape using an ordered list of vertices. Points are automatically projected into display space during the `contains()` test to ensure visual parity on log/biexp scales.
```python
PolygonGate(
    x_param: str,
    y_param: str,
    vertices: list[tuple[float, float]],
    name: str = "",
    adaptive: bool = False
)
```

### `EllipseGate`
Defines an elliptical region.
```python
EllipseGate(
    x_param: str,
    y_param: str,
    center: tuple[float, float],
    width: float,
    height: float,
    angle: float = 0.0,
    name: str = "",
    adaptive: bool = False
)
```
*Note: `width` and `height` refer to the full axis lengths (not semi-axes).*

### `QuadrantGate`
Divides the plot into four quadrants based on a central pivot.
```python
QuadrantGate(
    x_param: str,
    y_param: str,
    x_mid: float,
    y_mid: float,
    name: str = ""
)
```

---

## 2. Transformations (`analysis/transforms.py`)

BioPro supports three primary transform types, controlled via the `TransformType` enum.

### `TransformType`
- `LINEAR`: Identity transform.
- `LOG`: Standard Base-10 log scaling.
- `BIEXPONENTIAL`: Implementation of the Parks 2006 Logicle algorithm.

### `biexponential_transform`
The core of our fluorescence visualization.
```python
biexponential_transform(
    data: np.ndarray,
    top: float = 262144.0,  # T parameter
    width: float = 1.0,     # W parameter
    positive: float = 4.5,  # M parameter
    negative: float = 0.0   # A parameter
)
```
The implementation utilizes `flowkit` (C-extension) if available, falling back to a high-fidelity `asinh` approximation.

---

## 3. Scaling & Ranges (`analysis/scaling.py`)

The `AxisScale` dataclass persists scale settings and transform parameters for a single channel.

### `AxisScale`
```python
@dataclass
class AxisScale:
    transform_type: TransformType
    min_val: float | None = None
    max_val: float | None = None
    logicle_t: float = 262144.0
    logicle_w: float = 1.0
    logicle_m: float = 4.5
    logicle_a: float = 0.0
    outlier_percentile: float = 0.1
```

### Robust Auto-Ranging
The module implements a robust auto-range algorithm that ignores outliers at the `outlier_percentile` level (default 0.1%) to prevent "squishing" of plots due to background noise or extreme artifacts.

---

## 🔗 Internal Links
- **[Architecture Overview](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/00_ARCHITECTURE_OVERVIEW.md)**
- **[UI Engine & Rendering](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/02_UI_ENGINE.md)**
- **[Testing & QA](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**
