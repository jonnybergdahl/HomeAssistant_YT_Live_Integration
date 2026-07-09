"""Tests for the YouTube Live upcoming sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from yt_live_scraper import StreamLiveStatus

from custom_components.youtube_live.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_upcoming_sensor_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The upcoming sensor shows flat attributes for upcoming streams."""
    now = datetime.now(timezone.utc)
    
    stream1 = make_stream(
        video_id="vid1",
        title="Future Stream 1",
        channel="Channel A",
        scheduled_start=now + timedelta(hours=1),
    )
    stream2 = make_stream(
        video_id="vid2",
        title="Future Stream 2" * 10,  # Long title
        channel="Channel B",
        scheduled_start=now + timedelta(hours=2),
    )
    
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream1, stream2],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.youtube_live_test_group_upcoming")
    assert state is not None
    assert state.name == "Test Group upcoming"
    assert state.state == "2"
    
    attrs = state.attributes
    
    # Stream 0
    assert attrs["event_0_title"] == "Future Stream 1"
    assert attrs["event_0_video_id"] == "vid1"
    assert attrs["event_0_channel"] == "Channel A"
    assert "event_0_start" in attrs
    assert attrs["event_0_duration"] == 120
    
    # Stream 1 - check truncation
    assert len(attrs["event_1_title"]) <= 80
    assert attrs["event_1_title"].endswith("...")
    assert attrs["event_1_video_id"] == "vid2"
    assert attrs["event_1_channel"] == "Channel B"
    
    # Stream 2 - empty
    assert attrs["event_2_title"] == ""
    assert attrs["event_2_video_id"] == ""
    assert attrs["event_2_channel"] == ""
    assert attrs["event_2_start"] == ""
    assert attrs["event_2_duration"] == 0
    
    # Stream 4 - empty
    assert attrs["event_4_title"] == ""


async def test_upcoming_sensor_drops_ended_stream(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A stream that has ended stops counting as upcoming (honors ended_at).

    The scheduled start is only 5 minutes ago, so under the old fixed-2h
    logic it would still count for ~2 hours after ending. The sensor must
    instead defer to the coordinator's ended state.
    """
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="ended_sensor",
        title="Short Stream",
        channel="TestChannel",
        scheduled_start=now - timedelta(minutes=5),
        live=True,
    )

    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        # First refresh: stream is live -> counts as upcoming.
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

        state = hass.states.get("sensor.youtube_live_test_group_upcoming")
        assert state.state == "1"

        coordinator = mock_config_entry.runtime_data.coordinator

        # Stream drops offline. The first not-live poll is treated as a blip;
        # the second consecutive one ends it.
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=False),
        ):
            await coordinator.async_refresh()
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert coordinator.data.statuses["ended_sensor"].ended is True

    state = hass.states.get("sensor.youtube_live_test_group_upcoming")
    assert state.state == "0"
    assert state.attributes["event_0_title"] == ""


async def test_upcoming_sensor_no_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The upcoming sensor state is 0 and attributes are empty when no streams."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.youtube_live_test_group_upcoming")
    assert state is not None
    assert state.state == "0"
    assert state.attributes["event_0_title"] == ""
