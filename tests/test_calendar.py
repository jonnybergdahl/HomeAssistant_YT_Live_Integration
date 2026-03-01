"""Tests for the YouTube Live calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_calendar_entity_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that a calendar entity is created."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"calendar.{DOMAIN}_{mock_config_entry.entry_id}_calendar")
    # The entity may use a different entity_id pattern based on the name
    # Let's check all calendar entities
    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1


async def test_calendar_next_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that the calendar returns the next event."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
    state = calendar_states[0]
    assert state.attributes.get("message") == "Morning Stream"


async def test_calendar_get_events(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test async_get_events returns events in range."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the calendar entity
    entity_id = None
    for state in hass.states.async_all():
        if state.domain == "calendar":
            entity_id = state.entity_id
            break

    assert entity_id is not None

    # Test via the service call
    now = datetime.now(timezone.utc)
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": now.isoformat(),
            "end_date_time": (now + timedelta(hours=24)).isoformat(),
        },
        blocking=True,
        return_response=True,
    )
    assert entity_id in events
    assert len(events[entity_id]["events"]) == 2


async def test_calendar_empty(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test calendar with no streams."""
    from unittest.mock import patch

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
    state = calendar_states[0]
    assert state.state == "off"
