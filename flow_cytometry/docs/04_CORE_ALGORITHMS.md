# Flow Cytometry Module — Core Algorithms

This document provides explicit logic walk-throughs of the critical algorithms operating beneath the UI surface.

---

## 1. FlowCanvas: High-Performance Graphing

Flow cytometry data is huge. Rendering a `.scatter()` plot for 5,000,000 cells directly in matplotlib via PyQt will instantly lock the GUI thread for upwards of 15 seconds.

### The Pseudocolor Subterfuge (Hexbin)
The default `active_plot_type` is *Pseudocolor*. Instead of rendering individual vector dots, the `FlowCanvas` invokes matplotlib's `hexbin()`.

```python
self._ax.hexbin(
    x, y,
    gridsize=150,
    cmap="viridis",
    mincnt=1,
    rasterized=True
)
```

1. **`gridsize=150`**: The continuous float space is bucketed into a 150 $\times$ 150 hexagonal grid matrix using NumPy 2D histograms under the hood.
2. **`mincnt=1`**: Any hexagon containing zero cells is kept perfectly transparent rather than plotted as a dark-blue 0-density area.
3. **`rasterized=True`**: Crucial for UI. The generated hexagons are rasterized directly into a pixel bitmap rather than preserved as individual SVG/vector polygons when passed up to the PyQt memory renderer.

**Result:** A dataset of 2,000,000 coordinates is calculated into mathematical bins in C-time, and returned functionally instantly to the user as an image slice.

---

## 2. Compensation Matrix Derivation

Located in `analysis/compensation.py`, the `calculate_spillover_matrix()` function is the algorithmic heart of Phase 2.

**Logic Flow:**
1. **Background Assessment:** We instantiate a `bg = np.zeros(n)`. If an unstained control is supplied, we populate `bg` with the exact median fluorescence of the unstained cells.
2. **Setup Base Matrix:** We build an $N \times N$ identity matrix using `np.eye(n)`.
3. **Primary Detection Loop:** For every single-stain sample:
   - We extract all channels, compute the medians across all events, and subtract `bg`.
   - `primary_idx = np.argmax(medians)` safely and correctly identifies which fluorophore this tube is *actually* designated for without requiring human manual tagging! If the median of the APC channel shoots up to $80,000$ and everything else stays below $2,000$, the file unquestionably belongs to APC.
4. **Spillover Ratio Mapping:** Now that we know this Single-Stain is representing the `primary_idx` fluorophore, we compute the ratio across the entire row:
   ```python
   for j in range(n):
       if j == primary_idx: continue
       ratio = max(0.0, medians[j]) / primary_median
       spillover[primary_idx, j] = ratio
   ```
5. We record `channels_assigned.add(primary_idx)` to prevent a second PE single-stain control from overwriting the first one without raising a logged warning.

---

## 3. The `apply_compensation()` Matrix Inversion

Once computed, the compensation matrix $S$ is locked. How is it efficiently applied to raw dataframe data?

1. **Dimension Slicing:** A user's FlowJo-imported matrix might contain 14 channels, but the `.fcs` file they load only has 8 channels.
   ```python
   present = [ch for ch in channels if ch in df.columns]
   idx = [channels.index(ch) for ch in present]
   sub_matrix = comp.inverse[np.ix_(idx, idx)]
   ```
   The `.inverse` NumPy property computes $\text{inv}(S)$. `np.ix_` allows us to cleanly slice down to a smaller, perfectly valid $N \times N$ subset of the inverted matrix corresponding *only* to the overlapping channels explicitly requested.

2. **Vector Math:**
   ```python
   raw = df[present].values
   compensated = raw @ sub_matrix
   ```
   The inner values are dumped completely out of pandas into raw optimized C-structs. The `@` operator invokes BLAS/LAPACK matrix multiplication. Rather than iterating across rows, NumPy scales the dot product across the entirety of RAM.

---

## 4. Transform Normalization bypass

In Phase 1, `linear_transform()` divided all user values by `262,144` to shove the results strictly between `[0, 1]` because PyQt coordinate mappers prefer $0-1$ space. 

This artificially destroyed Matplotlib's mathematical auto-ranging system, squishing scatter parameters into the lower left 5% of the graph.

**The Fix:**
```python
def linear_transform(data: pd.Series) -> pd.Series:
    """Returns data identity (no transform)."""
    return data
```
By converting it to an identity functional pass-through, `FlowCanvas` correctly receives values up to `250,000.0`. We enforce `self._ax.margins(0.02)` during render, which forces matplotlib to naturally find its own bounding box for the data cloud entirely independently.
