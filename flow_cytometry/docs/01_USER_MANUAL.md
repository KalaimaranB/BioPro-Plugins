# Flow Cytometry Module — User Manual

Welcome to the **BioPro Flow Cytometry Module**! This manual provides a guided walkthrough for analyzing complex data sets, from raw FCS loading to final population statistics.

---

## 1. Guided Tour: The Workspace

The workspace is divided into several high-interaction zones designed to mirror a scientist's physical workflow.

### A. The Ribbon (Top)
Organized into context-aware tabs:
- **Workspace**: Global actions like adding samples, managing groups, and exporting templates.
- **Compensation**: Tools for creating, importing, and applying spillover matrices.
- **Gating**: Specialized tools for drawing and managing child populations.

### B. The Sidebar (Left)
- **Groups Panel**: Filter your data views by experimental condition (e.g., "Stimulated" vs. "Control").
- **Sample Tree**: The core of your workspace. It displays all loaded files and their hierarchical gate populations. Double-click a sample to open it in the canvas.

### C. The Canvas (Center)
The high-performance rendering engine. It handles millions of events using hardware-accelerated hexbin density plots. Interact with the canvas using the mouse to draw new gates or move existing ones.

### D. Properties & Stats (Right)
- **Sample Properties**: View metadata, change axis scales, or change display modes (e.g., Pseudocolor vs. Contour).
- **Statistics**: View real-time population numbers (MFI, CV, %Parent) for the currently selected sample and gate.

---

## 2. Getting Started: Loading & Mapping Data

### Launching the Workspace
When you open the Flow Cytometry module within BioPro, you are presented with a central workspace comprising:
- **Top Ribbon:** Tabbed groupings for Workspace actions, Compensation, and Gating.
- **Left Panel:** The **Groups Panel** (for organizing tubes) and the **Sample Tree** (the primary hierarchy of all loaded FCS files).
- **Center Canvas:** The high-speed visualization engine.
- **Right Panel:** The **Properties Panel** which displays metadata and allows you to assign roles to specific samples.

### Loading Data
Data loading in BioPro is safe and non-destructive.
1. Click the **➕ Add Samples** button in the Workspace Ribbon.
2. Select your `.fcs` files (FCS 2.0, 3.0, or 3.1).
3. If your files exist outside of your main BioPro project folder, the module will explicitly ask if you want to copy them into your project's `assets/` directory. This is highly recommended to ensure your analysis remains portable if you send the project to a collaborator!

---

## 2. Managing Your Samples

Flow cytometry experiments can have dozens of tubes. The module helps you track what each tube is for.

### Sample Roles
By default, newly loaded tubes are given the role of `Other`. To correctly compute compensation or background subtraction, you must tell the system what your tubes are.
1. Click a sample in the **Sample Tree** (left).
2. Look at the **Properties Panel** (right).
3. Under the *Sample Role* dropdown, choose the appropriate tag:
   - **Unstained Control:** Used for autofluorescence removal.
   - **Single Stain:** Used to compute the spillover matrix.
   - **FMO Control:** Fluorescence Minus One (used for gating).
   - **Full Panel / Test:** Your actual biological samples.

### Grouping 
You can create Groups (e.g., "Treatment A", "Stimulated") to filter the Sample Tree. Click **📁 Create Group** in the Workspace Ribbon, then drag or assign samples.

---

## 3. Visualization

The central canvas is driven by `FlowCanvas`, providing high-performance renders.

- **Opening a Plot:** Double-click any sample in the Sample Tree to open it in a new tab.
- **Changing Axes:** Use the dropdowns at the bottom and left of the plot to select your parameters (e.g., FSC-A vs SSC-A). The dropdowns display the *biological marker name* if available, alongside the detector channel.
- **Changing Modes:** Use the `Display Mode` dropdown in the Properties panel. Options include:
  - **Pseudocolor:** A high-speed hexbin density plot mapped to the viridis colormap.
  - **Dot Plot:** Raw individual scatter points.
  - **Density / Contour:** Smoothed topological views of your cell clouds.
  - **Histogram / CDF:** 1-dimensional analysis (set the Y-axis parameter to "None").

> [!TIP]
> The axes automatically scale to your data. Fluorescence channels automatically utilize the Logicle Transform (Parks 2006) which allows proper visualization of negative values alongside multi-decade positive populations. Scatter channels remain linear.

---

## 4. Compensation

Spectral overlap between fluorophores must be compensated before gating. This is managed in the **Compensation Tab** of the ribbon. 

> [!IMPORTANT]
> The Compensation matrix permanently modifies the memory-state of the loaded events arrays when applied. However, this is isolated to the BioPro process — your raw `.fcs` files on disk are **never modified or overwritten**.

### Option A: Calculate from Controls
1. Tag your single-stain tubes with the `Single Stain` role in the Properties panel.
2. (Optional but recommended) Tag an unstained tube with `Unstained Control`.
3. Go to the Compensation ribbon and click **🔬 Calculate Matrix**.
4. The system will automatically locate the primary fluorescence channel for each control, calculate the median ratio of spillover into all other detectors, generate an $N \times N$ matrix, and display the output.

### Option B: Extract from FCS Metadata
If your cytometer software (like FACSDiva) already computed and embedded the compensation matrix during acquisition:
1. Click **📄 Extract from FCS**.
2. The module scans the metadata for the `$SPILL` or `$SPILLOVER` keyword, reconstructs the matrix, and loads it into memory.

### Option C: Import/Export CSV
You can import matrices generated by FlowJo or other tools via **📥 Import CSV**. (It handles both `.csv` and tab-delimited `.tsv` files). Ensure the channel names closely match your FCS data.

### Applying the Matrix
Computing/Importing a matrix does not automatically change your data! You must click **✅ Apply to All** to multiply your raw data against the matrix. The plotted data will instantly refresh to display the compensated traces.

---

## 5. Gating: Defining Populations

Gating in BioPro is hierarchical. Every gate you create defines a new "sub-population" in the Sample Tree.

1.  **Select a Gate Tool**: Go to the **Gating Ribbon** and choose **Rectangle**, **Polygon**, **Ellipse**, or **Quadrant**.
2.  **Draw on the Canvas**: 
    - Click and drag for Rectangles/Ellipses.
    - Click for each vertex of a Polygon; double-click to close.
3.  **Name the Population**: A dialog will prompt you for a name (e.g., "Live Cells").
4.  **View Results**: The new population appears under its parent in the Sample Tree. Selecting it will filter the current view so you only see events inside that gate.

---

## 6. Compensation Troubleshooting

If your data looks "over-compensated" (populations hugging the axes) or "under-compensated" (bleeding into other channels):

- **Check Unstained Control**: Ensure you've tagged an Unstained Control sample to allow for correct background subtraction.
- **Inspect Matrix Ratios**: Open the **Matrix View** in the Compensation ribbon. Look for unusually high ratios (>1.0), which may indicate a misidentified primary channel.
- **Verify Transform Parameters**: Sometimes a poorly configured Logicle transform can hide negative data. Ensure your **Width (W)** parameter is set to at least 0.5 to see the spread around zero.

---

## 7. Workflow Templates and Saving

BioPro encourages reproducible science through "Workflows".

- **💾 Save Workflow (Project-wide):** Handled automatically by the BioPro Core (via `CTRL+S` or the core UI). This serializes your *entire session state*, including paths to your loaded FCS files, your compensation matrices, and your current display parameters, into a single JSON snapshot.
- **📋 Save as Template:** Located in the Workspace ribbon. If you've just spent 15 minutes defining all your marker mappings, FMO groups, and Single Stain roles for a 16-color panel, you can click this to save the *empty structural layout*. 
- **📋 Load Template:** When you start a fresh experiment next week, load your template first! It pre-creates your Groups and specific tube slots. You then simply select your newly acquired FCS files to fill the slots without having to redefine any metadata.

---

## 8. High-Fidelity Rendering & Export

BioPro provides a dedicated rendering engine for generating publication-quality images. While the main canvas is optimized for speed and interactivity, the **Full Render** engine is designed for maximum scientific accuracy and visual fidelity.

### Accessing Full Render
1.  **Right-Click** anywhere on the scatter or histogram plot in the center canvas.
2.  Select **🖼️ Render Full Quality...** from the context menu.
3.  A new, modeless window will open.

### Why use Full Render?
-   **No Subsampling**: Unlike the main view (which limits displays to 100,000 events for performance), the Full Render engine processes **every single event** in your dataset.
-   **High-Resolution Grids**: Pseudocolor density grids are calculated at 2x resolution (1024x1024 bins).
-   **Premium Export**:
    -   **📋 Copy to Clipboard**: Instantly grab a high-res bitmap for your laboratory slides.
    -   **💾 Publication Export**: Save as high-res **PNG (300 DPI)**, or vector-based **PDF/SVG** for infinite scalability in manuscripts.

> [!TIP]
> For rare event analysis (e.g., populations comprising <0.01% of total events), use Full Render to ensure every outlier dot is accurately represented in your final figure.
