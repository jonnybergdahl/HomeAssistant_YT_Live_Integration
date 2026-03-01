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
    assert "live1" in sensor_states[0].attributes.get("live_streams", [])


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
    assert state.attributes["channel"] == "@TestChannel"
    assert state.attributes["live_streams"] == []
