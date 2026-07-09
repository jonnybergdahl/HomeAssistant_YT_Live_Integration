"""Tests for the YouTube Live coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from yt_live_scraper import StreamLiveStatus

from custom_components.youtube_live.const import DEFAULT_STREAM_DURATION_HOURS
from custom_components.youtube_live.coordinator import (
    StreamStatus,
    YouTubeLiveCoordinator,
    YouTubeLiveCoordinatorData,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_stream


async def test_coordinator_fetches_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that the coordinator fetches streams for every channel."""
    mock_config_entry.add_to_hass(hass)
    coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    assert coordinator.data is not None
    assert len(coordinator.data.streams) == 2
    assert coordinator.data.streams[0].video_id == "stream1"
    assert coordinator.data.streams[1].video_id == "stream2"
    mock_get_upcoming_streams.assert_called_once_with(["@TestChannel"])

    # Group title is user-picked and must not be changed
    assert mock_config_entry.title == "Test Group"


async def test_coordinator_populates_channel_thumbnail(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Channel thumbnail/avatar is fetched when no streams are present."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[],
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

    # get_channel_info is mocked in conftest to return thumbnail_url
    assert (
        coordinator.channel_thumbnail_urls.get("@testchannel")
        == "https://example.com/thumb.jpg"
    )


async def test_coordinator_handles_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the coordinator handles errors gracefully."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        side_effect=Exception("Network error"),
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

        assert coordinator.last_update_success is False


async def test_coordinator_passes_all_handles(
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
        coordinator = YouTubeLiveCoordinator(hass, entry)
        await coordinator.async_refresh()
        mock_fn.assert_called_once_with(["@A", "@B", "@C"])


async def test_stream_status_no_active_streams(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that the coordinator does not poll streams outside the active window."""
    mock_config_entry.add_to_hass(hass)
    coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
    await coordinator.async_refresh()

    mock_is_stream_live.assert_not_called()
    assert coordinator.data is not None
    assert len(coordinator.data.statuses) == 0


async def test_stream_status_active_window(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test that the coordinator polls streams in the active window."""
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
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

    mock_is_stream_live.assert_called_once_with("active1")
    assert coordinator.data.statuses["active1"].is_live is False


async def test_stream_status_detects_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the coordinator detects when a stream goes live."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="live1",
        title="Going Live",
        scheduled_start=now + timedelta(minutes=5),
    )
    with (
        patch(
            "custom_components.youtube_live.coordinator.get_upcoming_streams",
            return_value=[stream],
        ),
        patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

        status = coordinator.data.statuses["live1"]
        assert status.is_live is True
        assert status.was_live is True
        assert status.ended is False


async def test_stream_status_detects_ended(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the coordinator detects when a stream ends."""
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
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()

        assert coordinator.data.statuses["ended1"].was_live is True

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=False),
        ):
            # A single not-live poll is treated as a transient blip.
            await coordinator.async_refresh()
            assert coordinator.data.statuses["ended1"].ended is False
            # A second consecutive not-live poll ends the stream.
            await coordinator.async_refresh()

    status = coordinator.data.statuses["ended1"]
    assert status.is_live is False
    assert status.was_live is True
    assert status.ended is True
    assert status.ended_at is not None


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

    with (
        patch(
            "custom_components.youtube_live.coordinator.get_upcoming_streams",
            return_value=[stream],
        ),
        patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True, actual_start=actual_start),
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
        await coordinator.async_refresh()

    assert stream.scheduled_start == actual_start
    assert coordinator.data.statuses["live_corrected"].is_live is True


async def test_stream_status_single_not_live_is_transient(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A single not-live poll must not end a live stream, and a later live
    poll clears the transient state (guards against scraper/network blips)."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="blip",
        title="Blip Stream",
        scheduled_start=now + timedelta(minutes=5),
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()

        # A single not-live reading is treated as a transient blip.
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=False),
        ):
            await coordinator.async_refresh()
        status = coordinator.data.statuses["blip"]
        assert status.ended is False
        assert status.not_live_streak == 1

        # A subsequent live reading clears the transient not-live streak.
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()
        status = coordinator.data.statuses["blip"]
        assert status.is_live is True
        assert status.ended is False
        assert status.not_live_streak == 0


async def test_stream_status_recovers_on_live_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A stream that got marked ended (e.g. during an outage) recovers when a
    later poll reads it live again, while the channel page still lists it as
    live so polling continues."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="stuck",
        title="Stuck Stream",
        scheduled_start=now + timedelta(minutes=5),
        live=True,
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()

        # Two consecutive not-live polls mark it ended.
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=False),
        ):
            await coordinator.async_refresh()
            await coordinator.async_refresh()
            assert coordinator.data.statuses["stuck"].ended is True

        # A real live reading recovers it (the channel page still lists it as
        # live, so it is still being polled).
        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()
        status = coordinator.data.statuses["stuck"]
        assert status.ended is False
        assert status.is_live is True
        assert status.ended_at is None


async def test_stream_status_stays_ended_while_channel_stale_live(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """After a genuine end, further not-live polls keep the stream ended even
    while the (stale) channel page still lists it as live -- no flip-flop."""
    now = datetime.now(timezone.utc)
    stream = make_stream(
        video_id="done",
        title="Done Stream",
        scheduled_start=now + timedelta(minutes=5),
        live=True,
    )
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=[stream],
    ):
        mock_config_entry.add_to_hass(hass)
        coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=True),
        ):
            await coordinator.async_refresh()

        with patch(
            "custom_components.youtube_live.coordinator.is_stream_live",
            return_value=StreamLiveStatus(is_live=False),
        ):
            await coordinator.async_refresh()
            await coordinator.async_refresh()
            ended_at = coordinator.data.statuses["done"].ended_at
            assert ended_at is not None

            # Further not-live polls must not un-end it or move the end time.
            await coordinator.async_refresh()
            await coordinator.async_refresh()

        status = coordinator.data.statuses["done"]
        assert status.ended is True
        assert status.ended_at == ended_at


async def test_stream_end_time_never_before_start(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A stale ``ended_at`` earlier than the (re-stamped) start must not yield
    an end before the start, which HA rejects as an invalid CalendarEvent."""
    now = datetime.now(timezone.utc)
    stream = make_stream(video_id="stale", scheduled_start=now)
    mock_config_entry.add_to_hass(hass)
    coordinator = YouTubeLiveCoordinator(hass, mock_config_entry)
    coordinator.data = YouTubeLiveCoordinatorData(
        streams=[stream],
        statuses={
            "stale": StreamStatus(
                was_live=True,
                ended=True,
                ended_at=now - timedelta(hours=3),
            )
        },
        stream_metadata={"stale": stream},
    )

    end = coordinator.stream_end_time(stream)
    assert end > stream.scheduled_start
    assert end == stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)
