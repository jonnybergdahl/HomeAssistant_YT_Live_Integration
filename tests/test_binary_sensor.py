"""Tests for the YouTube Live binary sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from yt_live_scraper import StreamLiveStatus

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLES, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_sensors_created_per_channel_plus_aggregate(
    hass: HomeAssistant,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Each handle gets one channel sensor; the group gets one aggregate sensor."""
    entry = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@ChannelA", "@ChannelB"]},
        title="Gaming",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sensor_states = [
        s for s in hass.states.async_all() if s.domain == "binary_sensor"
    ]
    # 2 per-channel + 1 aggregate
    assert len(sensor_states) == 3

    entity_ids = {s.entity_id for s in sensor_states}
    assert "binary_sensor.youtube_live_channela" in entity_ids
    assert "binary_sensor.youtube_live_channelb" in entity_ids
    assert "binary_sensor.youtube_live_gaming_any_live" in entity_ids


async def test_group_sensor_off_when_nothing_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Group aggregate sensor is off when no stream is live."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.youtube_live_test_group_any_live")
    assert state is not None
    assert state.state == "off"


async def test_channel_sensor_on_when_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The per-channel sensor and the group aggregate both go on when live."""
    now = datetime.now(timezone.utc)
    live_stream = make_stream(
        video_id="live1",
        title="Live Now",
        channel="TestChannel",
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
            return_value=StreamLiveStatus(is_live=True),
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    channel_state = hass.states.get("binary_sensor.youtube_live_testchannel")
    aggregate_state = hass.states.get(
        "binary_sensor.youtube_live_test_group_any_live"
    )
    assert channel_state is not None
    assert aggregate_state is not None
    assert channel_state.state == "on"
    assert aggregate_state.state == "on"

    # Channel sensor friendly name and attributes
    attrs = channel_state.attributes
    assert attrs["friendly_name"] == "Live Now"
    assert attrs["stream_id"] == "live1"
    assert attrs["channel_handle"] == "@TestChannel"
    assert attrs["group"] == "Test Group"


async def test_channel_sensor_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Channel sensor shows next upcoming stream and its thumbnail."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.youtube_live_testchannel")
    assert state is not None
    attrs = state.attributes
    assert attrs["friendly_name"] == "TestChannel"
    assert state.attributes.get("entity_picture") == "https://example.com/thumb.jpg"
    assert attrs["channel_handle"] == "@TestChannel"
    assert attrs["stream_id"] is None
    assert attrs["group"] == "Test Group"


async def test_channel_sensor_entity_picture_falls_back_to_channel_avatar(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """When no streams, entity_picture is the channel's avatar image."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.youtube_live_testchannel")
    assert state is not None
    assert state.attributes.get("entity_picture") == "https://example.com/thumb.jpg"
    assert state.attributes["stream_id"] is None


async def test_group_sensor_attributes_list_live_streams(
    hass: HomeAssistant,
) -> None:
    """Group aggregate sensor lists the live stream IDs and count."""
    now = datetime.now(timezone.utc)
    live_stream = make_stream(
        video_id="live1",
        title="Live A",
        channel="ChannelA",
        scheduled_start=now - timedelta(minutes=2),
        live=True,
    )
    entry = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@ChannelA", "@ChannelB"]},
        title="Gaming",
    )
    with (
        patch(
            "custom_components.youtube_live.coordinator.get_upcoming_streams",
            return_value=[live_stream],
        ),
        patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ),
    ):
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.youtube_live_gaming_any_live")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["live_count"] == 1
    assert state.attributes["live_stream_ids"] == ["live1"]
    assert state.attributes["channel_handles"] == ["@ChannelA", "@ChannelB"]
