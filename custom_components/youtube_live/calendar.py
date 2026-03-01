"""Calendar platform for the YouTube Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import CalendarCoordinator

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry, YouTubeLiveSharedData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    shared: YouTubeLiveSharedData = hass.data[DOMAIN]
    entity = YouTubeLiveCalendar(hass)
    shared.calendar_entity = entity
    async_add_entities([entity])


class YouTubeLiveCalendar(CalendarEntity):
    """Shared calendar entity aggregating streams from all channels."""

    _attr_has_entity_name = True
    _attr_name = "YouTube Live Streams"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the calendar entity."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_calendar"
        self._unsubs: dict[str, callable] = {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to all current coordinators when added to hass."""
        shared: YouTubeLiveSharedData = self.hass.data[DOMAIN]
        for entry_id, coordinator in shared.coordinators.items():
            self._subscribe(entry_id, coordinator)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from all coordinators when removed."""
        for unsub in self._unsubs.values():
            unsub()
        self._unsubs.clear()

    def register_coordinator(self, coordinator: CalendarCoordinator) -> None:
        """Register a new coordinator (when a new channel is added)."""
        entry_id = coordinator.config_entry.entry_id
        if entry_id not in self._unsubs:
            self._subscribe(entry_id, coordinator)
        # Trigger immediate state recalculation with the new data
        self.async_write_ha_state()

    def unregister_coordinator(self, entry_id: str) -> None:
        """Unregister a coordinator (when a channel is removed)."""
        unsub = self._unsubs.pop(entry_id, None)
        if unsub:
            unsub()
        # Trigger state update since data changed
        self.async_write_ha_state()

    def _subscribe(self, entry_id: str, coordinator: CalendarCoordinator) -> None:
        """Subscribe to a coordinator's updates."""
        self._unsubs[entry_id] = coordinator.async_add_listener(
            self._handle_coordinator_update
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from any coordinator."""
        self.async_write_ha_state()

    def _get_all_streams(self) -> list:
        """Aggregate streams from all coordinators."""
        shared: YouTubeLiveSharedData = self.hass.data[DOMAIN]
        all_streams = []
        for coordinator in shared.coordinators.values():
            if coordinator.data:
                all_streams.extend(coordinator.data)
        all_streams.sort(key=lambda s: s.scheduled_start)
        return all_streams

    @staticmethod
    def _stream_to_event(stream) -> CalendarEvent:
        """Convert an UpcomingStream to a CalendarEvent."""
        return CalendarEvent(
            start=stream.scheduled_start,
            end=stream.scheduled_start
            + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS),
            summary=f"{stream.channel} - {stream.title}",
            description=stream.url,
            uid=stream.video_id,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event across all channels."""
        streams = self._get_all_streams()
        if not streams:
            return None
        now = datetime.now().astimezone()
        for stream in streams:
            end = stream.scheduled_start + timedelta(
                hours=DEFAULT_STREAM_DURATION_HOURS
            )
            if end > now:
                return self._stream_to_event(stream)
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        streams = self._get_all_streams()
        events = []
        for stream in streams:
            event_start = stream.scheduled_start
            event_end = event_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
            if event_start < end_date and event_end > start_date:
                events.append(self._stream_to_event(stream))
        return events
