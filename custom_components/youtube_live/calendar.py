"""Calendar platform for the YouTube Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import CalendarCoordinator

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    coordinator = entry.runtime_data.calendar_coordinator
    async_add_entities([YouTubeLiveCalendar(coordinator, entry)])


class YouTubeLiveCalendar(
    CoordinatorEntity[CalendarCoordinator], CalendarEntity
):
    """Calendar entity showing upcoming YouTube live streams."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule"

    def __init__(
        self,
        coordinator: CalendarCoordinator,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _stream_to_event(self, stream) -> CalendarEvent:
        """Convert an UpcomingStream to a CalendarEvent."""
        return CalendarEvent(
            start=stream.scheduled_start,
            end=stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS),
            summary=stream.title,
            description=stream.url,
            uid=stream.video_id,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self.coordinator.data:
            return None
        now = datetime.now().astimezone()
        for stream in self.coordinator.data:
            end = stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
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
        if not self.coordinator.data:
            return []
        events = []
        for stream in self.coordinator.data:
            event_start = stream.scheduled_start
            event_end = event_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
            if event_start < end_date and event_end > start_date:
                events.append(self._stream_to_event(stream))
        return events
