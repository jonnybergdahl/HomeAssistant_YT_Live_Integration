"""Binary sensor platform for the YouTube Live integration."""

from __future__ import annotations

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

from .const import DOMAIN
from .coordinator import StreamStatusCoordinator

if TYPE_CHECKING:
    from . import YouTubeLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor platform."""
    stream_status_coordinator = entry.runtime_data.stream_status_coordinator
    async_add_entities([YouTubeLiveChannelSensor(stream_status_coordinator, entry)])


class YouTubeLiveChannelSensor(
    CoordinatorEntity[StreamStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a YouTube channel is currently live."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: StreamStatusCoordinator,
        entry: YouTubeLiveConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_live"
        self._attr_name = f"{entry.title} Live"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

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
        attrs: dict[str, Any] = {
            "channel": self._entry.title,
        }

        if self.coordinator.data is not None:
            live_streams = [
                video_id
                for video_id, status in self.coordinator.data.statuses.items()
                if status.is_live
            ]
            attrs["live_streams"] = live_streams

        return attrs
