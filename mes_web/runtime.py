from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .excel_runtime import ExcelRuntimeSink
from .mqtt_runtime import MqttIngestClient
from .oee_state import OeeRuntimeStateManager
from .store import DashboardStore


class SnapshotHub:
    def __init__(self, store: DashboardStore, *, coalesce_ms: int) -> None:
        self.store = store
        self.coalesce_delay = max(coalesce_ms, 1) / 1000
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._pending: set[str] = set()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def register(self, module_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        with self._lock:
            self._queues[module_id].add(queue)
        return queue

    async def unregister(self, module_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._queues[module_id].discard(queue)

    def _offer(self, queue: asyncio.Queue[dict[str, Any]], message: dict[str, Any]) -> None:
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        queue.put_nowait(message)

    def notify_change(self, module_id: str) -> None:
        if self._loop is None:
            return

        def schedule() -> None:
            if module_id in self._pending:
                return
            self._pending.add(module_id)
            asyncio.create_task(self._flush_after_delay(module_id))

        self._loop.call_soon_threadsafe(schedule)

    async def _flush_after_delay(self, module_id: str) -> None:
        try:
            await asyncio.sleep(self.coalesce_delay)
            snapshot = self.store.get_dashboard_snapshot(module_id)
            message = {
                "type": "dashboard_snapshot",
                "module_id": module_id,
                "data": snapshot,
            }
            with self._lock:
                queues = list(self._queues.get(module_id, set()))
            for queue in queues:
                self._offer(queue, message)
        finally:
            self._pending.discard(module_id)


class RuntimeService:
    def __init__(self, config: AppConfig, store: DashboardStore, hub: SnapshotHub) -> None:
        self.config = config
        self.store = store
        self.hub = hub
        self.excel_sink = ExcelRuntimeSink(config)
        self.oee_manager = OeeRuntimeStateManager(config.oee_runtime_state_path)
        self.mqtt_client = MqttIngestClient(
            config,
            store,
            excel_sink=self.excel_sink,
            oee_state_manager=self.oee_manager,
        )
        self._watchdog_task: asyncio.Task[None] | None = None
        self._last_fingerprint: tuple[Any, ...] | None = None
        self.store.register_listener(self.hub.notify_change)

    async def start(self) -> None:
        self.hub.attach_loop(asyncio.get_running_loop())
        if self.oee_manager.deactivate_active_shift_on_startup():
            self.store.refresh_oee_runtime_state(self.config.module_id, force=True)
        self.excel_sink.start()
        self.mqtt_client.start()
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def stop(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        self.mqtt_client.stop()
        self.excel_sink.stop()

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            tick_changed = self.oee_manager.tick(now=datetime.now().astimezone())
            self.store.refresh_oee_runtime_state(self.config.module_id, force=tick_changed)
            fingerprint = self.store.connection_fingerprint(
                self.config.module_id,
                now=datetime.now(timezone.utc),
            )
            if tick_changed or fingerprint != self._last_fingerprint:
                self._last_fingerprint = fingerprint
                self.hub.notify_change(self.config.module_id)
