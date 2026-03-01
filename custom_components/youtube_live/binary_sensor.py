"""Binary sensor platform for the YouTube Live integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StreamStatusCoordinator, StreamStatusData, UpcomingStream

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor platform."""
    runtime_data = entry.runtime_data
    calendar_coordinator = runtime_data.calendar_coordinator
    stream_status_coordinator = runtime_data.stream_status_coordinator

    # Store the add_entities callback for dynamic entity creation
    runtime_data.sensor_add_entities = async_add_entities

    # Track which video IDs already have entities
    known_video_ids: set[str] = set()

    # Create entities for any streams already known
    streams = calendar_coordinator.data or []
    entities = []
    for stream in streams:
        known_video_ids.add(stream.video_id)
        entities.append(
            YouTubeLiveStreamSensor(
                stream_status_coordinator, entry, stream
            )
        )
    if entities:
        async_add_entities(entities)

    @callback
    def _async_on_calendar_update() -> None:
        """Handle new streams from the calendar coordinator."""
        streams = calendar_coordinator.data or []
        new_entities = []
        current_ids = {s.video_id for s in streams}

        for stream in streams:
            if stream.video_id not in known_video_ids:
                known_video_ids.add(stream.video_id)
                new_entities.append(
                    YouTubeLiveStreamSensor(
                        stream_status_coordinator, entry, stream
                    )
                )

        # Remove IDs for streams that are gone
        known_video_ids.intersection_update(current_ids)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        calendar_coordinator.async_add_listener(_async_on_calendar_update)
    )


class YouTubeLiveStreamSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a YouTube stream is live."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
        stream: UpcomingStream,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._stream = stream
        self._attr_unique_id = f"{entry.entry_id}_{stream.video_id}"
        self._attr_name = stream.title
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the stream is currently live."""
        if self.coordinator.data is None:
            return self._stream.live

        status = self.coordinator.data.statuses.get(self._stream.video_id)
        if status is not None:
            return status.is_live

        # Fall back to the live flag from get_upcoming_streams
        return self._stream.live

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "video_id": self._stream.video_id,
            "stream_url": self._stream.url,
            "thumbnail_url": self._stream.thumbnail_url,
            "scheduled_start": self._stream.scheduled_start.isoformat(),
            "channel": self._stream.channel,
        }
