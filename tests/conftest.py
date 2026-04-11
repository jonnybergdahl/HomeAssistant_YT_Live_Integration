"""Shared fixtures for YouTube Live tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from yt_live_scraper import StreamLiveStatus, UpcomingStream

from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLE, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="@testchannel",
        data={CONF_CHANNEL_HANDLE: "@TestChannel"},
        title="@TestChannel",
    )


def make_stream(
    video_id: str = "abc123",
    title: str = "Test Stream",
    channel: str = "Test Channel",
    scheduled_start: datetime | None = None,
    live: bool = False,
) -> UpcomingStream:
    """Create a test UpcomingStream."""
    if scheduled_start is None:
        scheduled_start = datetime.now(timezone.utc) + timedelta(hours=1)
    return UpcomingStream(
        channel=channel,
        channel_id="UC_mock_channel_id",
        channel_thumbnail_url="https://example.com/thumb.jpg",
        video_id=video_id,
        title=title,
        scheduled_start=scheduled_start,
        url=f"https://www.youtube.com/watch?v={video_id}",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        live=live,
    )


@pytest.fixture
def mock_streams():
    """Return a list of mock streams."""
    now = datetime.now(timezone.utc)
    return [
        make_stream(
            video_id="stream1",
            title="Morning Stream",
            scheduled_start=now + timedelta(hours=2),
        ),
        make_stream(
            video_id="stream2",
            title="Evening Stream",
            scheduled_start=now + timedelta(hours=6),
        ),
    ]


@pytest.fixture
def mock_get_upcoming_streams(mock_streams):
    """Mock get_upcoming_streams."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        return_value=mock_streams,
    ) as mock_fn:
        yield mock_fn


@pytest.fixture
def mock_is_stream_live():
    """Mock is_stream_live."""
    with patch(
        "custom_components.youtube_live.coordinator.is_stream_live",
        return_value=StreamLiveStatus(is_live=False),
    ) as mock_fn:
        yield mock_fn


@pytest.fixture
def mock_get_channel():
    """Mock get_channel."""
    with patch(
        "custom_components.youtube_live.config_flow.get_channel",
        return_value="Test Channel",
    ) as mock_fn:
        yield mock_fn
