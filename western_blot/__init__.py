"""Western Blot Densitometry Plugin for BioPro."""

__version__ = "1.0.2"
__plugin_id__ = "western_blot"


def get_panel_class():
    """
    Standard entry point for all BioPro modules. 
    Returns the main QWidget class that should be injected into the UI.
    """
    from .ui.western_blot_panel import WesternBlotPanel 
    return WesternBlotPanel

def cleanup():
    """Module-level cleanup (no instance state)."""
    pass

def shutdown():
    """Module-level shutdown."""
    pass