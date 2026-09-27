"""Config flow for Mitsubishi GB-50 integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import GB50ProxyClient, GB50ProxyConnectionError, GB50ProxyAuthError, GB50ProxyError
from .const import DOMAIN, DEFAULT_PORT, CONF_API_KEY, CONF_USE_SSL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="127.0.0.1"): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
    }
)


class GB50ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mitsubishi GB-50."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle initial step where user provides connection settings."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            api_key = user_input[CONF_API_KEY].strip()
            use_ssl = bool(user_input.get(CONF_USE_SSL, False))

            session = async_get_clientsession(self.hass)
            client = GB50ProxyClient(
                host=host,
                port=port,
                api_key=api_key,
                use_ssl=use_ssl,
                session=session,
            )

            try:
                system_info = await client.get_system_info()
            except GB50ProxyAuthError:
                errors["base"] = "invalid_auth"
            except GB50ProxyConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as ex:
                _LOGGER.exception("Unexpected error validating GB-50 proxy connection: %s", ex)
                errors["base"] = "unknown"
            else:
                mac = system_info.get("mac_address")
                serial = system_info.get("serial_number")
                unique_id = mac or serial or f"gb50_{host}_{port}"

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                system_name = system_info.get("system_name") or "Mitsubishi GB-50"
                model = system_info.get("model") or "GB-50"

                return self.async_create_entry(
                    title=f"{system_name} ({model})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_API_KEY: api_key,
                        CONF_USE_SSL: use_ssl,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
