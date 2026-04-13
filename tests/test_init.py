"""Tests for the YouTube Live integration setup."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLES, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test successful setup of a group config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None


async def test_setup_entry_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_is_stream_live,
) -> None:
    """Test setup failure raises ConfigEntryNotReady."""
    with patch(
        "custom_components.youtube_live.coordinator.get_upcoming_streams",
        side_effect=Exception("Connection error"),
    ):
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test successful unload of a group config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_two_groups_are_independent(
    hass: HomeAssistant,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Two group entries should produce two independent devices and calendars."""
    entry_a = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@ChannelA"]},
        title="Gaming",
    )
    entry_b = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="tech",
        data={CONF_CHANNEL_HANDLES: ["@ChannelB"]},
        title="Tech",
    )

    entry_a.add_to_hass(hass)
    await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    entry_b.add_to_hass(hass)
    await hass.config_entries.async_setup(entry_b.entry_id)
    await hass.async_block_till_done()

    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    # One calendar per group
    assert len(calendar_states) == 2
