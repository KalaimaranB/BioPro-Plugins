import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from fast_histogram import histogram2d

def test_orientation():
    # Create a 4x4 grid
    # Cluster at (x=1, y=2)
    x = np.array([1.0, 1.0, 1.0])
    y = np.array([2.0, 2.0, 2.0])
    
    nbins = 4
    x_range = (0, 4)
    y_range = (0, 4)
    
    H = histogram2d(x, y, bins=[nbins, nbins], range=[x_range, y_range])
    print("Histogram H:")
    print(H)
    # If H[x, y], then H[1, 2] should be 3.
    # Expected:
    # [[0 0 0 0]
    #  [0 0 3 0]
    #  [0 0 0 0]
    #  [0 0 0 0]]
    
    # Coordinates for (x=1, y=2)
    # (x - lo) / span * nbins - 0.5
    # (1 - 0) / 4 * 4 - 0.5 = 0.5
    # (2 - 0) / 4 * 4 - 0.5 = 1.5
    
    cx = 0.5
    cy = 1.5
    
    print(f"Coordinates: cx={cx}, cy={cy}")
    
    # Case 1: [cx, cy]
    val1 = map_coordinates(H, [[cx], [cy]], order=1)[0]
    print(f"Lookup [cx, cy]: {val1}")
    
    # Case 2: [cy, cx]
    val2 = map_coordinates(H, [[cy], [cx]], order=1)[0]
    print(f"Lookup [cy, cx]: {val2}")

if __name__ == "__main__":
    test_orientation()
