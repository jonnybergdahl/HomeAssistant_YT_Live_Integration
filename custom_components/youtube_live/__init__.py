"""The YouTube Live integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CalendarCoordinator, StreamStatusCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.BINARY_SENSOR]


@dataclass
class YouTubeLiveRuntimeData:
    """Runtime data for the YouTube Live integration."""

    calendar_coordinator: CalendarCoordinator
    stream_status_coordinator: StreamStatusCoordinator
    sensor_add_entities: AddEntitiesCallback | None = None


type YouTubeLiveConfigEntry = ConfigEntry[YouTubeLiveRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Set up YouTube Live from a config entry."""
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

    # Now that platforms are set up, do the first sensor refresh
    await stream_status_coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
