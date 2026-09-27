"""DataUpdateCoordinator managing live telemetry and dynamic discovery for GB-50."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any, Dict, List, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import GB50ProxyClient, GB50ProxyError, GB50ProxyConnectionError, GB50ProxyAuthError
from .const import (
    DOMAIN,
    SIGNAL_NEW_GROUP_DISCOVERED,
    SIGNAL_GROUP_UPDATED,
    SIGNAL_SYSTEM_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


class GB50DataUpdateCoordinator(DataUpdateCoordinator[Dict[int, Dict[str, Any]]]):
    """Manages real-time WebSocket state streaming and dynamic entity discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GB50ProxyClient,
        entry_id: str,
    ) -> None:
        """Initialize coordinator with client and push stream handlers."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client.host}",
            update_interval=timedelta(seconds=60),  # Safety fallback poll; WebSocket handles real-time push
        )
        self.client = client
        self.entry_id = entry_id
        self.system_info: Dict[str, Any] = {}
        self.groups: Dict[int, Dict[str, Any]] = {}
        self.alarms: List[Dict[str, Any]] = []
        self._known_group_ids: Set[int] = set()
        self._ws_task: Optional[asyncio.Task] = None
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Return true if WebSocket stream or API is actively communicating."""
        return self._is_connected

    async def _async_update_data(self) -> Dict[int, Dict[str, Any]]:
        """Fallback polling fetch when WebSocket stream is reconnecting."""
        try:
            raw_groups = await self.client.get_groups()
            for group in raw_groups:
                gid = group.get("group_id")
                if gid is not None:
                    self._process_group_payload(group)
            self._is_connected = True
            return self.groups
        except (GB50ProxyConnectionError, GB50ProxyError) as ex:
            self._is_connected = False
            raise UpdateFailed(f"Error communicating with GB-50 proxy: {ex}") from ex

    async def async_setup(self) -> None:
        """Perform initial discovery fetch and start background WebSocket push stream."""
        _LOGGER.info("Starting GB-50 discovery handshake with proxy at %s:%s", self.client.host, self.client.port)
        
        # 1. Fetch system info
        self.system_info = await self.client.get_system_info()
        _LOGGER.info(
            "Discovered controller: %s (%s v%s, serial: %s)",
            self.system_info.get("system_name"),
            self.system_info.get("model"),
            self.system_info.get("version"),
            self.system_info.get("serial_number"),
        )

        # 2. Fetch initial groups snapshot
        initial_groups = await self.client.get_groups()
        for group in initial_groups:
            self._process_group_payload(group, is_initial=True)

        self._is_connected = True
        self.async_set_updated_data(self.groups)

        # 3. Start background WebSocket push listener task
        self._ws_task = self.hass.async_create_background_task(
            self._listen_websocket_stream(),
            name=f"{DOMAIN}_ws_{self.entry_id}",
        )

    def _process_group_payload(self, group: Dict[str, Any], is_initial: bool = False) -> None:
        """Process incoming group payload and dispatch discovery if new."""
        gid = group.get("group_id")
        if gid is None:
            return

        self.groups[gid] = group

        if gid not in self._known_group_ids:
            self._known_group_ids.add(gid)
            if not is_initial:
                _LOGGER.info("Dynamically discovered new GB-50 group %s ('%s')", gid, group.get("name"))
                # Notify platforms to instantiate new entity for this group
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=self.entry_id),
                    group,
                )

        # Signal individual group listeners
        async_dispatcher_send(
            self.hass,
            SIGNAL_GROUP_UPDATED.format(entry_id=self.entry_id, group_id=gid),
            group,
        )

    async def _listen_websocket_stream(self) -> None:
        """Run persistent WebSocket stream and handle incoming push notifications."""
        @callback
        def on_message(data: Dict[str, Any]) -> None:
            event_type = data.get("event")
            if event_type in ("initial_state", "group_updates"):
                groups_list = data.get("groups", [])
                for g in groups_list:
                    self._process_group_payload(g)
                self._is_connected = True
                self.async_set_updated_data(self.groups)
            elif event_type == "connection_status":
                self._is_connected = bool(data.get("connected", True))
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_SYSTEM_UPDATED.format(entry_id=self.entry_id),
                )

        @callback
        def on_disconnect() -> None:
            self._is_connected = False
            async_dispatcher_send(
                self.hass,
                SIGNAL_SYSTEM_UPDATED.format(entry_id=self.entry_id),
            )

        try:
            await self.client.listen_events(on_message=on_message, on_disconnect=on_disconnect)
        except asyncio.CancelledError:
            _LOGGER.debug("GB-50 WebSocket stream task cancelled")
        except Exception as ex:
            _LOGGER.error("Fatal error in GB-50 WebSocket listener: %s", ex)

    async def async_close(self) -> None:
        """Stop WebSocket task and close proxy client."""
        if self._ws_task and not self._ws_task.done():
            self.client.stop_listener()
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
