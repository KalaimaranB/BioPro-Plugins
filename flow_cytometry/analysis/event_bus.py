"""Event bus for flow cytometry state management.

Provides a centralized event dispatcher that decouples UI components from
analysis logic. All significant state changes are published as events,
allowing UI components to subscribe to changes without tight coupling.

This enables:
- Easier testing and mocking
- Cleaner separation of concerns
- Better debuggability (all state changes are logged)
- Support for undo/redo via event replay
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """All possible events in the flow cytometry system."""
    
    # Gate events
    GATE_CREATED = "gate.created"
    GATE_RENAMED = "gate.renamed"
    GATE_DELETED = "gate.deleted"
    GATE_MODIFIED = "gate.modified"
    GATE_PROPAGATED = "gate.propagated"
    GATE_SELECTED = "gate.selected"
    GATE_PREVIEW = "gate.preview"
    
    # Sample events
    SAMPLE_SELECTED = "sample.selected"
    SAMPLE_DESELECTED = "sample.deselected"
    SAMPLE_LOADED = "sample.loaded"
    
    # Canvas/Rendering events
    RENDER_MODE_CHANGED = "render.mode_changed"
    AXIS_PARAMS_CHANGED = "axis.params_changed"
    AXIS_RANGE_CHANGED = "axis.range_changed"
    AXIS_RANGE_AUTO_UPDATED = "axis.range_auto_updated"
    TRANSFORM_CHANGED = "transform.changed"
    DISPLAY_MODE_CHANGED = "display.mode_changed"
    
    # Statistics events
    STATS_COMPUTED = "stats.computed"
    STATS_INVALIDATED = "stats.invalidated"
    
    # Compensation events
    COMPENSATION_APPLIED = "compensation.applied"


@dataclass
class Event:
    """Represents a state change event in the system."""
    
    type: EventType
    data: dict[str, Any]  # Event-specific data
    source: str = "unknown"  # Component that emitted the event
    
    def __str__(self) -> str:
        return f"Event({self.type.value}, {self.data}, from={self.source})"


class EventBus:
    """Central event dispatcher for the flow cytometry module.
    
    Components publish events when state changes occur. Other components
    subscribe to event types they care about and get notified immediately.
    
    Example:
        >>> bus = EventBus()
        >>> def on_gate_created(event):
        ...     print(f"Gate created: {event.data['gate_name']}")
        >>> bus.subscribe(EventType.GATE_CREATED, on_gate_created)
        >>> bus.publish(Event(
        ...     type=EventType.GATE_CREATED,
        ...     data={"gate_id": "g1", "gate_name": "Live"},
        ...     source="gate_controller"
        ... ))
    """
    
    def __init__(self, enable_logging: bool = True):
        """Initialize the event bus.
        
        Args:
            enable_logging: If True, log all events for debugging.
        """
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._event_history: list[Event] = []
        self._enable_logging = enable_logging
        self._paused = False
        self._queue: list[Event] = []
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> Callable:
        """Register a handler for a specific event type.
        
        Args:
            event_type: The event type to listen for.
            handler: Callable that receives the event.
            
        Returns:
            Unsubscribe function to remove handler later.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(handler)
        
        # Return unsubscribe function
        def unsubscribe():
            if handler in self._subscribers.get(event_type, []):
                self._subscribers[event_type].remove(handler)
        
        return unsubscribe
    
    def subscribe_any(self, handler: Callable[[Event], None]) -> Callable:
        """Subscribe to all events regardless of type.
        
        Args:
            handler: Callable that receives all events.
            
        Returns:
            Unsubscribe function.
        """
        if None not in self._subscribers:
            self._subscribers[None] = []
        
        self._subscribers[None].append(handler)
        
        def unsubscribe():
            if handler in self._subscribers.get(None, []):
                self._subscribers[None].remove(handler)
        
        return unsubscribe
    
    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.
        
        Args:
            event: The event to broadcast.
        """
        if self._enable_logging:
            logger.debug(f"Published: {event}")
        
        if self._paused:
            self._queue.append(event)
            return

        # Store in history for debugging/replay
        self._event_history.append(event)
        
        # Deliver to specific event type subscribers
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error for {event.type.value}: {e}", exc_info=True)
        
        # Deliver to "any event" subscribers
        if None in self._subscribers:
            for handler in self._subscribers[None]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error (any): {e}", exc_info=True)
    
    def pause(self) -> None:
        """Pause event dispatching."""
        self._paused = True
        self._queue = []
    
    def resume(self) -> None:
        """Resume event dispatching and flush queued events."""
        self._paused = False
        for event in self._queue:
            self.publish(event)
        self._queue = []
    
    def clear_history(self) -> None:
        """Clear the event history (for memory management)."""
        self._event_history.clear()
    
    def get_history(self, event_type: Optional[EventType] = None) -> list[Event]:
        """Get event history, optionally filtered by type.
        
        Args:
            event_type: If provided, only return events of this type.
            
        Returns:
            List of events.
        """
        if event_type is None:
            return self._event_history.copy()
        return [e for e in self._event_history if e.type == event_type]
    
    def clear_subscribers(self, event_type: Optional[EventType] = None) -> None:
        """Clear all subscribers (mainly for testing).
        
        Args:
            event_type: If provided, only clear subscribers for this type.
        """
        if event_type is None:
            self._subscribers.clear()
        elif event_type in self._subscribers:
            self._subscribers[event_type].clear()
    
    def subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        """Get the number of subscribers.
        
        Args:
            event_type: If provided, count only subscribers for this type.
            
        Returns:
            Number of subscribers.
        """
        if event_type is None:
            return sum(len(handlers) for handlers in self._subscribers.values())
        return len(self._subscribers.get(event_type, []))
