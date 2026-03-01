"""Tests for the YouTube Live integration setup."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLE, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test successful setup of config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN].calendar_owner_entry_id == mock_config_entry.entry_id
    assert mock_config_entry.entry_id in hass.data[DOMAIN].coordinators


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
    """Test successful unload of config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data[DOMAIN].coordinators


async def test_calendar_ownership_transfer(
    hass: HomeAssistant,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Test that calendar ownership transfers when the owning entry is unloaded."""
    entry_a = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_a",
        data={CONF_CHANNEL_HANDLE: "@ChannelA"},
        title="@ChannelA",
    )
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@channel_b",
        data={CONF_CHANNEL_HANDLE: "@ChannelB"},
        title="@ChannelB",
    )

    entry_a.add_to_hass(hass)

    await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    # Add entry_b AFTER entry_a is set up to avoid HA auto-setting up all entries
    entry_b.add_to_hass(hass)

    await hass.config_entries.async_setup(entry_b.entry_id)
    await hass.async_block_till_done()

    shared = hass.data[DOMAIN]
    assert shared.calendar_owner_entry_id == entry_a.entry_id

    # Unload entry A — ownership should transfer to entry B
    await hass.config_entries.async_unload(entry_a.entry_id)
    await hass.async_block_till_done()

    assert shared.calendar_owner_entry_id == entry_b.entry_id
    assert shared.calendar_entity is not None

    # Calendar should still exist
    calendar_states = [
        s for s in hass.states.async_all() if s.domain == "calendar"
    ]
    assert len(calendar_states) == 1
