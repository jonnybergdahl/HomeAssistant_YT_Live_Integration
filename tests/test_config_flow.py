"""Tests for the YouTube Live config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.youtube_live.const import (
    CONF_CHANNEL_HANDLES,
    CONF_GROUP_NAME,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_full_user_flow(hass: HomeAssistant) -> None:
    """Creating a group with multiple channels."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_GROUP_NAME: "Gaming",
            CONF_CHANNEL_HANDLES: ["@ChannelA", "ChannelB"],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Gaming"
    # Second handle was normalized to add the @ prefix.
    assert result["data"] == {
        CONF_CHANNEL_HANDLES: ["@ChannelA", "@ChannelB"],
    }


async def test_flow_requires_at_least_one_channel(hass: HomeAssistant) -> None:
    """Submitting an empty channel list shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_GROUP_NAME: "Gaming", CONF_CHANNEL_HANDLES: []},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_channels"}


async def test_flow_channel_not_found(hass: HomeAssistant) -> None:
    """Unknown channels are reported as errors."""
    with patch(
        "custom_components.youtube_live.config_flow.get_channel_info",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_GROUP_NAME: "Gaming",
                CONF_CHANNEL_HANDLES: ["@bad_handle"],
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "channel_not_found"}


async def test_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Connection errors surface as cannot_connect."""
    with patch(
        "custom_components.youtube_live.config_flow.get_channel_info",
        side_effect=Exception("Connection error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_GROUP_NAME: "Gaming",
                CONF_CHANNEL_HANDLES: ["@BadChannel"],
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_already_configured(hass: HomeAssistant) -> None:
    """A group name that's already used aborts the flow."""
    entry = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@TestChannel"]},
        title="Gaming",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_GROUP_NAME: "Gaming",
            CONF_CHANNEL_HANDLES: ["@Something"],
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_edits_channels(
    hass: HomeAssistant,
    mock_get_upcoming_streams,
    mock_is_stream_live,
) -> None:
    """Options flow updates the channel list and reloads the entry."""
    entry = MockConfigEntry(version=2, 
        domain=DOMAIN,
        unique_id="gaming",
        data={CONF_CHANNEL_HANDLES: ["@ChannelA"]},
        title="Gaming",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_HANDLES: ["@ChannelA", "@ChannelC"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_CHANNEL_HANDLES] == ["@ChannelA", "@ChannelC"]
