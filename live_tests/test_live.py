"""Live integration tests that make real calls to YouTube.

Run with:  pytest live_tests/ -v
These tests are NOT part of the normal test suite (they live outside tests/).
They make real network requests to YouTube.
"""

from __future__ import annotations

import pytest
from yt_live_scraper.scraper import get_channel_info


def test_jonnybergdahl_subscriber_count():
    """@jonnybergdahl should have more than 50 000 subscribers."""
    info = get_channel_info("@jonnybergdahl")
    assert info is not None, "get_channel_info returned None for @jonnybergdahl"
    assert info.subscriber_count is not None, (
        "Subscriber count is hidden for @jonnybergdahl"
    )
    assert info.subscriber_count > 50_000, (
        f"Expected > 50 000 subscribers, got {info.subscriber_count}"
    )


def test_jonny_beeee_subscriber_count():
    """@jonny_beeee should have more than 70 subscribers."""
    info = get_channel_info("@jonny_beeee")
    assert info is not None, "get_channel_info returned None for @jonny_beeee"
    assert info.subscriber_count is not None, (
        "Subscriber count is hidden for @jonny_beeee"
    )
    assert info.subscriber_count > 70, (
        f"Expected > 70 subscribers, got {info.subscriber_count}"
    )
