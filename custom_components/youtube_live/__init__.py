"""The YouTube Live integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import CalendarCoordinator, StreamStatusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR]


@dataclass
class YouTubeLiveRuntimeData:
    """Runtime data for a YouTube Live group config entry."""

    calendar_coordinator: CalendarCoordinator
    stream_status_coordinator: StreamStatusCoordinator


type YouTubeLiveConfigEntry = ConfigEntry[YouTubeLiveRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Set up a YouTube Live group from a config entry."""
    calendar_coordinator = CalendarCoordinator(hass, entry)
    stream_status_coordinator = StreamStatusCoordinator(
        hass, entry, calendar_coordinator
    )

    await calendar_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = YouTubeLiveRuntimeData(
        calendar_coordinator=calendar_coordinator,
        stream_status_coordinator=stream_status_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await stream_status_coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
