import numpy as np
from fast_histogram import histogram2d

def test_inverted():
    x = np.array([1, 2, 3])
    y = np.array([1, 2, 3])
    try:
        H = histogram2d(x, y, bins=[4, 4], range=[[4, 0], [0, 4]])
        print("Inverted range H:")
        print(H)
    except Exception as e:
        print(f"Inverted range failed: {e}")

if __name__ == "__main__":
    test_inverted()
