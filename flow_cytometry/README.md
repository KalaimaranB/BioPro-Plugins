# 🧪 Flow Cytometry Workspace

A scientist-centric flow cytometry analysis module for BioPro, designed as
a flexible alternative to traditional flow cytometry software with intelligent workflow support.

## Features

### Workspace Paradigm
- **3-zone layout**: Groups & Sample Tree (left), Graph Canvas (center),
  Properties & Statistics (right)
- **Toolbar ribbons**: Context-aware tabs — Workspace, Compensation,
  Gating, Statistics, Reports
- Fully interactive — no forced wizard path

### Analysis Engine (powered by FlowKit)
- **FCS Loading**: Supports FCS 2.0/3.0/3.1 via `flowkit.Sample`
- **Transforms**: Real Logicle/biexponential (Parks 2006, C extensions via
  `flowutils`), linear, and log — **no approximations**
- **Compensation**: Spillover matrix computation from single-stain controls
  and matrix application via inverse
- **Gating**: 5 gate types (Rectangle, Polygon, Ellipse, Quadrant, Range)
  with hierarchical tree support
- **Statistics**: 13+ stat types (Mean, MFI, CV, %Parent, %Total, etc.)

### Scientist-Centric Extensions
- **Sample Roles**: Tag each sample as Unstained, Single-Stain, FMO
  Control, Isotype Control, or Full Panel
- **Marker Mapping**: Explicit Marker → Fluorophore → Channel declarations
  with auto-axis labeling
- **Workflow Templates**: JSON-serializable experimental designs that can
  be saved, shared, and re-applied to new data
- **FMO Auto-Gate**: 99th percentile boundary detection from FMO controls

### Visualization (6 display modes)
- Pseudocolor (hexbin density) — canonical density-style view
- Dot Plot (subsampled scatter)
- Contour (2D histogram with smoothing)
- Density (KDE-based)
- Histogram (1-D)
- CDF (cumulative distribution)

## Dependencies

This plugin requires the following packages to be installed in the
BioPro Core environment:

```
flowkit       # FCS I/O, transforms, compensation, GatingML
flowio        # FCS parsing (flowkit dependency)
flowutils     # C-extension transforms (flowkit dependency)
numpy
pandas
matplotlib
scipy
```

## Documentation

The documentation suite is organized into two primary silos:

- **[📖 User Documentation (For Scientists)](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/INDEX.md)**: Intro, Getting Started, Analysis Guide, and Scientific Logic.
- **[🛠️ Developer Documentation (For Engineers)](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/INDEX.md)**: Architecture, API Reference, UI Engine, and Testing Guide.

---

## Architecture

```
flow_cytometry/
├── manifest.json              # Plugin metadata + dependency list
├── __init__.py                # get_panel_class() entry point
├── README.md
├── ANALYSIS_ROADMAP.md        # Full implementation roadmap
├── analysis/                  # Pure Python — no GUI dependencies
│   ├── fcs_io.py              # FlowKit-backed FCS loading
│   ├── compensation.py        # Spillover matrix engine
│   ├── gating.py              # Gate types + hierarchical tree
│   ├── statistics.py          # Population statistics
│   ├── experiment.py          # Experiment model + workflow templates
│   ├── transforms.py          # Logicle/log/linear via flowkit
│   └── state.py               # Session state container
├── ui/
│   ├── main_panel.py          # Root workspace widget
│   ├── ribbons/               # Toolbar ribbon widgets
│   ├── widgets/               # Sidebar panels (groups, tree, props)
│   ├── graph/                 # Graph window + FlowCanvas (matplotlib)
│   └── onboarding/            # Quick Start overlay
└── workflows/                 # Pre-built workflow templates (JSON)
```

## References

- Parks, D.R., Roederer, M., Moore, W.A. (2006). *Cytometry Part A*, 69A:541-551.
  DOI: 10.1002/cyto.a.20258
- Roederer, M. (2001). Spectral compensation for flow cytometry.
  *Cytometry*, 45:194-205.
- FlowKit: https://github.com/whitews/FlowKit
