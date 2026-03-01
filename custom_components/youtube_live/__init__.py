"""The YouTube Live integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CalendarCoordinator, StreamStatusCoordinator

if TYPE_CHECKING:
    from .calendar import YouTubeLiveCalendar

_LOGGER = logging.getLogger(__name__)

PLATFORMS_PER_ENTRY: list[Platform] = [Platform.BINARY_SENSOR]


@dataclass
class YouTubeLiveRuntimeData:
    """Runtime data for the YouTube Live integration."""

    calendar_coordinator: CalendarCoordinator
    stream_status_coordinator: StreamStatusCoordinator
    sensor_add_entities: AddEntitiesCallback | None = None


@dataclass
class YouTubeLiveSharedData:
    """Shared data across all config entries."""

    coordinators: dict[str, CalendarCoordinator] = field(default_factory=dict)
    calendar_owner_entry_id: str | None = None
    calendar_entity: YouTubeLiveCalendar | None = None


type YouTubeLiveConfigEntry = ConfigEntry[YouTubeLiveRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the YouTube Live integration."""
    hass.data[DOMAIN] = YouTubeLiveSharedData()
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Set up YouTube Live from a config entry."""
    shared: YouTubeLiveSharedData = hass.data[DOMAIN]

    calendar_coordinator = CalendarCoordinator(hass, entry)
    stream_status_coordinator = StreamStatusCoordinator(
        hass, entry, calendar_coordinator
    )

    await calendar_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = YouTubeLiveRuntimeData(
        calendar_coordinator=calendar_coordinator,
        stream_status_coordinator=stream_status_coordinator,
    )

    # Register coordinator in shared data
    shared.coordinators[entry.entry_id] = calendar_coordinator

    # Forward binary sensor platform (always per-entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_PER_ENTRY)

    # Forward calendar platform only if no entry owns it yet
    if shared.calendar_owner_entry_id is None:
        shared.calendar_owner_entry_id = entry.entry_id
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.CALENDAR]
        )
    elif shared.calendar_entity is not None:
        # Calendar already exists — register this new coordinator with it
        shared.calendar_entity.register_coordinator(calendar_coordinator)

    # Now that platforms are set up, do the first sensor refresh
    await stream_status_coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YouTubeLiveConfigEntry,
) -> bool:
    """Unload a config entry."""
    shared: YouTubeLiveSharedData = hass.data[DOMAIN]

    # Remove coordinator from shared data
    shared.coordinators.pop(entry.entry_id, None)

    # Notify calendar entity that this coordinator is gone
    if shared.calendar_entity is not None:
        shared.calendar_entity.unregister_coordinator(entry.entry_id)

    # Determine which platforms to unload from this entry
    platforms_to_unload = list(PLATFORMS_PER_ENTRY)

    is_calendar_owner = shared.calendar_owner_entry_id == entry.entry_id
    if is_calendar_owner:
        platforms_to_unload.append(Platform.CALENDAR)
        shared.calendar_owner_entry_id = None
        shared.calendar_entity = None

    result = await hass.config_entries.async_unload_platforms(
        entry, platforms_to_unload
    )

    # If we just unloaded the calendar but other entries remain, re-forward it
    # from another entry. Defer this so it runs after the unload completes.
    if is_calendar_owner and shared.coordinators:
        other_entry_id = next(iter(shared.coordinators))
        other_entry = hass.config_entries.async_get_entry(other_entry_id)
        if other_entry is not None:
            shared.calendar_owner_entry_id = other_entry_id
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setups(
                    other_entry, [Platform.CALENDAR]
                )
            )

    return result
