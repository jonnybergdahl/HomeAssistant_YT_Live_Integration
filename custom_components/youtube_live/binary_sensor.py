"""Binary sensor platform for the YouTube Live integration."""

from __future__ import annotations

import logging
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
from homeassistant.util import slugify

from .const import CONF_CHANNEL_HANDLES, DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import StreamStatusCoordinator

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for a channel group."""
    runtime_data = entry.runtime_data
    stream_status_coordinator = runtime_data.stream_status_coordinator

    handles: list[str] = list(entry.data.get(CONF_CHANNEL_HANDLES, []))

    entities: list[BinarySensorEntity] = [
        YouTubeLiveChannelSensor(stream_status_coordinator, entry, handle)
        for handle in handles
    ]
    entities.append(YouTubeLiveGroupSensor(stream_status_coordinator, entry))

    async_add_entities(entities)


def _group_device_info(entry: YouTubeLiveConfigEntry) -> DeviceInfo:
    """Return the shared device info for a group's entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        entry_type=DeviceEntryType.SERVICE,
    )


class YouTubeLiveChannelSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a specific channel is currently live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
        handle: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._handle = handle
        handle_slug = slugify(handle.lstrip("@"))
        self._attr_unique_id = f"{entry.entry_id}_{handle_slug}_live"
        self._attr_device_info = _group_device_info(entry)
        object_id = f"youtube_live_{handle_slug}"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"binary_sensor.{object_id}"

    @property
    def _channel_name(self) -> str:
        """Best known display name for this channel."""
        key = self.coordinator.calendar_coordinator._hkey(self._handle)
        return self.coordinator.calendar_coordinator.channel_names.get(
            key, self._handle.lstrip("@")
        )

    def _next_stream(self):
        """Return this channel's live stream, or the next upcoming one."""
        calendar = self.coordinator.calendar_coordinator
        streams = calendar.streams_for_handle(self._handle)
        if not streams:
            return None

        live_statuses = self.coordinator.data.statuses if self.coordinator.data else {}
        for stream in streams:
            status = live_statuses.get(stream.video_id)
            if status and status.is_live:
                return stream

        now = datetime.now().astimezone()
        for stream in streams:
            end = stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
            if end > now:
                return stream
        return None

    @property
    def name(self) -> str:
        """Return the stream title, or fall back to the channel name."""
        stream = self._next_stream()
        if stream is not None:
            return stream.title
        return f"{self._channel_name} Live"

    @property
    def entity_picture(self) -> str | None:
        """Return the stream thumbnail when live/upcoming, else the channel avatar."""
        stream = self._next_stream()
        if stream is not None:
            return stream.thumbnail_url
        key = self.coordinator.calendar_coordinator._hkey(self._handle)
        return self.coordinator.calendar_coordinator.channel_thumbnail_urls.get(key)

    @property
    def is_on(self) -> bool | None:
        """Return true if any of this channel's streams is currently live."""
        if self.coordinator.data is None:
            return None
        streams = self.coordinator.calendar_coordinator.streams_for_handle(self._handle)
        stream_ids = {s.video_id for s in streams}
        if not stream_ids:
            return False
        statuses = self.coordinator.data.statuses
        return any(
            status.is_live
            for vid, status in statuses.items()
            if vid in stream_ids
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        stream = self._next_stream()
        return {
            "channel_handle": self._handle,
            "channel_name": self._channel_name,
            "group": self._entry.title,
            "stream_id": stream.video_id if stream else None,
            "url": stream.url if stream else None,
            "stream_start": stream.scheduled_start.isoformat() if stream else None,
        }


class YouTubeLiveGroupSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether *any* channel in the group is live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_has_entity_name = False
    _attr_translation_key = "group_any_live"

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the aggregate sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_any_live"
        self._attr_device_info = _group_device_info(entry)
        object_id = f"youtube_live_{slugify(entry.title)}_any_live"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"binary_sensor.{object_id}"

    @property
    def name(self) -> str:
        """Friendly name for the aggregate sensor."""
        return f"{self._entry.title} live"

    @property
    def is_on(self) -> bool | None:
        """Return true if any stream in the group is currently live."""
        if self.coordinator.data is None:
            return None
        return any(
            status.is_live for status in self.coordinator.data.statuses.values()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes listing live channels."""
        live_ids: list[str] = []
        if self.coordinator.data is not None:
            live_ids = [
                vid
                for vid, status in self.coordinator.data.statuses.items()
                if status.is_live
            ]
        return {
            "group": self._entry.title,
            "channel_handles": list(self._entry.data.get(CONF_CHANNEL_HANDLES, [])),
            "live_stream_ids": live_ids,
            "live_count": len(live_ids),
        }
