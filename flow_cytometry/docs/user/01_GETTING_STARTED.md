# Getting Started with BioPro Flow Cytometry

This guide will walk you through your first analysis, from launching the module to creating your initial population gates.

## 1. Guided Tour: The Workspace

The workspace is designed to mirror a scientist's physical workflow.

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

## 2. Your First Analysis

### Step 1: Loading Data
1. Click the **➕ Add Samples** button in the Workspace Ribbon.
2. Select your `.fcs` files (FCS 2.0, 3.0, or 3.1).
3. **Recommendation**: When asked, copy files into your project's `assets/` directory to ensure your analysis remains portable.

### Step 2: Opening a Plot
Double-click any sample in the **Sample Tree** (left panel). The central canvas will render the default parameters (usually FSC-A vs SSC-A).

### Step 3: Changing Axes
Use the dropdown menus at the bottom (X-axis) and left (Y-axis) of the plot.
- Dropdowns show both the **Detector Name** (e.g., *FITC-A*) and the **Biological Marker** (e.g., *CD4*), making it easy to find your channels.

### Step 4: Drawing a Gate
1. Click the **Gating** tab in the Ribbon.
2. Select the **Rectangle** tool.
3. Click and drag over the population of interest (e.g., the Lymphocyte cloud).
4. Enter a name like "Lymphocytes" when prompted.
5. Notice the new population appears as a child of your sample in the Sample Tree!

---

## 💡 Pro Tips
- **Right-click** a sample in the tree to quickly export its statistics to CSV.
- Use the **Mouse Wheel** to zoom in/out on the canvas.
- Toggle between **Pseudocolor** and **Dot Plot** in the Properties panel to see individual outliers.

---

## 🔗 Next Steps
- **[Deep Dive: Compensation & Advanced Gating](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/02_ANALYSIS_GUIDE.md)**
- **[Scientific Principles of Scaling](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/03_SCIENTIFIC_LOGIC.md)**
