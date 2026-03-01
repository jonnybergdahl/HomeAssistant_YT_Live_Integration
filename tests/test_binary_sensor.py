"""Tests for the YouTube Live binary sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_binary_sensors_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that binary sensors are created for each stream."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 2


async def test_binary_sensor_off_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that binary sensors are off when stream is not live."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    for state in sensor_states:
        assert state.state == "off"


async def test_binary_sensor_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test binary sensor extra state attributes."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) >= 1

    # Find the sensor for stream1
    stream1_state = None
    for state in sensor_states:
        if state.attributes.get("video_id") == "stream1":
            stream1_state = state
            break

    assert stream1_state is not None
    assert stream1_state.attributes["video_id"] == "stream1"
    assert "stream_url" in stream1_state.attributes
    assert "thumbnail_url" in stream1_state.attributes
    assert "scheduled_start" in stream1_state.attributes
    assert stream1_state.attributes["channel"] == "Test Channel"


async def test_binary_sensor_live_stream(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test binary sensor when stream is live."""
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


async def test_dynamic_sensor_creation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test that new binary sensors are created when new streams appear."""
    now = datetime.now(timezone.utc)
    initial_streams = [
        make_stream(video_id="s1", title="Stream 1", scheduled_start=now + timedelta(hours=2)),
    ]

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=initial_streams,
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 1

    # Simulate calendar coordinator finding a new stream
    updated_streams = initial_streams + [
        make_stream(video_id="s2", title="Stream 2", scheduled_start=now + timedelta(hours=4)),
    ]

    runtime_data = mock_config_entry.runtime_data
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=updated_streams,
    ):
        await runtime_data.calendar_coordinator.async_refresh()
        await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    assert len(sensor_states) == 2
