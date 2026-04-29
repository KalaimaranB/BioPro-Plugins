import numpy as np
from fast_histogram import histogram2d

x = np.array([1, 1, 2])
y = np.array([1, 2, 2])
# Range [0, 3] for both
h = histogram2d(x, y, bins=[3, 3], range=[[0, 3], [0, 3]])
print("Histogram:")
print(h)
# If h[x_idx, y_idx]:
# (1, 1) -> idx (1, 1)
# (1, 2) -> idx (1, 2)
# (2, 2) -> idx (2, 2)
# Expected h:
# [[0 0 0]
#  [0 1 1]
#  [0 0 1]]
