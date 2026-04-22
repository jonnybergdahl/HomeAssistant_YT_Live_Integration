"""Sensor platform for the YouTube Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
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
    """Set up the upcoming streams sensor."""
    runtime_data = entry.runtime_data
    async_add_entities([YouTubeLiveUpcomingSensor(runtime_data.calendar_coordinator, entry)])


class YouTubeLiveUpcomingSensor(
    CoordinatorEntity[CalendarCoordinator], SensorEntity
):
    """Sensor showing upcoming streams in a flat format for ESPHome."""

    _attr_has_entity_name = True
    _attr_translation_key = "upcoming_streams"

    def __init__(
        self,
        coordinator: CalendarCoordinator,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_upcoming"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
        object_id = f"youtube_live_{slugify(entry.title)}_upcoming"
        self.entity_id = f"sensor.{object_id}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Upcoming"

    @property
    def native_value(self) -> int:
        """Return the count of upcoming streams."""
        streams = self.coordinator.data or []
        now = datetime.now().astimezone()
        # Filter out streams that have already ended based on default duration
        upcoming = [
            s for s in streams 
            if s.scheduled_start.astimezone() + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS) > now
        ]
        return len(upcoming)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return flat list of upcoming streams as attributes."""
        streams = self.coordinator.data or []
        now = datetime.now().astimezone()
        
        # Sort by start time and filter out past streams
        upcoming = sorted(
            [
                s for s in streams 
                if s.scheduled_start.astimezone() + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS) > now
            ],
            key=lambda s: s.scheduled_start
        )

        attrs = {}
        for i in range(5):
            prefix = f"event_{i}"
            if i < len(upcoming):
                stream = upcoming[i]
                title = stream.title or ""
                if len(title) > 80:
                    title = title[:77] + "..."
                
                attrs[f"{prefix}_title"] = title
                attrs[f"{prefix}_start"] = stream.scheduled_start.isoformat()
                attrs[f"{prefix}_video_id"] = stream.video_id
                attrs[f"{prefix}_channel"] = stream.channel
                attrs[f"{prefix}_duration"] = DEFAULT_STREAM_DURATION_HOURS * 60
            else:
                attrs[f"{prefix}_title"] = ""
                attrs[f"{prefix}_start"] = ""
                attrs[f"{prefix}_video_id"] = ""
                attrs[f"{prefix}_channel"] = ""
                attrs[f"{prefix}_duration"] = ""

        return attrs
