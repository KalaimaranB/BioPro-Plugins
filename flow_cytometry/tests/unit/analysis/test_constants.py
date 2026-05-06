import pytest
import flow_cytometry.analysis.constants as constants

def test_rendering_constants_have_not_drifted():
    """Verify core math parameters for density rendering haven't drifted.
    
    If these values are changed, the visual appearance of the pseudocolor 
    plots will change significantly. Ensure any changes are intentional.
    """
    assert constants.DEFAULT_NBINS_MIN == 512
    assert constants.DEFAULT_NBINS_MAX == 1024
    assert constants.NBINS_SCALING_FACTOR == 2.0
    
    assert constants.SIGMA_MIN == 1.2
    assert constants.SIGMA_SCALING_FACTOR == 1.8
    
    assert constants.DENSITY_THRESHOLD_MIN == 0.1
    assert constants.DENSITY_THRESHOLD_PCT == 0.02
    
    assert constants.VIBRANCY_MIN == 0.15
    assert constants.VIBRANCY_RANGE == 0.85

def test_logicle_defaults_are_standard():
    """Verify Logicle parameters match the Parks 2006 / traditional analysis software defaults."""
    assert constants.LOGICLE_T_DEFAULT == 262144.0
    assert constants.LOGICLE_W_DEFAULT == 1.0
    assert constants.LOGICLE_M_DEFAULT == 4.5
    assert constants.LOGICLE_A_DEFAULT == 0.0

def test_overlay_colors_exist():
    """Verify required overlay semantic colors are present."""
    assert "default" in constants.OVERLAY_COLORS
    assert "selected" in constants.OVERLAY_COLORS
    assert "inactive" in constants.OVERLAY_COLORS
