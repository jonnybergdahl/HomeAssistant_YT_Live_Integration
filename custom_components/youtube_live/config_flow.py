"""Config flow for the YouTube Live integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from yt_live_scraper import get_upcoming_streams

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_CHANNEL_HANDLE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHANNEL_HANDLE): str,
    }
)


class YouTubeLiveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YouTube Live."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            handle = user_input[CONF_CHANNEL_HANDLE].strip()
            if not handle.startswith("@"):
                handle = f"@{handle}"

            try:
                await self.hass.async_add_executor_job(
                    get_upcoming_streams, [handle]
                )
            except Exception:
                _LOGGER.exception("Error connecting to YouTube")
                errors["base"] = "cannot_connect"
            else:
                unique_id = handle.lower()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=handle,
                    data={CONF_CHANNEL_HANDLE: handle},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
