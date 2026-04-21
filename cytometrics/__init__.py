"""CytoMetrics Plugin for BioPro."""

__version__ = "0.1.2-beta"
__plugin_id__ = "cytometrics"


def get_panel_class():
    """
    Standard entry point for all BioPro modules.
    Returns the main QWidget class that should be injected into the UI.
    """
    from .ui.main_panel import CytoMetricsPanel
    return CytoMetricsPanel

def cleanup():
    """Module-level cleanup."""
    pass

def shutdown():
    """Module-level shutdown: Release global VRAM and AI models."""
    import sys
    if "torch" in sys.modules:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            import gc
            gc.collect()