"""Western Blot Densitometry Plugin for BioPro."""

def get_panel_class():
    """
    Standard entry point for all BioPro modules. 
    Returns the main QWidget class that should be injected into the UI.
    """
    from .ui.western_blot_panel import WesternBlotPanel 
    return WesternBlotPanel