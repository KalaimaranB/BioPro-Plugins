"""CytoMetrics Plugin for BioPro."""

def get_panel_class():
    """
    Standard entry point for all BioPro modules.
    Returns the main QWidget class that should be injected into the UI.
    """
    from .ui.main_panel import CytoMetricsPanel
    return CytoMetricsPanel