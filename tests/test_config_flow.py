"""Tests for the YouTube Live config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.youtube_live.const import CONF_CHANNEL_HANDLE, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_full_user_flow(
    hass: HomeAssistant,
    mock_config_flow_channel_exists,
) -> None:
    """Test a successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_HANDLE: "@TestChannel"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "@TestChannel"
    assert result["data"] == {CONF_CHANNEL_HANDLE: "@TestChannel"}
    mock_config_flow_channel_exists.assert_called_once_with("@TestChannel")


async def test_flow_adds_at_prefix(
    hass: HomeAssistant,
    mock_config_flow_channel_exists,
) -> None:
    """Test that the flow adds @ prefix if missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_HANDLE: "TestChannel"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CHANNEL_HANDLE] == "@TestChannel"
    mock_config_flow_channel_exists.assert_called_once_with("@TestChannel")


async def test_flow_channel_not_found(hass: HomeAssistant) -> None:
    """Test config flow when channel handle is not found on YouTube."""
    with patch(
        "custom_components.youtube_live.config_flow.UpcomingStream.exists",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHANNEL_HANDLE: "@bad_handle"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "channel_not_found"}


async def test_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Test config flow when YouTube is unreachable."""
    with patch(
        "custom_components.youtube_live.config_flow.UpcomingStream.exists",
        side_effect=Exception("Connection error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHANNEL_HANDLE: "@BadChannel"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_already_configured(
    hass: HomeAssistant,
    mock_config_flow_channel_exists,
) -> None:
    """Test that we abort if channel is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="@testchannel",
        data={CONF_CHANNEL_HANDLE: "@TestChannel"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_HANDLE: "@TestChannel"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
