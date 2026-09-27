"""Unit tests for GB-50 Home Assistant Config Flow."""

import pytest
from unittest.mock import AsyncMock, patch

from custom_components.gb50.config_flow import GB50ConfigFlow
from custom_components.gb50.const import CONF_API_KEY
from custom_components.gb50.client import GB50ProxyAuthError, GB50ProxyConnectionError


@pytest.mark.asyncio
async def test_config_flow_form_display():
    """Verify that the initial config flow step renders the setup form."""
    flow = GB50ConfigFlow()
    result = await flow.async_step_user(user_input=None)

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_config_flow_success(mock_system_info_payload):
    """Verify successful setup creates a config entry with controller details."""
    flow = GB50ConfigFlow()
    flow.hass = AsyncMock()

    user_input = {
        "host": "127.0.0.1",
        "port": 8080,
        CONF_API_KEY: "valid_secret_key",
        "use_ssl": False,
    }

    with patch("custom_components.gb50.config_flow.GB50ProxyClient") as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        mock_instance.get_system_info = AsyncMock(return_value=mock_system_info_payload)

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == "create_entry"
        assert "Saint Thomas Church" in result["title"]
        assert result["data"]["host"] == "127.0.0.1"
        assert result["data"]["port"] == 8080
        assert result["data"][CONF_API_KEY] == "valid_secret_key"
        assert flow._unique_id == "0026926268AE"


@pytest.mark.asyncio
async def test_config_flow_invalid_auth():
    """Verify that an invalid API key presents an invalid_auth error."""
    flow = GB50ConfigFlow()
    flow.hass = AsyncMock()

    user_input = {
        "host": "127.0.0.1",
        "port": 8080,
        CONF_API_KEY: "wrong_key",
        "use_ssl": False,
    }

    with patch("custom_components.gb50.config_flow.GB50ProxyClient") as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        mock_instance.get_system_info = AsyncMock(side_effect=GB50ProxyAuthError("Invalid API Key"))

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_config_flow_cannot_connect():
    """Verify that an unreachable host presents a cannot_connect error."""
    flow = GB50ConfigFlow()
    flow.hass = AsyncMock()

    user_input = {
        "host": "10.255.255.1",
        "port": 8080,
        CONF_API_KEY: "key",
        "use_ssl": False,
    }

    with patch("custom_components.gb50.config_flow.GB50ProxyClient") as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        mock_instance.get_system_info = AsyncMock(side_effect=GB50ProxyConnectionError("Host unreachable"))

        result = await flow.async_step_user(user_input=user_input)

        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"
