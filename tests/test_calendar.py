"""Tests for the YouTube Live calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLES, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_one_calendar_per_group(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Each group entry produces exactly one calendar entity."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
    assert calendar_states[0].entity_id == "calendar.youtube_live_test_group"


async def test_calendar_next_event(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Calendar exposes the nearest upcoming event."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("calendar.youtube_live_test_group")
    assert state is not None
    assert state.attributes.get("message") == "TestChannel - Morning Stream"


async def test_calendar_get_events(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """async_get_events returns all events in range."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = "calendar.youtube_live_test_group"
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
    """Calendar with no streams is off and has no next event."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("calendar.youtube_live_test_group")
    assert state is not None
    assert state.state == "off"


async def test_calendar_per_group_scoping(
    hass: HomeAssistant,
    mock_is_stream_live,
) -> None:
    """Each group's calendar shows only its own streams, not other groups'."""
    now = datetime.now(timezone.utc)
    streams_a = [
        make_stream(
            video_id="a1",
            title="Gaming Stream",
            channel="ChannelA",
            scheduled_start=now + timedelta(hours=3),
        ),
    ]
    streams_b = [
        make_stream(
            video_id="b1",
            title="Tech Stream",
            channel="ChannelB",
            scheduled_start=now + timedelta(hours=1),
        ),
    ]

    entry_a = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@ChannelA"]},
        title="Gaming",
    )
    entry_b = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="tech",
        data={CONF_CHANNEL_HANDLES: ["@ChannelB"]},
        title="Tech",
    )

    entry_a.add_to_hass(hass)
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_a,
    ):
        await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

    entry_b.add_to_hass(hass)
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_b,
    ):
        await hass.config_entries.async_setup(entry_b.entry_id)
        await hass.async_block_till_done()

    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 2

    gaming = hass.states.get("calendar.youtube_live_gaming")
    tech = hass.states.get("calendar.youtube_live_tech")
    assert gaming is not None
    assert tech is not None
    assert gaming.attributes.get("message") == "ChannelA - Gaming Stream"
    assert tech.attributes.get("message") == "ChannelB - Tech Stream"
