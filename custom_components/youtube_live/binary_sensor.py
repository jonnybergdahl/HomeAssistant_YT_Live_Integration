"""Binary sensor platform for the YouTube Live integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_CHANNEL_HANDLES, DEFAULT_STREAM_DURATION_HOURS, DOMAIN
from .coordinator import StreamStatusCoordinator

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from yt_live_scraper import UpcomingStream
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

    # Remove entities that are no longer in the config
    ent_reg = er.async_get(hass)
    existing_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    handle_slugs = {slugify(h.lstrip("@")) for h in handles}
    for entity_entry in existing_entries:
        if entity_entry.domain != "binary_sensor":
            continue
        # The unique_id format is f"{entry.entry_id}_{handle_slug}_live"
        # and f"{entry.entry_id}_any_live"
        uid = entity_entry.unique_id
        if not uid.startswith(f"{entry.entry_id}_"):
            continue
        suffix = uid[len(entry.entry_id) + 1:]
        if suffix == "any_live":
            continue
        if suffix.endswith("_live"):
            slug = suffix[:-5]
            if slug not in handle_slugs:
                ent_reg.async_remove(entity_entry.entity_id)

    # Add new entities
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

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
        handle: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        # Must be set as instance attr AFTER super().__init__() so the
        # @cached_property Entity.has_entity_name picks it up and the
        # entity registry stores False — preventing HA from prepending
        # the device name to the friendly_name.
        self._attr_has_entity_name = False
        self._entry = entry
        self._handle = handle
        handle_slug = slugify(handle.lstrip("@"))
        self._attr_unique_id = f"{entry.entry_id}_{handle_slug}_live"
        self._attr_device_info = _group_device_info(entry)
        object_id = f"youtube_live_{handle_slug}"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"binary_sensor.{object_id}"
        self._attr_name = f"{handle.lstrip('@')} Live"

    @property
    def _channel_name(self) -> str:
        """Best known display name for this channel."""
        key = self.coordinator.calendar_coordinator._hkey(self._handle)
        return self.coordinator.calendar_coordinator.channel_names.get(
            key, self._handle.lstrip("@")
        )

    def _next_stream(self) -> UpcomingStream | None:
        """Return this channel's live stream, or the next upcoming one."""
        calendar = self.coordinator.calendar_coordinator
        streams = calendar.streams_for_handle(self._handle)
        
        live_statuses = self.coordinator.data.statuses if self.coordinator.data else {}
        
        # 1. Look for a stream in the calendar that is currently live.
        for stream in streams:
            status = live_statuses.get(stream.video_id)
            if status and status.is_live:
                return stream

        # 2. Look for any stream being tracked that is live for this channel,
        # even if it's no longer in the calendar data.
        if self.coordinator.data:
            for vid, status in live_statuses.items():
                if status.is_live:
                    if vid in self.coordinator.stream_metadata:
                        metadata = self.coordinator.stream_metadata[vid]
                        if metadata.handle == self._handle:
                            return metadata.stream

        now = datetime.now().astimezone()
        for stream in streams:
            # Skip streams that have ended according to the status coordinator
            status = live_statuses.get(stream.video_id)
            if status and status.ended:
                continue

            end = stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
            if end > now:
                return stream
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the friendly name when coordinator data changes."""
        self._attr_name = self._channel_name
        super()._handle_coordinator_update()

    @property
    def entity_picture(self) -> str | None:
        """Return the stream thumbnail when live, else the channel avatar."""
        if self.is_on:
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
        
        # Check streams currently in the calendar
        streams = self.coordinator.calendar_coordinator.streams_for_handle(self._handle)
        stream_ids = {s.video_id for s in streams}
        statuses = self.coordinator.data.statuses
        
        for vid, status in statuses.items():
            if status.is_live:
                # If it's in the calendar for this handle, it's live.
                if vid in stream_ids:
                    return True
                
                # If it's NOT in the calendar, we need to check if it's
                # one of ours. We can check the full list of streams
                # currently in the StreamStatusCoordinator's internal states
                # and see if any that are live match our handle.
                if vid in self.coordinator.stream_metadata:
                    metadata = self.coordinator.stream_metadata[vid]
                    if metadata.handle == self._handle:
                        return True
        
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        is_live = self.is_on
        stream = self._next_stream() if is_live else None
        return {
            "channel_handle": self._handle,
            "channel_name": self._channel_name,
            "group": self._entry.title,
            "stream_id": stream.video_id if stream else None,
            "stream_title": stream.title if stream else None,
            "url": stream.url if stream else None,
            "stream_start": stream.scheduled_start.isoformat() if stream else None,
        }


class YouTubeLiveGroupSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether *any* channel in the group is live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "group_any_live"

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the aggregate sensor."""
        super().__init__(coordinator)
        self._attr_has_entity_name = False
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
        return self._first_live_stream is not None

    @property
    def _first_live_stream(self) -> UpcomingStream | None:
        """Return the first live stream in the group."""
        if self.coordinator.data is None:
            return None
        
        statuses = self.coordinator.data.statuses
        # 1. Check streams currently in the calendar
        if self.coordinator.calendar_coordinator.data:
            for stream in self.coordinator.calendar_coordinator.data:
                status = statuses.get(stream.video_id)
                if status and status.is_live:
                    return stream
        
        # 2. Check streams in metadata (those that might have dropped from calendar)
        for vid, status in statuses.items():
            if status.is_live:
                if vid in self.coordinator.stream_metadata:
                    return self.coordinator.stream_metadata[vid].stream
                    
        return None

    @property
    def entity_picture(self) -> str | None:
        """Return the thumbnail of the first live stream."""
        if stream := self._first_live_stream:
            return stream.thumbnail_url
        return None

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
        
        attrs = {
            "group": self._entry.title,
            "channel_handles": list(self._entry.data.get(CONF_CHANNEL_HANDLES, [])),
            "live_stream_ids": live_ids,
            "live_count": len(live_ids),
        }

        if stream := self._first_live_stream:
            # Find the handle for this stream
            handle = None
            calendar = self.coordinator.calendar_coordinator
            for h in self._entry.data.get(CONF_CHANNEL_HANDLES, []):
                key = calendar._hkey(h)
                display_name = calendar.channel_names.get(key)
                if (display_name and stream.channel.lower() == display_name.lower()) or (
                    stream.channel.lower() == h.lstrip("@").lower()
                ):
                    handle = h
                    break
            
            attrs.update({
                "live_channel_handle": handle,
                "live_channel_name": stream.channel,
                "live_stream_title": stream.title,
                "live_url": stream.url,
            })

        return attrs
