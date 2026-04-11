# Gating Mathematics & Hierarchical Logic

This document details the mathematical algorithms used for event classification (containment) and the logic behind hierarchical population filtering.

## 1. Containment Algorithms

Every gate defines a boolean inclusion test $f(x, y) \rightarrow \{0, 1\}$.

### Rectangle & Range Gates
The simplest form of gating. A point is included if it falls within the closed interval of both axes:
$$x_{min} \leq x \leq x_{max} \quad \text{AND} \quad y_{min} \leq y \leq y_{max}$$
For 1D Range gates (Histograms), the $y$ terms are omitted.

### Polygon Gates (Ray Casting)
For arbitrary shapes, we use the **Crossing Number** (Ray Casting) algorithm.
1.  A ray is projected from the event point $(x, y)$ in any fixed direction (e.g., $+x$).
2.  We count how many times the ray intersects the polygon edges.
3.  If the number of intersections is **odd**, the point is **inside**.
*Implementation note: We utilize `matplotlib.path.Path.contains_points` which uses a highly optimized C implementation of this logic.*

### Ellipse Gates (Quadratic Form)
A point $(x, y)$ is inside if it satisfies the normalized quadratic inequality for a rotated ellipse:
$$\frac{((x - c_x)\cos\theta + (y - c_y)\sin\theta)^2}{a^2} + \frac{(-(x - c_x)\sin\theta + (y - c_y)\cos\theta)^2}{b^2} \leq 1$$
Where:
- $(c_x, c_y)$ is the center.
- $a, b$ are the semi-axis lengths.
- $\theta$ is the counter-clockwise rotation angle.

---

## 2. Data Integrity: Boundary Handling

In flow cytometry, events frequently sit exactly on the dynamic range limits (rails) or precisely on a gate vertex.
- **Inclusion**: We use **inclusive** boundaries ($\leq$, $\geq$) for all geometric tests.
- **Railing**: Events at the exact instrument maximum (e.g., channel 262,144) are included in the outermost bins of any gate that touches the boundary.

---

## 3. Hierarchical Population Logic

Gates form a parent-child hierarchy. The true population of a child node is the **intersection** of its own mask and the masks of all its ancestors.

### The GateNode Tree
- **Root Node**: Contains the ungated event set ($N_{all}$).
- **Child Node**: Filters its parent's events.
- **Math**: For a node $G_k$ with ancestors $G_1, G_2, \dots, G_{k-1}$, the set of events $S_k$ is:
  $$S_k = \{ \text{events } e \mid e \in S_{k-1} \text{ AND } \text{gate}_k.\text{contains}(e) \}$$

### Population Statistics
- **Event Count**: $|S_k|$
- **% Parent**: $(|S_k| / |S_{parent}|) \times 100$
- **% Total**: $(|S_k| / |S_{root}|) \times 100$

---

## 4. Propagation & Serialization

When a gating strategy is "Applied to All Samples", the system:
1.  Serializes the active `GateNode` tree into a JSON structure (geometry and parameter names).
2.  Iterates through each sample in the target group.
3.  Recursively reconstructs the tree on the new dataset.
4.  Optionally triggers **Adaptive Alignment** (if enabled) to move vertex positions toward local density peaks in the new sample.
