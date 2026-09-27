"""Asynchronous REST and WebSocket client for gb50-web-proxy."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional
import aiohttp

_LOGGER = logging.getLogger(__name__)


class GB50ProxyError(Exception):
    """Base exception for GB-50 proxy errors."""


class GB50ProxyConnectionError(GB50ProxyError):
    """Raised when connection to proxy fails."""


class GB50ProxyAuthError(GB50ProxyError):
    """Raised when authentication fails."""


class GB50ProxyClient:
    """Asynchronous client for communicating with gb50-web-proxy."""

    def __init__(
        self,
        host: str,
        port: int = 8080,
        api_key: Optional[str] = None,
        use_ssl: bool = False,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.use_ssl = use_ssl
        self._session = session
        self._own_session = False
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_running = False

    @property
    def http_scheme(self) -> str:
        return "https" if self.use_ssl else "http"

    @property
    def ws_scheme(self) -> str:
        return "wss" if self.use_ssl else "ws"

    @property
    def base_url(self) -> str:
        return f"{self.http_scheme}://{self.host}:{self.port}/api/v1"

    @property
    def ws_url(self) -> str:
        url = f"{self.ws_scheme}://{self.host}:{self.port}/api/v1/ws"
        if self.api_key:
            url += f"?api_key={self.api_key}"
        return url

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close active client session and WebSocket."""
        self._ws_running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform an HTTP request against the proxy API."""
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=json_data,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10.0),
            ) as response:
                if response.status in (401, 403):
                    text = await response.text()
                    raise GB50ProxyAuthError(f"Authentication failed ({response.status}): {text}")
                if response.status >= 400:
                    text = await response.text()
                    raise GB50ProxyError(f"API request failed ({response.status}) {url}: {text}")
                return await response.json()
        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as ex:
            raise GB50ProxyConnectionError(f"Failed to connect to GB-50 proxy at {url}: {ex}") from ex

    async def get_system_info(self) -> Dict[str, Any]:
        """Fetch system information and hardware specifications."""
        return await self.request("GET", "/system")

    async def get_groups(self) -> List[Dict[str, Any]]:
        """Fetch all groups with current telemetry and hardware capabilities."""
        return await self.request("GET", "/groups")

    async def get_group(self, group_id: int) -> Dict[str, Any]:
        """Fetch a single group by ID."""
        return await self.request("GET", f"/groups/{group_id}")

    async def set_group(self, group_id: int, **kwargs: Any) -> Dict[str, Any]:
        """Mutate state for an individual group."""
        clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return await self.request("PATCH", f"/groups/{group_id}", json_data=clean_kwargs)

    async def reset_filter(self, group_id: int) -> Dict[str, Any]:
        """Reset dirty filter warning sign for a group."""
        return await self.request("POST", f"/groups/{group_id}/reset-filter")

    async def apply_preset(self, preset_name: str) -> List[Dict[str, Any]]:
        """Trigger a church/facility preset scene."""
        return await self.request("POST", f"/presets/{preset_name}")

    async def get_alarms(self) -> List[Dict[str, Any]]:
        """Retrieve active malfunction alarms and error history."""
        return await self.request("GET", "/system/alarms")

    async def listen_events(
        self,
        on_message: Callable[[Dict[str, Any]], Any],
        on_disconnect: Optional[Callable[[], Any]] = None,
    ) -> None:
        """Persistent WebSocket event listener with heartbeat and exponential reconnect."""
        self._ws_running = True
        backoff = 1.0
        max_backoff = 30.0

        while self._ws_running:
            session = await self._get_session()
            try:
                _LOGGER.info("Connecting to GB-50 WebSocket stream at %s", self.ws_url)
                async with session.ws_connect(
                    self.ws_url,
                    headers=self._headers(),
                    heartbeat=25.0,
                ) as ws:
                    self._ws = ws
                    backoff = 1.0  # Reset backoff on successful connect
                    _LOGGER.info("GB-50 WebSocket stream connected")

                    async for msg in ws:
                        if not self._ws_running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                res = on_message(data)
                                if asyncio.iscoroutine(res):
                                    await res
                            except Exception as ex:
                                _LOGGER.error("Error processing GB-50 WebSocket message: %s", ex)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            _LOGGER.warning("GB-50 WebSocket connection closed")
                            break

            except GB50ProxyAuthError:
                _LOGGER.error("Fatal: GB-50 WebSocket authentication rejected. Check API key.")
                self._ws_running = False
                raise
            except Exception as ex:
                if not self._ws_running:
                    break
                _LOGGER.warning("GB-50 WebSocket error (%s). Reconnecting in %.1fs...", ex, backoff)

            if on_disconnect and self._ws_running:
                try:
                    res = on_disconnect()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as ex:
                    _LOGGER.error("Error in on_disconnect callback: %s", ex)

            if self._ws_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, max_backoff)

    def stop_listener(self) -> None:
        """Signal the WebSocket listener loop to terminate."""
        self._ws_running = False
        if self._ws and not self._ws.closed:
            asyncio.create_task(self._ws.close())
