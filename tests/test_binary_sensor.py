"""Tests for the YouTube Live binary sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_channel_sensor_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that one binary sensor is created per channel."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1


async def test_channel_sensor_off_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that the channel sensor is off when no streams are live."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1
    assert sensor_states[0].state == "off"


async def test_channel_sensor_on_when_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the channel sensor is on when a stream is live."""
    now = datetime.now(timezone.utc)
    live_stream = make_stream(
        video_id="live1",
        title="Live Now",
        scheduled_start=now - timedelta(minutes=5),
        live=True,
    )
    with (
        patch(
            "custom_components.youtube_live.coordinator.get_upcoming_streams",
            return_value=[live_stream],
        ),
        patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=True,
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1
    assert sensor_states[0].state == "on"

    # Friendly name should be the stream title
    assert sensor_states[0].attributes.get("friendly_name") == "Live Now"

    # Attributes should reflect the live stream
    attrs = sensor_states[0].attributes
    assert attrs["url"] == f"https://www.youtube.com/watch?v=live1"
    assert attrs["channel_handle"] == "@TestChannel"
    assert attrs["channel_name"] == "Test Channel"


async def test_channel_sensor_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test channel sensor extra state attributes."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1
    state = sensor_states[0]

    # Friendly name should be the next stream title
    assert state.attributes.get("friendly_name") == "Morning Stream"

    # entity_picture should be the next stream's thumbnail
    assert state.attributes.get("entity_picture") is not None
    assert "stream1" in state.attributes["entity_picture"]

    # Channel info
    assert state.attributes["channel_handle"] == "@TestChannel"
    assert state.attributes["channel_name"] == "Test Channel"

    # Stream info
    assert state.attributes["url"] == "https://www.youtube.com/watch?v=stream1"
    assert state.attributes["stream_start"] is not None


async def test_channel_sensor_no_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test channel sensor fallback when no streams exist."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1
    state = sensor_states[0]

    # Friendly name falls back to channel name + Live
    assert state.attributes.get("friendly_name") == "@TestChannel Live"

    # No entity_picture when no streams
    assert state.attributes.get("entity_picture") is None

    # Stream attributes are None
    assert state.attributes["url"] is None
    assert state.attributes["stream_start"] is None

    # Channel info still present
    assert state.attributes["channel_handle"] == "@TestChannel"
    assert state.attributes["channel_name"] == "@TestChannel"
