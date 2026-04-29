"""Event topic constants for the flow cytometry module.

These are used with the BioPro SDK's CentralEventBus to ensure
decoupled communication between components.
"""

# Gate events
GATE_CREATED = "flow.gate.created"
GATE_RENAMED = "flow.gate.renamed"
GATE_DELETED = "flow.gate.deleted"
GATE_MODIFIED = "flow.gate.modified"
GATE_PROPAGATED = "flow.gate.propagated"
GATE_SELECTED = "flow.gate.selected"
GATE_PREVIEW = "flow.gate.preview"

# Sample events
SAMPLE_SELECTED = "flow.sample.selected"
SAMPLE_DESELECTED = "flow.sample.deselected"
SAMPLE_LOADED = "flow.sample.loaded"

# Canvas/Rendering events
RENDER_MODE_CHANGED = "flow.render.mode_changed"
RENDER_CONFIG_CHANGED = "flow.render.config_changed"
AXIS_PARAMS_CHANGED = "flow.axis.params_changed"
AXIS_RANGE_CHANGED = "flow.axis.range_changed"
AXIS_RANGE_AUTO_UPDATED = "flow.axis.range_auto_updated"
TRANSFORM_CHANGED = "flow.transform.changed"
DISPLAY_MODE_CHANGED = "flow.display.mode_changed"

# Statistics events
STATS_COMPUTED = "flow.stats.computed"
STATS_INVALIDATED = "flow.stats.invalidated"

# Compensation events
COMPENSATION_APPLIED = "flow.compensation.applied"
