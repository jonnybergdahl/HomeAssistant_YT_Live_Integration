"""Tests for the YouTube Live coordinators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from yt_live_scraper import StreamLiveStatus

from custom_components.youtube_live.coordinator import (
    CalendarCoordinator,
    StreamStatusCoordinator,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_calendar_coordinator_fetches_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
) -> None:
    """Test that the calendar coordinator fetches streams for every channel."""
    mock_config_entry.add_to_hass(hass)
    coordinator = CalendarCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert coordinator.data is not None
    assert len(coordinator.data) == 2
    assert coordinator.data[0].video_id == "stream1"
    assert coordinator.data[1].video_id == "stream2"
    mock_get_upcoming_streams.assert_called_once_with(["@TestChannel"])

    # Group title is user-picked and must not be changed
    assert mock_config_entry.title == "Test Group"


async def test_calendar_coordinator_populates_channel_thumbnail(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Channel thumbnail/avatar is fetched when no streams are present."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = CalendarCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

    # get_channel_info is mocked in conftest to return thumbnail_url
    assert (
        coordinator.channel_thumbnail_urls.get("@testchannel")
        == "https://example.com/thumb.jpg"
    )


async def test_calendar_coordinator_handles_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the calendar coordinator handles errors gracefully."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        side_effect=Exception("Network error"),
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = CalendarCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

        assert coordinator.last_update_success is False


async def test_calendar_coordinator_passes_all_handles(
    hass: HomeAssistant,
) -> None:
    """A group with multiple handles passes them all to the scraper."""
    entry = MockConfigEntry(version=2, 
        domain="youtube_live",
        unique_id="gaming",
        data={"channel_handles": ["@A", "@B", "@C"]},
        title="Gaming",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ) as mock_fn:
        coordinator = CalendarCoordinator(hass, entry)
        await coordinator.async_refresh()
        mock_fn.assert_called_once_with(["@A", "@B", "@C"])


async def test_stream_status_no_active_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that stream status coordinator does nothing when no streams are in active window."""
    mock_config_entry.add_to_hass(hass)
    calendar_coordinator = CalendarCoordinator(hass, mock_config_entry)
    await calendar_coordinator.async_refresh()

    stream_coordinator = StreamStatusCoordinator(
        hass, mock_config_entry, calendar_coordinator
    )
    await stream_coordinator.async_refresh()

    mock_is_stream_live.assert_not_called()
    assert stream_coordinator.data is not None
    assert len(stream_coordinator.data.statuses) == 0


async def test_stream_status_active_window(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test that stream status coordinator polls streams in active window."""
    now = datetime.now(timezone.utc)
    active_stream = make_stream(
        video_id="active1",
        title="Starting Soon",
        scheduled_start=now + timedelta(minutes=10),
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[active_stream],
    ):
        mock_config_entry.add_to_hass(hass)
        calendar_coordinator = CalendarCoordinator(hass, mock_config_entry)
        await calendar_coordinator.async_refresh()

    stream_coordinator = StreamStatusCoordinator(
        hass, mock_config_entry, calendar_coordinator
    )
    await stream_coordinator.async_refresh()

    mock_is_stream_live.assert_called_once_with("active1")
    assert stream_coordinator.data.statuses["active1"].is_live is False


async def test_stream_status_detects_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that stream status coordinator detects when a stream goes live."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="live1",
        title="Going Live",
        scheduled_start=now + timedelta(minutes=5),
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        calendar_coordinator = CalendarCoordinator(hass, mock_config_entry)
        await calendar_coordinator.async_refresh()

    with patch(
        "custom_components.youtube_live.coordinator.is_stream_live",
        return_value=StreamLiveStatus(is_live=True),
    ):
        stream_coordinator = StreamStatusCoordinator(
            hass, mock_config_entry, calendar_coordinator
        )
        await stream_coordinator.async_refresh()

        status = stream_coordinator.data.statuses["live1"]
        assert status.is_live is True
        assert status.was_live is True
        assert status.ended is False


async def test_stream_status_detects_ended(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that stream status coordinator detects when a stream ends."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="ended1",
        title="Ending Stream",
        scheduled_start=now + timedelta(minutes=5),
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        calendar_coordinator = CalendarCoordinator(hass, mock_config_entry)
        await calendar_coordinator.async_refresh()

    with patch(
        "custom_components.youtube_live.coordinator.is_stream_live",
        return_value=StreamLiveStatus(is_live=True),
    ):
        stream_coordinator = StreamStatusCoordinator(
            hass, mock_config_entry, calendar_coordinator
        )
        await stream_coordinator.async_refresh()

    assert stream_coordinator.data.statuses["ended1"].was_live is True

    with patch(
        "custom_components.youtube_live.coordinator.is_stream_live",
        return_value=StreamLiveStatus(is_live=False),
    ):
        await stream_coordinator.async_refresh()

    status = stream_coordinator.data.statuses["ended1"]
    assert status.is_live is False
    assert status.was_live is True
    assert status.ended is True


async def test_stream_status_corrects_start_time(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that scheduled_start is corrected from the player response."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="live_corrected",
        title="Already Live",
        scheduled_start=now,
        live=True,
    )
    actual_start = now - timedelta(hours=2)

    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        calendar_coordinator = CalendarCoordinator(hass, mock_config_entry)
        await calendar_coordinator.async_refresh()

    with patch(
        "custom_components.youtube_live.coordinator.is_stream_live",
        return_value=StreamLiveStatus(is_live=True, actual_start=actual_start),
    ):
        stream_coordinator = StreamStatusCoordinator(
            hass, mock_config_entry, calendar_coordinator
        )
        await stream_coordinator.async_refresh()

    assert stream.scheduled_start == actual_start
    assert stream_coordinator.data.statuses["live_corrected"].is_live is True
