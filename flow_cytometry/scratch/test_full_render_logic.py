import numpy as np
from fast_histogram import histogram2d
from scipy.ndimage import gaussian_filter
from scipy.ndimage import map_coordinates

# 1. Create a cluster at (15, 5) in a 20x20 space
x = np.random.normal(15, 1, 1000)
y = np.random.normal(5, 1, 1000)

# Add one outlier at (2, 18)
x = np.append(x, [2.0])
y = np.append(y, [18.0])

x_range = (0, 20)
y_range = (0, 20)
nbins = 20

# Histogram logic
H = histogram2d(x, y, bins=[nbins, nbins], range=[x_range, y_range])
smoothed = gaussian_filter(H, sigma=1.0)

# Mapping logic
x_span = x_range[1] - x_range[0]
y_span = y_range[1] - y_range[0]
x_coords = (x - x_range[0]) / x_span * nbins - 0.5
y_coords = (y - y_range[0]) / y_span * nbins - 0.5

densities = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')

print(f"Cluster point (15, 5) density: {densities[0]:.4f}")
print(f"Outlier point (2, 18) density: {densities[-1]:.4f}")

if densities[0] > densities[-1]:
    print("SUCCESS: Cluster is denser than outlier.")
else:
    print("FAILURE: Outlier is denser than cluster (FLIPPED!)")
