import re

with open("mes_web/app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update _kiosk_big_action signature
target_sig = """def _kiosk_big_action(
    *,
    operational_state: str,
    active_order: dict[str, Any] | None,
    queue_orders: list[dict[str, Any]],
    opening_session: dict[str, Any] | None,
    closing_session: dict[str, Any] | None,
) -> dict[str, Any]:"""
new_sig = """def _kiosk_big_action(
    *,
    operational_state: str,
    active_order: dict[str, Any] | None,
    queue_orders: list[dict[str, Any]],
    opening_session: dict[str, Any] | None,
    closing_session: dict[str, Any] | None,
    packaging: dict[str, Any] | None = None,
) -> dict[str, Any]:"""
content = content.replace(target_sig, new_sig)

# 2. Update active order logic in _kiosk_big_action
target_logic = """    if isinstance(active_order, dict) and str(active_order.get("status") or "") == "active":
        return {
            "action": "wait",
            "label": "Aktif Is Emri Calisiyor",
            "enabled": False,
            "phase": "",
        }"""

new_logic = """    if isinstance(active_order, dict) and str(active_order.get("status") or "") == "active":
        if _is_kiosk_package_order(str(active_order.get("order_id") or ""), active_order):
            active_sessions = packaging.get("active_sessions", []) if isinstance(packaging, dict) else []
            my_session = next((s for s in active_sessions if str(s.get("package_order_id") or "") == str(active_order.get("order_id") or "")), None)
            if my_session:
                return {
                    "action": "package_finish",
                    "label": "Paketlemeyi Bitir",
                    "enabled": True,
                    "phase": "",
                    "payload": {"session_id": str(my_session.get("session_id") or "")}
                }
            else:
                available_count = (packaging.get("buffer", {}) if isinstance(packaging, dict) else {}).get("available_count", 0)
                if available_count > 0:
                    return {
                        "action": "package_start",
                        "label": "Paketlemeyi Baslat",
                        "enabled": True,
                        "phase": "",
                        "payload": {"package_order_id": str(active_order.get("order_id") or "")}
                    }
                else:
                    return {
                        "action": "wait",
                        "label": "Uygun GOOD kutu yok",
                        "enabled": False,
                        "phase": "",
                    }

        return {
            "action": "wait",
            "label": "Aktif Is Emri Calisiyor",
            "enabled": False,
            "phase": "",
        }"""
content = content.replace(target_logic, new_logic)

# 3. Update _build_kiosk_snapshot packaging evaluation and big_action call
target_snapshot1 = """    operational_state = str(state.get("operationalState") or "idle_ready")
    permissions = store.command_permissions()
    return {"""
new_snapshot1 = """    operational_state = str(state.get("operationalState") or "idle_ready")
    permissions = store.command_permissions()
    packaging_state = _project_kiosk_packaging(state, ordered_orders)
    return {"""
content = content.replace(target_snapshot1, new_snapshot1)

target_snapshot2 = """        "packaging": _project_kiosk_packaging(state, ordered_orders),"""
new_snapshot2 = """        "packaging": packaging_state,"""
content = content.replace(target_snapshot2, new_snapshot2)

target_snapshot3 = """        "big_action": _kiosk_big_action(
            operational_state=operational_state,
            active_order=active_order,
            queue_orders=queue_orders,
            opening_session=opening_session if isinstance(opening_session, dict) else None,
            closing_session=closing_session if isinstance(closing_session, dict) else None,
        ),"""
new_snapshot3 = """        "big_action": _kiosk_big_action(
            operational_state=operational_state,
            active_order=active_order,
            queue_orders=queue_orders,
            opening_session=opening_session if isinstance(opening_session, dict) else None,
            closing_session=closing_session if isinstance(closing_session, dict) else None,
            packaging=packaging_state,
        ),"""
content = content.replace(target_snapshot3, new_snapshot3)

with open("mes_web/app.py", "w", encoding="utf-8") as f:
    f.write(content)
