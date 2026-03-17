"""Binary sensor platform for the YouTube Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import StreamStatusCoordinator

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor platform."""
    runtime_data = entry.runtime_data
    stream_status_coordinator = runtime_data.stream_status_coordinator
    calendar_coordinator = runtime_data.calendar_coordinator

    # Use the friendly channel name from stream data, fall back to handle
    channel_name = entry.title
    if calendar_coordinator.data:
        channel_name = calendar_coordinator.data[0].channel

    async_add_entities(
        [YouTubeLiveChannelSensor(stream_status_coordinator, entry, channel_name)]
    )


class YouTubeLiveChannelSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a YouTube channel is currently live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
        channel_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._channel_name = channel_name
        self._attr_unique_id = f"{entry.entry_id}_live"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=channel_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def suggested_object_id(self) -> str:
        """Return stable object ID for entity ID generation."""
        return f"{self._channel_name} live"

    def _next_stream(self):
        """Return the next upcoming or currently live stream."""
        streams = self.coordinator.calendar_coordinator.data
        if not streams:
            return None
        now = datetime.now().astimezone()
        for stream in streams:
            end = stream.scheduled_start + timedelta(
                hours=DEFAULT_STREAM_DURATION_HOURS
            )
            if end > now:
                return stream
        return None

    @property
    def name(self) -> str:
        """Return the stream title or channel fallback as friendly name."""
        stream = self._next_stream()
        if stream is not None:
            return stream.title
        return f"{self._channel_name} Live"

    @property
    def entity_picture(self) -> str | None:
        """Return the thumbnail of the next scheduled stream."""
        stream = self._next_stream()
        if stream is not None:
            return stream.thumbnail_url
        return None

    @property
    def is_on(self) -> bool | None:
        """Return true if any stream on this channel is currently live."""
        if self.coordinator.data is None:
            return None

        return any(
            status.is_live
            for status in self.coordinator.data.statuses.values()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        stream = self._next_stream()
        attrs: dict[str, Any] = {
            "channel_handle": self._entry.title,
            "channel_name": self._channel_name,
            "stream_id": stream.video_id if stream else None,
            "url": stream.url if stream else None,
            "stream_start": (
                stream.scheduled_start.isoformat() if stream else None
            ),
        }
        return attrs
