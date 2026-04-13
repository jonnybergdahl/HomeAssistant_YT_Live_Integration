"""Config flow for the YouTube Live integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from yt_live_scraper.scraper import get_channel_info

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import CONF_CHANNEL_HANDLES, CONF_GROUP_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


_CHANNEL_LIST_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[],
        custom_value=True,
        multiple=True,
    )
)


def _normalize_handle(handle: str) -> str:
    """Ensure handle starts with a single ``@`` and strip whitespace."""
    h = handle.strip()
    if not h:
        return h
    if not h.startswith("@"):
        h = f"@{h}"
    return h


async def _validate_handles(
    hass, handles: list[str]
) -> tuple[list[str], dict[str, str]]:
    """Normalize and validate a list of channel handles.

    :returns: Tuple of ``(normalized_handles, errors)``. On success, the
              error dict is empty.
    """
    errors: dict[str, str] = {}
    normalized: list[str] = []
    seen: set[str] = set()

    if not handles:
        errors["base"] = "no_channels"
        return normalized, errors

    for raw in handles:
        handle = _normalize_handle(raw)
        if not handle:
            continue
        if handle.lower() in seen:
            continue
        seen.add(handle.lower())
        normalized.append(handle)

    if not normalized:
        errors["base"] = "no_channels"
        return normalized, errors

    for handle in normalized:
        try:
            info = await hass.async_add_executor_job(get_channel_info, handle)
        except Exception:
            _LOGGER.exception("Error connecting to YouTube for handle: %s", handle)
            errors["base"] = "cannot_connect"
            return normalized, errors
        if info is None:
            _LOGGER.warning("Channel not found on YouTube: %s", handle)
            errors["base"] = "channel_not_found"
            return normalized, errors

    return normalized, errors


class YouTubeLiveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YouTube Live."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: create a channel group."""
        errors: dict[str, str] = {}

        if user_input is not None:
            group_name = user_input[CONF_GROUP_NAME].strip()
            handles = user_input.get(CONF_CHANNEL_HANDLES, []) or []

            if not group_name:
                errors["base"] = "no_group_name"
            else:
                normalized, errors = await _validate_handles(self.hass, handles)
                if not errors:
                    unique_id = slugify(group_name)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=group_name,
                        data={CONF_CHANNEL_HANDLES: normalized},
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_GROUP_NAME): str,
                vol.Required(CONF_CHANNEL_HANDLES, default=[]): _CHANNEL_LIST_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return YouTubeLiveOptionsFlow(config_entry)


class YouTubeLiveOptionsFlow(OptionsFlow):
    """Options flow: edit the channels in a group."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        current_handles = list(self._entry.data.get(CONF_CHANNEL_HANDLES, []))

        if user_input is not None:
            handles = user_input.get(CONF_CHANNEL_HANDLES, []) or []
            normalized, errors = await _validate_handles(self.hass, handles)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, CONF_CHANNEL_HANDLES: normalized},
                )
                self.hass.config_entries.async_schedule_reload(
                    self._entry.entry_id
                )
                return self.async_create_entry(title="", data={})
            current_handles = handles

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CHANNEL_HANDLES, default=current_handles
                ): _CHANNEL_LIST_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
