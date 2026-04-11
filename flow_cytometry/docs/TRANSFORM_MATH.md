# Axis Transformations & Signal Processing

This document explains why and how we transform raw instrument data for visualization, including the math behind Linear, Log, and Logicle (Biexponential) scaling.

## 1. Why Transform?

Flow Cytometer sensors (Photomultiplier Tubes or Silicon Photodiodes) capture light intensity across a high dynamic range (typically $0$ to $2^{18}$ or $262,144$ channels).
- **Linear Parameters** (FSC, SSC): Cell size and granularity are usually best viewed on a linear scale.
- **Fluorescent Parameters**: Fluorescent distributions often span 3-5 orders of magnitude, requiring Logarithmic scaling to visualize both dim and bright populations simultaneously.
- **Compensated Data**: Subtraction of spectral overlap (compensation) can result in negative values for dim populations. Pure Log scales cannot display values $\leq 0$, creating a "smeared" artifact against the axis.

---

## 2. Transformation Mathematics

### Linear Transform
An identity mapping used for scatter parameters:
$$f(x) = x$$

### Logarithmic Transform
Base-10 scaling with a defined floor to prevent $\log(0)$:
$$f(x) = \frac{\log_{10}(\max(x, \text{floor}))}{\text{decades}}$$
Where `floor` is typically 1.0 and `decades` is the dynamic range (e.g., 4.5).

### Biexponential (Logicle) Transform
The gold standard for modern cytometry (Parks et al., 2006). It maps data such that the region near zero is linear (handling negative values) and transitioned smoothly to a logarithmic scale for higher values.
A simplified form of the Logicle function $S(x)$ is:
$$S(x) = ae^{bx} - ce^{dx} + f$$
The implementation in this module uses the validated C-source algorithm from **Parks et al.**, which solves for parameters $T, W, M, A$:
- **T**: Top of the data range.
- **W**: Linearization width (decades of data to be linear).
- **M**: Total positive decades.
- **A**: Additional negative decades.

---

## 3. Edge Accumulation & Outliers

### The "Rail" Strategy
Instruments hard-clamp out-of-range signals. Any signal $> T$ or $< 0$ is piled up at the boundary.
- We render these "railed" events as a thin, dense line at the edge of the plot.
- When transforming, these events remain at the $0$ and $1.0$ display coordinates.

### Auto-Zoom Heuristics
When navigating into a gated subset, the module executes an **Auto-Zoom** to focus on the population:
1.  **Percentile Pass**: We calculate the 1st and 99th percentile of the gated event set.
2.  **Margin Expansion**: We add a 10% margin to the bounds to ensure outliers are visible.
3.  **Recursive Clamping**: We clamp the expansion to the absolute `[min, max]` of the raw instrument data. This prevents the "floating axis" artifact where railed data appears to detach from the plot frame.

### Smart Channel Guessing
When double-clicking a gate:
- If current axis = `FSC` vs `SSC` $\rightarrow$ Target the first two fluorescent channels.
- If current axis = Fluorescent $\rightarrow$ Stay on those channels but tighter zoom.
This heuristic prioritizes the most likely "next step" in a clinical gating workflow (moving from debris exclusion to marker identification).
