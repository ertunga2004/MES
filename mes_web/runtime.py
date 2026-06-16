from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .db.work_order_transition_writer import mirror_work_order_transition_from_state
from .db.work_order_mirror import mirror_work_orders_from_state
from .excel_runtime import ExcelRuntimeSink
from .mqtt_runtime import MqttIngestClient
from .oee_state import OeeRuntimeStateManager
from .store import DashboardStore, utc_now_text


logger = logging.getLogger(__name__)


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
        self.oee_manager = OeeRuntimeStateManager(
            config.oee_runtime_state_path,
            heartbeat_timeout_sec=config.heartbeat_timeout_sec,
            vision_decision_deadline_ms=config.vision_decision_deadline_ms,
            min_remaining_travel_ms_for_early_pick=config.min_remaining_travel_ms_for_early_pick,
            vision_degraded_fps=config.vision_degraded_fps,
            vision_degraded_latency_ratio=config.vision_degraded_latency_ratio,
            vision_bad_window_threshold=config.vision_bad_window_threshold,
            vision_recovery_window_threshold=config.vision_recovery_window_threshold,
        )
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
        current_state = self.oee_manager.read_state()
        bootstrap_imported = False
        current_orders = ((current_state.get("workOrders") or {}) if isinstance(current_state.get("workOrders"), dict) else {}).get("ordersById")
        if not isinstance(current_orders, dict) or not current_orders:
            candidates = sorted(self.config.work_orders_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
            if candidates:
                with contextlib.suppress(ValueError, OSError):
                    self.oee_manager.import_work_orders_from_file(candidates[0], replace_existing=True)
                    self.store.refresh_oee_runtime_state(self.config.module_id, force=True)
                    current_state = self.oee_manager.read_state()
                    bootstrap_imported = True
        self.store.refresh_oee_runtime_state(self.config.module_id, force=True)
        self.excel_sink.start()
        self.excel_sink.record_work_order_state(current_state, utc_now_text())
        if bootstrap_imported:
            self._sync_work_order_transition(current_state, event_type="bootstrap_import", replace_current=True)
        if self.config.db_mirror_work_orders:
            self._mirror_work_orders(current_state)
        self.mqtt_client.start()
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    def _mirror_work_orders(self, state: dict[str, Any]) -> None:
        if not self.config.db_mirror_work_orders:
            return
        try:
            result = mirror_work_orders_from_state(self.config, state)
        except Exception:
            logger.exception("Work order DB mirror hook failed unexpectedly")
            return
        if result.status == "error":
            logger.warning("Work order DB mirror failed: %s", result.message)

    def _sync_work_order_transition(self, state: dict[str, Any], *, event_type: str, replace_current: bool = False) -> None:
        try:
            result = mirror_work_order_transition_from_state(
                self.config,
                state,
                event_type=event_type,
                replace_current=replace_current,
            )
        except Exception:
            logger.exception("Work order DB transition hook failed unexpectedly")
            return
        if result.reason == "error_fail_open":
            logger.warning("Work order DB transition hook failed open: %s", result.error_type)

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
            tick_now = datetime.now().astimezone()
            tick_changed = self.oee_manager.tick(now=tick_now)
            self.store.refresh_oee_runtime_state(self.config.module_id, force=tick_changed)
            if tick_changed:
                self.excel_sink.record_work_order_state(self.oee_manager.read_state(), utc_now_text(tick_now))
            fingerprint = self.store.connection_fingerprint(
                self.config.module_id,
                now=datetime.now(timezone.utc),
            )
            if tick_changed or fingerprint != self._last_fingerprint:
                self._last_fingerprint = fingerprint
                self.hub.notify_change(self.config.module_id)
