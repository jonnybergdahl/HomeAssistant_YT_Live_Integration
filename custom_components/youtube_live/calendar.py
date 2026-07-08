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

from .const import DOMAIN
from .coordinator import YouTubeLiveCoordinator

if TYPE_CHECKING:
    from yt_live_scraper import UpcomingStream

    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one calendar entity per channel group."""
    async_add_entities([YouTubeLiveCalendar(entry)])


class YouTubeLiveCalendar(
    CoordinatorEntity[YouTubeLiveCoordinator], CalendarEntity
):
    """Calendar entity listing upcoming streams for a single group."""

    # Names embed the channel/group title, so opt out of device-based naming.
    _attr_has_entity_name = False

    def __init__(
        self,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(entry.runtime_data.coordinator)
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

    def _stream_to_event(self, stream: UpcomingStream) -> CalendarEvent:
        """Convert an UpcomingStream to a CalendarEvent."""
        # The coordinator is the single source of truth for the end time
        # (it accounts for a stream that ended early).
        end_time = self.coordinator.stream_end_time(stream)

        status = (
            self.coordinator.data.statuses.get(stream.video_id)
            if self.coordinator.data
            else None
        )
        if status and status.is_live:
            # If the stream is currently live, ensure the end time is in the future.
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
        streams = self.coordinator.relevant_streams()
        if not streams:
            return None

        now = dt_util.now()
        for stream in sorted(streams, key=lambda s: s.scheduled_start):
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
        events: list[CalendarEvent] = []
        for stream in self.coordinator.relevant_streams():
            event = self._stream_to_event(stream)
            if event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda e: e.start)
        return events
