"""Sensor platform for the YouTube Live integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

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
    """Set up the upcoming streams sensor."""
    async_add_entities([YouTubeLiveUpcomingSensor(entry.runtime_data.coordinator, entry)])


class YouTubeLiveUpcomingSensor(
    CoordinatorEntity[YouTubeLiveCoordinator], SensorEntity
):
    """Sensor showing upcoming streams in a flat format for ESPHome."""

    # Names embed the channel/group title, so opt out of device-based naming.
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: YouTubeLiveCoordinator,
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
        return f"{self._entry.title} upcoming"

    def _upcoming_streams(self) -> list[UpcomingStream]:
        """Return the group's still-active streams, sorted by start time.

        Uses the coordinator's shared stream set and active check so this
        sensor stays consistent with the calendar and binary sensors.
        """
        now = dt_util.now()
        upcoming = [
            s
            for s in self.coordinator.relevant_streams()
            if self.coordinator.is_stream_active(s, now)
        ]
        return sorted(upcoming, key=lambda s: s.scheduled_start)

    @property
    def native_value(self) -> int:
        """Return the count of upcoming streams."""
        return len(self._upcoming_streams())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return flat list of upcoming streams as attributes."""
        upcoming = self._upcoming_streams()

        attrs = {}
        for i in range(5):
            prefix = f"event_{i}"
            if i < len(upcoming):
                stream = upcoming[i]
                title = stream.title or ""
                if len(title) > 80:
                    title = title[:77] + "..."

                duration = self.coordinator.stream_end_time(stream) - stream.scheduled_start
                attrs[f"{prefix}_title"] = title
                attrs[f"{prefix}_start"] = stream.scheduled_start.isoformat()
                attrs[f"{prefix}_video_id"] = stream.video_id
                attrs[f"{prefix}_channel"] = stream.channel
                attrs[f"{prefix}_duration"] = int(duration.total_seconds() // 60)
            else:
                attrs[f"{prefix}_title"] = ""
                attrs[f"{prefix}_start"] = ""
                attrs[f"{prefix}_video_id"] = ""
                attrs[f"{prefix}_channel"] = ""
                # Keep a stable int type for duration across all slots.
                attrs[f"{prefix}_duration"] = 0

        return attrs
