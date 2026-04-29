import numpy as np
from fast_histogram import histogram2d
from scipy.ndimage import gaussian_filter, map_coordinates

# Create a cluster at (X=15, Y=5)
x = np.random.normal(15, 0.5, 100)
y = np.random.normal(5, 0.5, 100)

x_range = (0, 20)
y_range = (0, 20)
nbins = 20

# H[x, y]
H = histogram2d(x, y, bins=[nbins, nbins], range=[x_range, y_range])
smoothed = gaussian_filter(H, sigma=1.0)

# True location in bin space
tx = (15 - 0) / 20 * nbins - 0.5 # 14.5
ty = (5 - 0) / 20 * nbins - 0.5  # 4.5

# Test [tx, ty]
d1 = map_coordinates(smoothed, [[tx], [ty]], order=1)[0]
# Test [ty, tx]
d2 = map_coordinates(smoothed, [[ty], [tx]], order=1)[0]

print(f"Density with [x, y]: {d1:.4f}")
print(f"Density with [y, x]: {d2:.4f}")

if d1 > d2:
    print("RESULT: [x, y] is correct for H[x, y]")
else:
    print("RESULT: [y, x] is correct for H[x, y] (Wait, what?)")
