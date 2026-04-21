# Flow Cytometry Module — Technical Reference

This document provides the mathematical and algorithmic foundations of the BioPro Flow Cytometry module. It is intended for researchers and developers who require a detailed understanding of how data is transformed, compensated, gated, and rendered.

---

## 1. Mathematical Foundations

### 1.1 The Logicle Transform (Biexponential)
Fluorescence data often spans many decades and includes zero or negative values due to compensation and baseline subtraction. The module uses the **Logicle Transform** (Parks et al., 2006) to allow seamless visualization from linear space (near zero) to logarithmic space (high signals).

**The Forward Transform:**
The Logicle function $S(y)$ maps a display value $y$ to a data value $x$. The function is defined piecewise, but the core biexponential form is:
$$ S(y) = a \cdot e^{b \cdot y} - c \cdot e^{-d \cdot y} + f $$

**The Inverse Problem (Logicle Inversion):**
For analysis and plotting, we must find the display coordinate $y$ for a given data point $x$. Since $S(y)$ cannot be solved analytically for $y$, the module employs a high-performance **Newton-Raphson iteration** (or a Look-Up Table for bulk values) provided by the `flowutils` C-extension. The solver iterates until the difference $\left| S(y_n) - x \right|$ falls below a precision threshold ($\epsilon < 10^{-6}$), ensuring that data points are mapped to pixel space with sub-micron accuracy.

**Parameters:**
- **$T$ (Top):** The maximum data value (e.g., $262,144$ for 18-bit digital data).
- **$W$ (Width):** The width of the linear region around zero in decades.
- **$M$ (Decades):** The total number of positive decades to display.
- **$A$ (Additional Negative Decades):** The amount of negative data to display.

**Fallback (Asinh):**
If `flowkit` is unavailable, the system falls back to a scaled inverse hyperbolic sine ($arcsinh$) transform, which mirrors biexponential behavior without the piece-wise complexity:
$$ y = \text{arcsinh}\left(\frac{x}{150}\right) $$

---

## 2. Adaptive Gating

Adaptive gating allows a scientist's defined populations to "find their center" when applied to a new sample where the biological density has shifted slightly.

### 2.1 KDE Peak Detection
When a gate is marked as `adaptive=True`, the module performs a local optimization:
1. **Bootstrap Initialization**: A subset of events from the parent population is extracted.
2. **KDE Fit**: A Kernel Density Estimation (KDE) is performed in the region of the original gate.
3. **Centroid Alignment**: The algorithm finds the local maximum (peak) within the proximity of the original gate's centroid.
4. **Rescaling**: The gate vertices are translated (and optionally rescaled) such that the peak of the new data density aligns with the gate's geometric center.

---

## 3. Statistical Formulas & Compensation

### 3.1 Spectral Overlap & Compensation
Fluorescent dyes bleed into neighboring detector channels. We correct this by solving the linear system:
$$ \vec{e} = \vec{f} \cdot S $$
Where $\vec{e}$ is the observed event vector, $\vec{f}$ is the true fluorophore vector, and $S$ is the **Spillover Matrix**.

**Matrix Derivation:**
For each single-stain control $i$, the spillover into channel $j$ is calculated as:
$$ S_{i, j} = \frac{\max(0, \tilde{x}_{\text{detector } j} - \text{bg}_j)}{\tilde{x}_{\text{detector } i} - \text{bg}_i} $$
- $\tilde{x}$ is the median fluorescence intensity (MFI).
- $\text{bg}$ is the background median from an unstained control.

**Application:**
The compensated signal is retrieved by multiplying against the matrix inverse:
$$ \vec{f} = \vec{e} \cdot S^{-1} $$

### 3.2 Gating Algorithms
All gating calculations are performed in **Data Space**, but containment is tested in **Display Space** (after applying transforms) to ensure the visual boundaries match the selected populations.

| Gate Type | Mathematical Test |
| :--- | :--- |
| **Rectangle** | $x_{min} \leq x \leq x_{max} \quad \text{AND} \quad y_{min} \leq y \leq y_{max}$ |
| **Polygon** | **Ray Casting (Crossing Number)**: A ray is projected from the point; an odd number of intersections with polygon edges indicates the point is inside. |
| **Ellipse** | **Quadratic Form on Rotated Coordinates**: $\left(\frac{x'}{w}\right)^2 + \left(\frac{y'}{h}\right)^2 \leq 1$, where $(x', y')$ are centered and rotated. |
| **Range** | 1-Dimensional threshold: $x_{low} \leq x \leq x_{high}$ |

The module computes population-level statistics using the following standard definitions:

- **Mean**: $\bar{x} = \frac{1}{n} \sum_{i=1}^n x_i$
- **Median**: The middle value of the sorted data set.
- **Geometric Mean**: $\exp\left(\frac{1}{n_+} \sum_{x_i > 0} \ln(x_i)\right)$ (computed only on positive values).
- **Coefficient of Variation (CV)**: $\frac{SD}{\left| \bar{x} \right|} \times 100\%$, where $SD$ is the sample standard deviation.
- **Percent Parent**: $\frac{\text{Count}_{\text{population}}}{\text{Count}_{\text{parent}}} \times 100\%$
- **MFI**: Median Fluorescence Intensity (equivalent to Median).

---

## 4. High-Performance Rendering

Rendering millions of events in real-time requires significant optimization. The `FlowCanvas` employs several strategies to maintain responsiveness without sacrificing scientific accuracy.

### 4.1 "Cutting Corners" (Optimizations)
1.  **Hexbin/Pseudocolor Density**:
    -   Instead of plotting individual dots, data is bucketed into a $512 \times 512$ grid.
    -   A Gaussian smoothing filter ($\sigma = 1.5$) is applied to the grid to reduce sampling noise.
2.  **Subsampling**:
    -   **Pseudocolor**: Limited to 100,000 events for density estimation.
    -   **Dot Plots**: Limited to 50,000 events for scatter rendering.
    -   **KDE Density**: Limited to 20,000 events (due to $O(n^2)$ complexity).
3.  **Bitmap Caching**:
    -   The scatter/density data layer is snapshotted to a bitmap memory buffer.
    -   Gate overlays (which change frequently during user interaction) are redrawn onto this bitmap, avoiding expensive re-renders of the underlying cell data.
4.  **Rasterization**:
    -   Final plot elements are rasterized into a pixel bitmap rather than preserved as vector objects (SVG), preventing UI lag when moving or resizing the window.

### 4.4 High-Fidelity Render Engine (RenderWindow)

The `RenderWindow` bypasses the performance optimizations of the standard `FlowCanvas` to provide a "Raw Signal" visualization:

1.  **Exhaustive Processing**: Subsampling is completely disabled (`max_events = None`). In a 5-million event dataset, every point is transformed and contributed to the density calculation.
2.  **Grid Upscaling**: The density grid resolution is doubled ($1024 \times 1024$ bins). This increases the precision of population boundary visualizations and reduces discretization noise.
3.  **Publication Standards**:
    -   **PNG Export**: Forced to 300 DPI regardless of screen resolution.
    -   **Vector Export**: PDF and SVG exports utilize the `matplotlib` backend to preserve mathematical paths for all gates and labels, ensuring they remain "infinite-resolution" in vector editing software (e.g., Adobe Illustrator).

### 4.2 Data Jittering (Dithering)
Digital cytometers produce integer values. Parallel populations in a density plot can create "integer banding" (artificial vertical and horizontal lines) because all events have exact same whole-number intensities (e.g., $1023.0$ vs $1024.0$).

To prevent this, the module applies a continuous **Uniform Jitter ($\pm 0.5$)** to data values during the transformation phase. This "dithering" breaks the integer alignment, allowing the density estimators (KDE and hexbin) to find the true underlying biological distribution without sampling artifacts.

### 4.3 Visual Logic & Bounds
-   **Axis Pile-up**: Events falling outside the current visual range are clipped to the boundaries rather than being discarded. This ensures that "rail" populations are visible and contribute correctly to density visualizations.
-   **Equal Probability Normalization**: To match FlowJo's aesthetic, the module uses **Percentile Normalization (Rank-based)** for pseudocolor. Linear density values are converted to percentiles, inflating the visibility of sparse populations so they appear as distinct "islands" of color.

---

## 5. Default Parameters & Justifications

| Parameter | Default Value | Justification |
| :--- | :--- | :--- |
| **Logicle T** | $262,144$ ($2^{18}$) | standard top-of-scale for modern 18-bit digital cytometers. |
| **Logicle W** | $1$ | Provides $1$ decade of linearization around zero, preventing visual "pinching." |
| **Logicle M** | $4.5$ | Standard display range for fluorescence (4.5 decades). |
| **Grid Size** | $512$ | Balanced resolution for 1080p and 4K displays; looks continuous to the eye. |
| **KDE BW** | $0.15$ | Silvermann-like bandwidth; provides enough smoothing without losing population definition. |

---

## 5. References

- Parks, D.R., Roederer, M., Moore, W.A. (2006). *Cytometry Part A*, 69A:541-551.
- Roederer, M. (2001). Spectral compensation for flow cytometry. *Cytometry*, 45:194-205.
