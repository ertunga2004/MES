from __future__ import annotations
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .command_policy import is_local_only_command
from .config import AppConfig
from .oee_state import WorkOrderTransitionReasonRequired
from .runtime import RuntimeService, SnapshotHub
from .store import DashboardStore, utc_now_text
from .windows_asyncio import install_windows_connection_reset_filter


config = AppConfig.from_env()
store = DashboardStore(config)
hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
runtime_service = RuntimeService(config, store, hub)
oee_state_manager = runtime_service.oee_manager


def create_app() -> FastAPI:
    app = FastAPI(title="MES Web", version="0.1.0")
    static_dir = Path(config.static_dir)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def sync_work_order_runtime(state: dict[str, Any] | None = None) -> None:
        runtime_state = state if isinstance(state, dict) else oee_state_manager.read_state()
        runtime_service.excel_sink.record_work_order_state(runtime_state, utc_now_text())

    @app.on_event("startup")
    async def on_startup() -> None:
        install_windows_connection_reset_filter()
        await runtime_service.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await runtime_service.stop()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "time": utc_now_text()}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            static_dir / "index.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/api/modules")
    async def list_modules() -> list[dict[str, Any]]:
        return store.modules_summary()

    @app.get("/api/modules/{module_id}/dashboard")
    async def get_dashboard(module_id: str) -> dict[str, Any]:
        try:
            return store.get_dashboard_snapshot(module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND") from exc

    @app.post("/api/modules/{module_id}/commands")
    async def publish_command(module_id: str, payload: dict[str, str]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        kind = str(payload.get("kind") or "").strip().lower()
        value = str(payload.get("value") or "").strip()
        if kind not in {"preset", "manual"} or not value:
            raise HTTPException(status_code=400, detail="INVALID_COMMAND_PAYLOAD")

        permissions = store.command_permissions()
        if kind == "preset" and value not in permissions["allowed_presets"]:
            raise HTTPException(status_code=400, detail="UNKNOWN_PRESET_COMMAND")
        if not permissions["publish_enabled"]:
            raise HTTPException(status_code=409, detail="COMMAND_PUBLISH_DISABLED")
        if kind == "manual" and not permissions["manual_command_enabled"]:
            raise HTTPException(status_code=409, detail="MANUAL_COMMAND_DISABLED")

        if is_local_only_command(kind, value):
            stamp = utc_now_text()
            runtime_result: dict[str, Any] | None = None
            try:
                runtime_result = oee_state_manager.reset_runtime_counts()
            except OSError as exc:
                raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
            store.reset_counts(module_id, received_at=stamp)
            store.refresh_oee_runtime_state(module_id, force=True)
            sync_work_order_runtime(runtime_result.get("state") if isinstance(runtime_result, dict) and isinstance(runtime_result.get("state"), dict) else None)
            runtime_service.excel_sink.record_local_counts_reset(stamp)
            return {"status": "accepted", "kind": kind, "value": value, "dispatch": "local_only"}

        try:
            runtime_service.mqtt_client.publish_command(value)
        except RuntimeError as exc:
            detail = str(exc)
            status_code = 503 if detail.startswith("MQTT_") else 500
            raise HTTPException(status_code=status_code, detail=detail) from exc
        store.append_system_log(module_id, f"SYSTEM|CMD|PUBLISH|KIND={kind.upper()}|VALUE={value}", topic="local/command")

        return {"status": "accepted", "kind": kind, "value": value, "dispatch": "mqtt"}

    @app.post("/api/modules/{module_id}/oee/control")
    async def update_oee_control(module_id: str, payload: dict[str, Any]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        action = str(payload.get("action") or "").strip().lower()
        value = payload.get("value")
        try:
            result = oee_state_manager.apply_control(action, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        recent_log = str(result.get("recent_log") or "").strip()
        if recent_log:
            store.append_system_log(module_id, recent_log, topic="local/oee")
            runtime_service.excel_sink.record_system_oee_log(recent_log, utc_now_text())

        return {
            "status": "accepted",
            "action": action,
            "summary": str(result.get("summary") or ""),
        }

    @app.post("/api/modules/{module_id}/oee/quality-override")
    async def apply_oee_quality_override(module_id: str, payload: dict[str, Any]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        item_id = str(payload.get("item_id") or "").strip()
        classification = str(payload.get("classification") or "").strip().upper()
        try:
            result = oee_state_manager.apply_quality_override(item_id, classification)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        override = result.get("override") if isinstance(result.get("override"), dict) else None
        if override is not None:
            runtime_service.excel_sink.record_quality_override(
                str(override.get("item_id") or item_id),
                str(override.get("classification") or classification),
                str(override.get("applied_at") or utc_now_text()),
            )
        return {
            "status": "accepted",
            "item_id": item_id,
            "classification": classification,
            "summary": str(result.get("summary") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/import")
    async def import_work_orders(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        orders = payload.get("orders")
        replace_existing = bool(payload.get("replace_existing", True))
        try:
            result = oee_state_manager.import_work_orders(orders, replace_existing=replace_existing)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri listesi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|IMPORT|COUNT={int(result.get('total_count') or 0)}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "queued_count": int(result.get("queued_count") or 0),
            "total_count": int(result.get("total_count") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reload")
    async def reload_work_orders(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        candidates = sorted(config.work_orders_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            raise HTTPException(status_code=404, detail="WORK_ORDER_SOURCE_NOT_FOUND")
        try:
            result = oee_state_manager.import_work_orders_from_file(candidates[0], replace_existing=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri kaynagi yenilendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|RELOAD|FILE={candidates[0].name}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "source_file": candidates[0].name,
        }

    @app.post("/api/modules/{module_id}/work-orders/tolerance")
    async def update_work_order_tolerance(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.set_work_order_tolerance(payload.get("minutes", payload.get("tolerance_minutes")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri toleransi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|TOLERANCE|{result.get('tolerance_minutes')}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "tolerance_minutes": float(result.get("tolerance_minutes") or 0.0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reorder")
    async def reorder_work_orders(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.reorder_work_orders(payload.get("order_ids") or payload.get("orderIds"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri sirasi guncellendi.")
        store.append_system_log(module_id, "SYSTEM|WORK_ORDER|REORDER", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
        }

    @app.post("/api/modules/{module_id}/work-orders/start")
    async def start_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.start_work_order(
                str(payload.get("order_id") or payload.get("orderId") or ""),
                operator_code=str(payload.get("operator_code") or payload.get("operatorCode") or ""),
                operator_name=str(payload.get("operator_name") or payload.get("operatorName") or ""),
                transition_reason=str(payload.get("transition_reason") or payload.get("transitionReason") or ""),
                started_at=str(payload.get("started_at") or payload.get("startedAt") or ""),
            )
        except WorkOrderTransitionReasonRequired as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WORK_ORDER_REASON_REQUIRED",
                    "order_id": exc.order_id,
                    "previous_order_id": exc.previous_order_id,
                    "elapsed_minutes": round(exc.elapsed_minutes, 1),
                    "tolerance_minutes": round(exc.tolerance_minutes, 1),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Is emri baslatildi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|START|ORDER={order.get('orderId') or ''}|OPERATOR={order.get('startedBy') or ''}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "inventory_used": int(result.get("inventory_used") or 0),
            "order_id": str(order.get("orderId") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/accept-active")
    async def accept_active_work_order(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.accept_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Is emri operator onayi ile kapatildi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|ACCEPT|ORDER={order.get('orderId') or ''}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "order_id": str(order.get("orderId") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/rollback-active")
    async def rollback_active_work_order(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.rollback_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Aktif is emri geri alindi.")
        store.append_system_log(
            module_id,
            (
                f"SYSTEM|WORK_ORDER|ROLLBACK|ORDER={order.get('orderId') or ''}"
                f"|RETURNED={int(result.get('returned_to_inventory') or 0)}"
            ),
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "order_id": str(order.get("orderId") or ""),
            "returned_to_inventory": int(result.get("returned_to_inventory") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reset")
    async def reset_work_orders(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.reset_work_orders()
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emirleri sifirlandi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|RESET|CLEARED={int(result.get('cleared_item_count') or 0)}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "cleared_item_count": int(result.get("cleared_item_count") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/inventory/remove")
    async def remove_inventory_stock(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.remove_inventory_stock(
                str(payload.get("match_key") or payload.get("matchKey") or ""),
                payload.get("quantity", 1),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Depo stogu guncellendi.")
        store.append_system_log(
            module_id,
            (
                f"SYSTEM|WORK_ORDER|INVENTORY_REMOVE|MATCH_KEY={result.get('match_key') or ''}"
                f"|QTY={int(result.get('removed_qty') or 0)}"
            ),
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "match_key": str(result.get("match_key") or ""),
            "removed_qty": int(result.get("removed_qty") or 0),
            "remaining_qty": int(result.get("remaining_qty") or 0),
        }

    @app.websocket("/ws/modules/{module_id}")
    async def module_stream(websocket: WebSocket, module_id: str) -> None:
        if module_id != config.module_id:
            await websocket.close(code=4404)
            return

        await websocket.accept()
        queue = await hub.register(module_id)
        try:
            await websocket.send_json(
                {
                    "type": "dashboard_snapshot",
                    "module_id": module_id,
                    "data": store.get_dashboard_snapshot(module_id),
                }
            )
            while True:
                message = await queue.get()
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        finally:
            await hub.unregister(module_id, queue)

    return app


app = create_app()
