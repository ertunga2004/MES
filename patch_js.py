import re

with open("mes_web/static/kiosk.js", "r", encoding="utf-8") as f:
    content = f.read()

target = """    } else if (action === "work_order_accept") {
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/work-orders/accept-active`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    }"""

new = """    } else if (action === "work_order_accept") {
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/work-orders/accept-active`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    } else if (action === "package_start") {
      const payload = (snapshot.big_action || {}).payload || {};
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/package/start`, {
        method: "POST",
        body: JSON.stringify({
          ...currentActorPayload(),
          package_order_id: payload.package_order_id,
        }),
      });
    } else if (action === "package_finish") {
      const payload = (snapshot.big_action || {}).payload || {};
      await fetchJson(`/api/modules/${state.moduleId}/kiosk/package/finish`, {
        method: "POST",
        body: JSON.stringify({
          ...currentActorPayload(),
          session_id: payload.session_id,
        }),
      });
    }"""

content = content.replace(target, new)

with open("mes_web/static/kiosk.js", "w", encoding="utf-8") as f:
    f.write(content)
