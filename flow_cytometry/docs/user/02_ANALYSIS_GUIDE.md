# Advanced Analysis Guide

This guide covers advanced workflows including sample role management, automated compensation, and high-fidelity rendering for publication.

## 1. Managing Large Experiments

### Sample Roles
By default, newly loaded tubes are given the role of `Other`. To enable automated features, you must assign roles:
1. Click a sample in the **Sample Tree**.
2. In the **Properties Panel** (right), select a role:
   - **Unstained Control**: Used for autofluorescence removal.
   - **Single Stain**: Used to compute the spillover matrix.
   - **FMO Control**: Fluorescence Minus One (used for gating precision).
   - **Full Panel / Test**: Your actual biological samples.

### Grouping 
Use Groups to organize multi-day or multi-patient experiments. Click **📁 Create Group** in the Workspace Ribbon, then drag samples into the new group.

---

## 2. Automated Compensation

Compensation ensures that signal bleeding from one fluorophore into another is mathematically removed.

### Calculating a Matrix
1. Tag your single-stain tubes with the `Single Stain` role.
2. Go to the **Compensation** ribbon tab.
3. Click **🔬 Calculate Matrix**.
4. The system automatically identifies the primary fluorescence channel for each control and generates the $N \times N$ spillover matrix.

### Applying the Matrix
Computing a matrix does not automatically change your data. You must click **✅ Apply to All** to update your events. The plots will refresh instantly.

---

## 3. Advanced Gating Tools

Beyond basic rectangles, the module supports complex shapes:

- **Polygon**: Click for each vertex; double-click to close. Ideal for non-standard lymphocyte or myeloid populations.
- **Ellipse**: Click and drag to create an elliptical region. Best for tightly clustered populations on logarithmic scales.
- **Quadrant**: Click a single point to divide the plot into four regions (e.g., $CD4^+/CD8^-$, $CD4^-/CD8^+$, etc.).

### Managing the Hierarchy
Gating is hierarchical. Selecting a child gate in the **Sample Tree** filters the canvas to only show events belonging to that population. This allows for "gating down" to rare cell types (e.g., *Lymphocytes → T Cells → CD4+ T Cells*).

---

## 4. Publication-Quality Export

While the main canvas is optimized for speed, the **Full Render** engine is designed for publication.

### Creating a Full Render
1. **Right-Click** anywhere on the center canvas.
2. Select **🖼️ Render Full Quality...**.
3. The resulting window processes **every single event** (no subsampling) and uses high-resolution grids (1024x1024).

### Export Options
- **📋 Copy to Clipboard**: High-res bitmap for slides.
- **💾 Publication Export**: Save as **PNG (300 DPI)** or vector-based **PDF/SVG** for manuscripts.

---

## 🔗 Deep Dives
- **[Scientific Principles of Logicle Transforms](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/03_SCIENTIFIC_LOGIC.md)**
- **[Developer API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**
