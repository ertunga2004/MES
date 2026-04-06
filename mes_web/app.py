from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .command_policy import is_local_only_command
from .config import AppConfig
from .runtime import RuntimeService, SnapshotHub
from .store import DashboardStore, utc_now_text


config = AppConfig.from_env()
store = DashboardStore(config)
hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
runtime_service = RuntimeService(config, store, hub)
oee_state_manager = runtime_service.oee_manager


def create_app() -> FastAPI:
    app = FastAPI(title="MES Web", version="0.1.0")
    static_dir = Path(config.static_dir)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.on_event("startup")
    async def on_startup() -> None:
        await runtime_service.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await runtime_service.stop()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "time": utc_now_text()}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

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
            store.reset_counts(module_id, received_at=stamp)
            runtime_service.excel_sink.record_local_counts_reset(stamp)
            return {"status": "accepted", "kind": kind, "value": value, "dispatch": "local_only"}

        try:
            runtime_service.mqtt_client.publish_command(value)
        except RuntimeError as exc:
            detail = str(exc)
            status_code = 503 if detail.startswith("MQTT_") else 500
            raise HTTPException(status_code=status_code, detail=detail) from exc

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
        recent_log = str(result.get("recent_log") or "").strip()
        if recent_log:
            store.append_system_log(module_id, recent_log, topic="local/oee")

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
