"""Flow Cytometry Workspace — BioPro plugin entry point.

A scientist-centric flow cytometry analysis environment with workspace-based
navigation, FMO-guided gating, adaptive gates, and reusable workflow templates.
"""

__version__ = "0.1.3"
__plugin_id__ = "flow_cytometry"

def get_panel_class():
    """Returns the main QWidget class that should be injected into the UI.

    Standard BioPro entry point.  The core ``ModuleManager`` calls this
    function to obtain the class (not an instance) and then instantiates it
    into the central workspace container.
    """
    from .ui.main_panel import FlowCytometryPanel
    return FlowCytometryPanel

def cleanup():
    """Module-level cleanup."""
    pass

def shutdown():
    """Module-level shutdown."""
    pass
