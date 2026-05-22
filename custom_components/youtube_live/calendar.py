"""Calendar platform for the YouTube Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
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
    async_add_entities([YouTubeLiveCalendar(entry)])


class YouTubeLiveCalendar(
    CoordinatorEntity[CalendarCoordinator], CalendarEntity
):
    """Calendar entity listing upcoming streams for a single group."""

    _attr_has_entity_name = False

    def __init__(
        self,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(entry.runtime_data.calendar_coordinator)
        self._entry = entry
        self._stream_status_coordinator = entry.runtime_data.stream_status_coordinator
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

    def _stream_to_event(self, stream) -> CalendarEvent:
        """Convert an UpcomingStream to a CalendarEvent."""
        end_time = stream.scheduled_start + timedelta(
            hours=DEFAULT_STREAM_DURATION_HOURS
        )

        # If the stream is currently live, ensure the end time is in the future.
        if (
            self._stream_status_coordinator.data
            and (status := self._stream_status_coordinator.data.statuses.get(stream.video_id))
            and status.is_live
        ):
            now = dt_util.now()
            if end_time < now + timedelta(minutes=30):
                end_time = now + timedelta(minutes=30)

        return CalendarEvent(
            start=stream.scheduled_start,
            end=end_time,
            summary=f"{stream.channel} - {stream.title}",
            description=stream.url,
            uid=stream.video_id,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event in this group."""
        streams = self.coordinator.data or []
        statuses = self._stream_status_coordinator.data.statuses if self._stream_status_coordinator.data else {}
        
        # Combine current calendar streams and streams that dropped from calendar but are still live
        all_stream_ids = {s.video_id for s in streams}
        relevant_streams = list(streams)
        
        for vid, status in statuses.items():
            if status.is_live and vid not in all_stream_ids:
                if vid in self._stream_status_coordinator.stream_metadata:
                    relevant_streams.append(self._stream_status_coordinator.stream_metadata[vid].stream)

        if not relevant_streams:
            return None
            
        now = dt_util.now()
        for stream in sorted(relevant_streams, key=lambda s: s.scheduled_start):
            event = self._stream_to_event(stream)
            if event.end > now:
                return event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        streams = self.coordinator.data or []
        statuses = self._stream_status_coordinator.data.statuses if self._stream_status_coordinator.data else {}
        
        # Combine current calendar streams and streams that dropped from calendar but are still live
        all_stream_ids = {s.video_id for s in streams}
        relevant_streams = list(streams)
        
        for vid, status in statuses.items():
            if status.is_live and vid not in all_stream_ids:
                if vid in self._stream_status_coordinator.stream_metadata:
                    relevant_streams.append(self._stream_status_coordinator.stream_metadata[vid].stream)
        
        events: list[CalendarEvent] = []
        for stream in relevant_streams:
            event = self._stream_to_event(stream)
            if event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda e: e.start)
        return events
