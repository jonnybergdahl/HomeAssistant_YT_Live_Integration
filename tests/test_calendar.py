"""Tests for the YouTube Live calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLE, DOMAIN

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
    assert state.attributes.get("message") == "Test Channel - Morning Stream"


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

    entity_id = None
    for state in hass.states.async_all():
        if state.domain == "calendar":
            entity_id = state.entity_id
            break

    assert entity_id is not None

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
    with (
        patch(
            "custom_components.youtube_live.coordinator.get_upcoming_streams",
            return_value=[],
        ),
        patch(
            "custom_components.youtube_live.coordinator.get_channel",
            return_value="Test Channel",
        ),
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


async def test_single_calendar_multiple_channels(
    hass: HomeAssistant,
    mock_is_stream_live,
) -> None:
    """Test that only one calendar exists with streams from all channels."""
    now = datetime.now(timezone.utc)

    streams_a = [
        make_stream(
            video_id="a1",
            title="Channel A Stream",
            channel="Channel A",
            scheduled_start=now + timedelta(hours=3),
        ),
    ]
    streams_b = [
        make_stream(
            video_id="b1",
            title="Channel B Stream",
            channel="Channel B",
            scheduled_start=now + timedelta(hours=1),
        ),
    ]

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_a",
        data={CONF_CHANNEL_HANDLE: "@ChannelA"},
        title="@ChannelA",
    )
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_b",
        data={CONF_CHANNEL_HANDLE: "@ChannelB"},
        title="@ChannelB",
    )
    entry_a.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_a,
    ):
        await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

    # Add entry_b AFTER entry_a is set up to avoid HA auto-setting up all entries
    entry_b.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_b,
    ):
        await hass.config_entries.async_setup(entry_b.entry_id)
        await hass.async_block_till_done()

    # Only one calendar entity
    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1

    # Calendar should show the nearest event (Channel B Stream at +1h)
    state = calendar_states[0]
    assert state.attributes.get("message") == "Channel B - Channel B Stream"

    # get_events should return both streams
    entity_id = state.entity_id
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
    assert len(events[entity_id]["events"]) == 2


async def test_calendar_updates_when_channel_added(
    hass: HomeAssistant,
    mock_is_stream_live,
) -> None:
    """Test that the calendar updates immediately when a new channel is added."""
    now = datetime.now(timezone.utc)

    streams_a = [
        make_stream(
            video_id="a1",
            title="Channel A Stream",
            channel="Channel A",
            scheduled_start=now + timedelta(hours=3),
        ),
    ]
    streams_b = [
        make_stream(
            video_id="b1",
            title="Channel B Stream",
            channel="Channel B",
            scheduled_start=now + timedelta(hours=1),
        ),
    ]

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_a",
        data={CONF_CHANNEL_HANDLE: "@ChannelA"},
        title="@ChannelA",
    )
    entry_a.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_a,
    ):
        await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

    # After entry_a only: calendar shows Channel A's stream
    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
    state = calendar_states[0]
    assert state.attributes.get("message") == "Channel A - Channel A Stream"
    entity_id = state.entity_id

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
    assert len(events[entity_id]["events"]) == 1

    # Now add entry_b — calendar should update to include the new channel
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_b",
        data={CONF_CHANNEL_HANDLE: "@ChannelB"},
        title="@ChannelB",
    )
    entry_b.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_b,
    ):
        await hass.config_entries.async_setup(entry_b.entry_id)
        await hass.async_block_till_done()

    # Calendar should now show Channel B's nearer stream as next event
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("message") == "Channel B - Channel B Stream"

    # get_events should return both streams
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
    assert len(events[entity_id]["events"]) == 2


async def test_calendar_survives_entry_removal(
    hass: HomeAssistant,
    mock_is_stream_live,
) -> None:
    """Test that calendar keeps working after removing the owning entry."""
    now = datetime.now(timezone.utc)

    streams_a = [
        make_stream(
            video_id="a1",
            title="Channel A Stream",
            channel="Channel A",
            scheduled_start=now + timedelta(hours=1),
        ),
    ]
    streams_b = [
        make_stream(
            video_id="b1",
            title="Channel B Stream",
            channel="Channel B",
            scheduled_start=now + timedelta(hours=2),
        ),
    ]

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_a",
        data={CONF_CHANNEL_HANDLE: "@ChannelA"},
        title="@ChannelA",
    )
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_b",
        data={CONF_CHANNEL_HANDLE: "@ChannelB"},
        title="@ChannelB",
    )
    entry_a.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_a,
    ):
        await hass.config_entries.async_setup(entry_a.entry_id)
        await hass.async_block_till_done()

    # Add entry_b AFTER entry_a is set up to avoid HA auto-setting up all entries
    entry_b.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=streams_b,
    ):
        await hass.config_entries.async_setup(entry_b.entry_id)
        await hass.async_block_till_done()

    # Remove entry A (the calendar owner)
    await hass.config_entries.async_unload(entry_a.entry_id)
    await hass.async_block_till_done()

    # Calendar should still exist with entry B's streams
    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
    state = calendar_states[0]
    assert state.attributes.get("message") == "Channel B - Channel B Stream"
