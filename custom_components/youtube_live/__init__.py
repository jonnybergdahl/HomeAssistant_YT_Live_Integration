"""The YouTube Live integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import YouTubeLiveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]


@dataclass
class YouTubeLiveRuntimeData:
    """Runtime data for a YouTube Live group config entry."""

    coordinator: YouTubeLiveCoordinator


type YouTubeLiveConfigEntry = ConfigEntry[YouTubeLiveRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Set up a YouTube Live group from a config entry."""
    coordinator = YouTubeLiveCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = YouTubeLiveRuntimeData(
        coordinator=coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
