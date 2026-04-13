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
from homeassistant.util import slugify

from .const import DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import CalendarCoordinator

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one calendar entity per channel group."""
    runtime_data = entry.runtime_data
    async_add_entities([YouTubeLiveCalendar(runtime_data.calendar_coordinator, entry)])


class YouTubeLiveCalendar(
    CoordinatorEntity[CalendarCoordinator], CalendarEntity
):
    """Calendar entity listing upcoming streams for a single group."""

    _attr_has_entity_name = False

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
        object_id = f"youtube_live_{slugify(entry.title)}"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"calendar.{object_id}"

    @property
    def name(self) -> str:
        """Return a friendly name for the calendar."""
        return f"{self._entry.title} streams"

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
        """Return the next upcoming event in this group."""
        streams = self.coordinator.data or []
        if not streams:
            return None
        now = datetime.now().astimezone()
        for stream in sorted(streams, key=lambda s: s.scheduled_start):
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
        streams = self.coordinator.data or []
        events: list[CalendarEvent] = []
        for stream in streams:
            event_start = stream.scheduled_start
            event_end = event_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
            if event_start < end_date and event_end > start_date:
                events.append(self._stream_to_event(stream))
        events.sort(key=lambda e: e.start)
        return events
