# Flow Cytometry Module — Mathematics

Flow cytometry relies on several rigorous mathematical transformations to turn continuous photodetector voltage cascades into usable biological inference. This document details the specific mathematics deployed in the BioPro flow cytometry pipeline.

---

## 1. The Logicle Transform (Biexponential)

Fluorescence data spans many decades. While traditionally represented on a logarithmic scale, modern digital cytometers suffer from spread around zero due to baseline restoration artifacts and compensation errors. Pure logarithmic scaling fails because $\log_{10}(x)$ is undefined for $x \leq 0$, causing negative events (which are biologically real zero-fluorescence events subject to instrumental noise) to stack up artificially against the axis.

The flow module uses the **Logicle Transform**, introduced by Parks et al. (2006), via the `flowkit` C-extension backend. The Logicle transform is a parameterized, generalized inverse hyperbolic sine function that smoothly transitions from linear logic near zero to logarithmic logic at high decades.

### Formula Definition

A generic biexponential function is defined as:
$$ S(x) = a \cdot e^{b \cdot x} - c \cdot e^{-d \cdot x} + f $$

In the Logicle parameterization, the data $x$ is transformed to a scale value $y$ such that $S(y) = x$. The function is defined by four primary parameters:

- **$T$ (Top):** The maximum data value (top of scale), typically $262,144$ ($2^{18}$) for modern digital machines.
- **$W$ (Width):** The width of the linear region around zero, measured in logarithmic decades. This dictates how gentle the transition is. Typically $W = 0.5$.
- **$M$ (Decades):** The total number of decades the function covers across the display range. Typically $M = 4.5$.
- **$A$ (Additional Negative Decades):** Determines the extent of the linear region pushing into negative values. If $A = 0$, it exactly mirrors the basic inverse sinh transform.

The module explicitly scales data onto a $[0, 1]$ coordinate space for plotting purposes, transforming the raw channel values $x_i$:

$$ y_i = \text{Logicle}^{-1}(x_i; T, W, M, A) $$

> [!NOTE]
> Unlike standard linear approximations, the Logicle transform ensures that properties like the median of an unstained population perfectly mirror the true biological center rather than suffering from visual truncation bias.

---

## 2. Spectral Overlap & Compensation

Fluorophores do not emit light cleanly within a single defined bandpass filter; their emission spectra overlap. E.g., PE usually leaks slightly into the APC detector. If we have $N$ detectors and $N$ fluorophores, we can define a linear combination matrix.

### The Spillover Matrix ($S$)
Let $S$ be an $N \times N$ matrix where an element $S_{i, j}$ represents the light contribution from the $i$-th fluorophore into the $j$-th detector. In a perfectly isolated system, $S$ would be the identity matrix $I$.

By convention:
1. The diagonal is normalized to $1.0$ ($S_{i, i} = 1.0$). If you excite PE and look in the PE detector, that is $100\%$ of its designated signal.
2. The off-diagonal $S_{i, j}$ is the ratio of the fluorescence measured in detector $j$ to the fluorescence measured in detector $i$ when *only* fluorophore $i$ is present.

$$ S_{i, j} = \frac{\tilde{x}_{\text{single } i, \text{ detector } j}}{\tilde{x}_{\text{single } i, \text{ detector } i}} $$

Where $\tilde{x}$ is the median fluorescence intensity (MFI) of the sample.

### Background Subtraction
Before computing the ratios, biological autofluorescence ($B$) and digital instrument baseline must be subtracted. If an unstained control is provided, we compute a background vector $\vec{b}$ where $b_k = \text{MFI}_{\text{unstained, detector } k}$.

The true spillover ratio is therefore:

$$ S_{i, j} = \frac{\max(0, \tilde{x}_{\text{detector } j} - b_j)}{\tilde{x}_{\text{detector } i} - b_i} $$

> [!WARNING]
> By ensuring $\max(0, \dots)$ for the numerator, we prevent negative spillover computations which occur due to sampling noise when a fluorophore has exactly $0$ emission overlap into a far-red detector. 

### The Inverse Transformation (Compensation)
Once the Spillover Matrix $S$ is known, we must solve for the *true* fluorophore abundancies. 

If $\vec{e}$ is a vector of observed event measurements across $N$ detectors, and $\vec{f}$ is the underlying true fluorophore abundancies, we have the linear system:
$$ \vec{e} = \vec{f} \cdot S $$

To isolate $\vec{f}$, we right-multiply by the inverse of the spillover matrix, $S^{-1}$:
$$ \vec{f} = \vec{e} \cdot S^{-1} $$

### Matrix Implementation in Code
In `apply_compensation()`, the operation is vectorized entirely in Pandas/NumPy. If $E$ is an $m \times N$ matrix containing $m$ events (rows) across $N$ fluorescent channels (cols), the compensated event matrix $C$ is computed via transposing the submatrix logic:

```python
sub_matrix = comp.inverse[np.ix_(idx, idx)]
compensated = raw_events @ sub_matrix.T
```

This matrix multiplication ensures that overlap contribution is stripped uniformly across hundreds of thousands of events in milliseconds without Python `for` loops.
