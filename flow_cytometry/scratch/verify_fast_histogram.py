import numpy as np
from fast_histogram import histogram2d

# Create a cluster at (X=10, Y=2)
x = np.array([10.0])
y = np.array([2.0])

# Grid 20x20
H = histogram2d(x, y, bins=[20, 20], range=[[0, 20], [0, 20]])

# Find where the 1.0 is
indices = np.argwhere(H > 0)
print(f"Cluster at (10, 2) found at index: {indices}")
