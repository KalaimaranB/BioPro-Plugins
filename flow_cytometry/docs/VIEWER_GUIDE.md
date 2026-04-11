# Viewer Guide: Understanding Your Graphs

This guide decodes what you are seeing on the screen when viewing flow cytometry data in BioPro.

## 1. The "Point" (Single Event)
Every dot on a scatter plot represents a **Single Event**. In a biological sample, an event corresponds to one cell or particle that passed through the instrument's laser.
- **Dots**: Individual events in low-density regions.
- **Heat/Color**: When thousands of events occupy the same coordinate, we use a "Pseudocolor" map to indicate density.

---

## 2. Pseudocolor Decoding
BioPro uses a thermal density gradient (the "Turbo" colormap) to help you identify populations:
- **Blue/Purple**: Low density (singleton cells or outliers).
- **Green/Yellow**: Medium density.
- **Red/White**: Peak density (the "heart" of a population).

**Why use Pseudocolor?**
Without it, a million events would just look like a solid black blob. Pseudocolor allows you to see the internal structure and "peaks" of a population cluster.

---

## 3. The "Rail" Effect
You will often see dense lines of dots perfectly stacked against the $0$ or $262,144$ axis lines. This is called **Railing**.
- **The Top Rail**: These are "off-scale" events—cells that were so bright they saturated the instrument's detector.
- **The Bottom Rail**: These are "zeroed" events—often the result of background noise subtraction or compensation that pushed the signal to the minimum possible channel.

*Note: BioPro's Auto-Zoom is designed to keep these rails visible so you don't lose track of saturated data.*

---

## 4. Interaction Layers
The graph window is composed of two independent visual layers:
1.  **The Raster Data Layer**: A high-resolution bitmap of your millions of cells. This is "static" to preserve rendering performance.
2.  **The Vector Gate Layer**: The gates, handles, and labels you interact with. These are drawn on top and respond instantly to your mouse without causing the complex data points to re-render.

---

## 5. Statistical Overlays
Inside a graph window, you see real-time statistics in the corner or bottom bar:
- **Events**: The absolute number of cells inside the current view.
- **% Parent**: How many cells are in this gate compared to the gate one level up in the hierarchy.
- **% Total**: How many cells are in this gate compared to the entire un-gated tube.

---

## 6. Pro-Tip: The "Smart Zoom"
When you double-click a gate in the hierarchy, BioPro's "Smart Zoom" automatically calculates a new axis range that captures exactly $98\%$ of your cells (excluding the extreme $1\%$ outliers) and adds a small $10\%$ margin. This is why the graph seems to "jump" to a perfect, high-resolution view of your population.
