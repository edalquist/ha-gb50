"""Unit tests for GB50ProxyClient REST and WebSocket communication."""

import asyncio
import json
from typing import Any, Optional, Dict, List
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from custom_components.gb50.client import (
    GB50ProxyClient,
    GB50ProxyAuthError,
    GB50ProxyConnectionError,
    GB50ProxyError,
)


class MockResponse:
    """Mock aiohttp response context manager."""

    def __init__(self, status: int = 200, json_data: Any = None, text_data: str = ""):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


@pytest.mark.asyncio
async def test_client_rest_and_auth(mock_system_info_payload, mock_ac_group_payload):
    """Test REST endpoints, headers, and authentication validation."""
    valid_api_key = "test_church_secret_key"
    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.closed = False

    def mock_request(method, url, headers=None, json=None, params=None, timeout=None):
        assert headers.get("X-API-Key") == valid_api_key
        assert headers.get("Content-Type") == "application/json"

        if url.endswith("/api/v1/system"):
            return MockResponse(status=200, json_data=mock_system_info_payload)
        elif url.endswith("/api/v1/groups"):
            return MockResponse(status=200, json_data=[mock_ac_group_payload])
        elif "/groups/1" in url and method == "PATCH":
            assert json.get("drive") == "ON"
            assert json.get("set_temp_c") == 22.0
            return MockResponse(status=200, json_data={"success": True})
        elif "/groups/1/reset-filter" in url and method == "POST":
            return MockResponse(status=200, json_data={"success": True})
        elif "/presets/all_off" in url and method == "POST":
            return MockResponse(status=200, json_data=[mock_ac_group_payload])
        elif url.endswith("/api/v1/system/alarms"):
            return MockResponse(status=200, json_data=[])
        return MockResponse(status=404, text_data="Not Found")

    mock_session.request = mock_request

    client = GB50ProxyClient(
        host="127.0.0.1",
        port=8080,
        api_key=valid_api_key,
        session=mock_session,
    )

    # 1. Test get_system_info
    sys_info = await client.get_system_info()
    assert sys_info["model"] == "GB-50ADA-A"
    assert sys_info["mac_address"] == "0026926268AE"

    # 2. Test get_groups
    groups = await client.get_groups()
    assert len(groups) == 1
    assert groups[0]["name"] == "FC1-1"

    # 3. Test set_group
    set_res = await client.set_group(1, drive="ON", set_temp_c=22.0)
    assert set_res["success"] is True

    # 4. Test reset_filter
    reset_res = await client.reset_filter(1)
    assert reset_res["success"] is True

    # 5. Test apply_preset
    preset_res = await client.apply_preset("all_off")
    assert len(preset_res) == 1

    # 6. Test alarms
    alarms = await client.get_alarms()
    assert alarms == []

    await client.close()


@pytest.mark.asyncio
async def test_client_auth_error():
    """Verify that a 401 response raises GB50ProxyAuthError."""
    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.closed = False

    def mock_unauthorized(*args, **kwargs):
        return MockResponse(status=401, text_data="Unauthorized")

    mock_session.request = mock_unauthorized

    client = GB50ProxyClient(
        host="127.0.0.1",
        port=8080,
        api_key="bad_key",
        session=mock_session,
    )

    with pytest.raises(GB50ProxyAuthError):
        await client.get_system_info()

    await client.close()


@pytest.mark.asyncio
async def test_client_connection_error():
    """Verify that network disconnect raises GB50ProxyConnectionError."""
    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.closed = False

    class FailingContext:
        async def __aenter__(self):
            raise asyncio.TimeoutError("Connection timed out")

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_conn_fail(*args, **kwargs):
        return FailingContext()

    mock_session.request = mock_conn_fail

    client = GB50ProxyClient(
        host="10.255.255.1",
        port=8080,
        api_key="key",
        session=mock_session,
    )

    with pytest.raises(GB50ProxyConnectionError):
        await client.get_system_info()

    await client.close()


@pytest.mark.asyncio
async def test_client_websocket_stream(mock_ac_group_payload):
    """Test WebSocket listener parsing and callback execution."""
    valid_api_key = "test_church_secret_key"
    messages_received = []

    # Mock WebSocket Message objects
    class MockWSMessage:
        def __init__(self, data: str):
            self.type = aiohttp.WSMsgType.TEXT
            self.data = data

    class MockWebSocketResponse:
        def __init__(self):
            self.closed = False
            self.messages = [
                MockWSMessage(json.dumps({
                    "event": "initial_state",
                    "groups": [mock_ac_group_payload],
                })),
                MockWSMessage(json.dumps({
                    "event": "group_updates",
                    "groups": [dict(mock_ac_group_payload, drive="ON")],
                })),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.closed = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.messages:
                return self.messages.pop(0)
            raise StopAsyncIteration

        async def close(self):
            self.closed = True

    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.closed = False

    def mock_ws_connect(url, headers=None, heartbeat=None):
        assert f"api_key={valid_api_key}" in url
        return MockWebSocketResponse()

    mock_session.ws_connect = mock_ws_connect

    client = GB50ProxyClient(
        host="127.0.0.1",
        port=8080,
        api_key=valid_api_key,
        session=mock_session,
    )

    def on_message(data):
        messages_received.append(data)
        if len(messages_received) >= 2:
            client.stop_listener()

    await client.listen_events(on_message=on_message)

    assert len(messages_received) == 2
    assert messages_received[0]["event"] == "initial_state"
    assert messages_received[1]["event"] == "group_updates"
    assert messages_received[1]["groups"][0]["drive"] == "ON"

    await client.close()
