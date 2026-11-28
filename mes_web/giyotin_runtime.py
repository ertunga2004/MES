"""Protocol 4 bridge between the Giyotin tablet, MES orders and Nano."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from .manual_coating import manual_coating_progress


LOG = logging.getLogger(__name__)
PERMIT_SECONDS = 15
ACK_SECONDS = 4
READY_STATES = ("PERMIT_REQUIRED", "READY", "WAIT_RELEASE")
LINKS = ("wifi_connected", "mqtt_connected", "nano_connected")
PERMIT_ACK = re.compile(r"ACK\|PERMIT\|permit_id=(\d+)\|permit=([01])")


class GiyotinError(ValueError):
    pass


@dataclass
class Write:
    action: str
    number: int
    sent_at: float
    status_version: int
    permit: int | None = None
    ack: bool = False
    confirmed: bool = False
    calibration: dict | None = None
    revision: str | None = None


def order_progress(state):
    progress = manual_coating_progress(state, cutting_enabled=True)
    return progress if progress and progress["cutting"]["order_open"] else None


def record_tape(state, permit):
    batches = state["cuttingWorkflow"]["batches"]
    batch = batches.setdefault(permit["orderId"], {}).setdefault(permit["orderKey"], {"cut_tapes": 0})
    batch["cut_tapes"] += 1


def event_permit(data, payload, line, event_id, live_session):
    """Resolve persisted permit ownership, including events replayed in a new MQTT session."""
    fields = dict(part.split("=", 1) for part in line.split("|") if "=" in part)
    session = fields.get("session_id") or payload.get("session_id")
    number = str(fields.get("permit_id") or payload.get("permit_id") or "")
    permits = data.get("permits", {})
    if session and number.isdecimal() and not event_id:
        return permits.get(f"{session}:{number}")
    # The guide specifies a derived ID but does not prescribe its separator.
    if event_id:
        candidates = []
        for separator in (":", "|", "-", "_", "/"):
            original, _, suffix = event_id.rpartition(separator)
            key = f"{original}:{suffix}"
            if original and suffix.isdecimal() and key in permits:
                candidates.append(permits[key])
        if candidates and all(row == candidates[0] for row in candidates):
            return candidates[0] if not number or str(candidates[0]["permitId"]) == number else None
        if not candidates and isinstance(session, str) and number.isdecimal():
            return permits.get(f"{session}:{number}")
        return None
    return permits.get(f"{live_session}:{number}") if number.isdecimal() else None


class GiyotinRuntime:
    def __init__(self, config, manager, read_shift, publish, *, on_production=None, clock=monotonic):
        self.config = config
        self.manager = manager
        self.read_shift = read_shift
        self.publish = publish
        self.on_production = on_production
        self.clock = clock
        self.lock = RLock()
        self.session = None
        self.heartbeat_at = None
        self.bridge = {}
        self.bridge_at = None
        self.status = {}
        self.status_at = None
        self.status_version = 0
        self.status_required = 0
        self.last_query = float("-inf")
        self.run = None
        self.write = None
        self.revoke = False
        self.reason = None
        self.calibration = None
        self.rejection = None
        self.pong_at = None
        self.initialized = False
        self.links_were_ready = False
        self.event_acks = set()
        self.pending_until = None
        self.revoke_after = float("-inf")
        self.uncertain_seen = False

    def _transport(self):
        now = self.clock()
        return (self.session is not None and self.heartbeat_at is not None and self.bridge_at is not None
                and now - self.heartbeat_at <= self.config.heartbeat_timeout_sec
                and now - self.bridge_at <= self.config.bridge_stale_after_sec
                and all(self.bridge.get(link) is True for link in LINKS))

    def _fresh_status(self):
        return (self.status_at is not None and self.status_version >= self.status_required
                and self.clock() - self.status_at <= self.config.bridge_stale_after_sec)

    def _quiet_status(self):
        return (self._fresh_status() and self.status.get("cycle_busy") is False
                and self.status.get("permit_active") is False and self.status.get("event_pending") is not True)

    def _idle(self):
        return self._quiet_status() and self.status.get("nano_state") in READY_STATES

    def _ready(self):
        return self._transport() and self._idle() and self.status.get("nano_ready") is True

    def _send(self, payload):
        if not self.config.publish_enabled:
            return False
        try:
            self.publish(payload)
        except RuntimeError:
            return False
        return True

    def _halt(self, reason, *, review=False):
        self.run = None
        self.write = None
        if not self.revoke:
            self.revoke_after = float("-inf")
        self.revoke = True
        self.reason = reason
        self.status_required = self.status_version + 1 if review else self.status_required
        if review:
            def mark(_state, data):
                if data.get("review"):
                    return None, False
                data["review"] = {"id": uuid4().hex, "reason": reason, "permit": data.get("pending")}
                return None, True
            self.manager.edit_giyotin(mark)

    def disconnect(self):
        with self.lock:
            try:
                data = self.manager.read_state()["cuttingWorkflow"]["protocol4"]
                if self.run or self.write or data.get("pending"):
                    self._halt("connection_lost", review=bool(data.get("pending")))
            except OSError:
                LOG.exception("Giyotin disconnect could not be recorded")
                self._fail()
            finally:
                self.session = self.heartbeat_at = self.bridge_at = self.status_at = None
                self.bridge = self.status = {}
                self.links_were_ready = False
                self.revoke_after = float("-inf")
                self.uncertain_seen = False

    def shutdown(self):
        with self.lock:
            if self.run or self.write:
                if not self.revoke:
                    self._halt("stopped")
                self.tick()

    def _start_write(self, *, permit=None, calibration=None, expected=None):
        action = "CALIBRATE" if calibration is not None else "PERMIT"
        session = self.session
        write = None

        def reserve(state, data):
            nonlocal write
            if permit == 1:
                progress = order_progress(state)
                shift = self.read_shift()
                if (not progress or not shift or data.get("review") or data.get("pending")
                        or progress["cutting"]["legacy_blocked"]
                        or progress["cutting"]["cut_tapes"] >= progress["cutting"]["target_tapes"]
                        or (progress["order_id"], progress["order_key"], shift["startedAt"]) != expected):
                    return None, False
            numbers = data.setdefault("sequence", {})
            number = numbers[session] = numbers.get(session, 0) + 1
            payload = {"action": action, "session_id": session}
            if permit is not None:
                payload.update(permit_id=number, permit=permit)
            else:
                payload.update(command_id=number, **calibration)
            if permit == 1:
                key = f"{session}:{number}"
                data["pending"] = key
                station_order = progress["cutting"].get("station_order") or {}
                data.setdefault("permits", {})[key] = {
                    "sessionId": session, "permitId": number, "orderId": expected[0], "orderKey": expected[1],
                    "stationOrderId": station_order.get("station_order_id", ""),
                    "unit": station_order.get("unit", "adet"),
                    "shiftStartedAt": expected[2], "operator": shift["operator"], "state": "issued",
                    "issuedAt": datetime.now(timezone.utc).isoformat(),
                }
            write = Write(action, number, self.clock(), self.status_version, permit, calibration=calibration)
            return payload, True

        if permit == 0:
            self.revoke_after = self.clock() + ACK_SECONDS
        try:
            sent = self.manager.edit_giyotin(reserve, self._send_after_commit)
        except GiyotinError:
            if permit == 1:
                self._halt("publish_failed", review=True)
            raise
        if sent is None:
            return False
        self.write = write
        if permit != 0:
            self.rejection = None
        if permit == 1:
            self.pending_until = write.sent_at + PERMIT_SECONDS + self.config.bridge_stale_after_sec
        return True

    def _send_after_commit(self, payload):
        if not self._transport() or not self._send(payload):
            raise GiyotinError("publish_failed")

    def _close_pending(self):
        def close(_state, data):
            key = data.get("pending")
            if key and data["permits"][key]["state"] == "issued" and not data.get("review"):
                data["permits"][key]["state"] = "closed"
                data.pop("pending")
                return None, True
            return None, False
        self.manager.edit_giyotin(close)

    def handle(self, topic, raw, received_at, *, retained=False):
        if retained or topic == "command":
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        with self.lock:
            if topic == "heartbeat":
                session = payload.get("session_id")
                if type(payload.get("protocol")) is not int or payload["protocol"] != 4 or not isinstance(session, str) or not session.strip():
                    if self.session:
                        self.disconnect()
                    return
                if self.session and (session != self.session or not self._heartbeat_fresh()):
                    self.disconnect()
                self.session = session
                self.heartbeat_at = self.clock()
            elif topic == "logs":
                self._log(payload, received_at)
            elif not self._heartbeat_fresh():
                return
            elif topic in {"bridge_status", "status"}:
                if payload.get("session_id", self.session) != self.session:
                    return
                self._telemetry(topic, payload)
            self._advance()

    def _heartbeat_fresh(self):
        return self.heartbeat_at is not None and self.clock() - self.heartbeat_at <= self.config.heartbeat_timeout_sec

    def _telemetry(self, topic, payload):
        if topic == "bridge_status":
            old, new = self.bridge.get("dropped_publish"), payload.get("dropped_publish")
            self.bridge, self.bridge_at = payload, self.clock()
            if type(old) is int and type(new) is int and new > old:
                self._halt("telemetry_loss", review=True)
                self.last_query = float("-inf")
            return
        old, new = self.status.get("uptime_ms"), payload.get("uptime_ms")
        if type(old) is int and type(new) is int and new < old:
            self._device_reset()
        self.status = payload
        self.status_at = self.clock()
        self.status_version += 1
        uncertain = payload.get("nano_state") == "CYCLE_UNCERTAIN"
        if uncertain and not self.uncertain_seen:
            self._halt("cycle_uncertain", review=True)
        self.uncertain_seen = uncertain
        if payload.get("cycle_busy") is True:
            def started(_state, data):
                key = data.get("pending")
                if key and data["permits"][key]["sessionId"] == self.session and data["permits"][key]["state"] == "issued":
                    data["permits"][key]["state"] = "started"
                    return None, True
                return None, False
            self.manager.edit_giyotin(started)

    def _device_reset(self):
        data = self.manager.read_state()["cuttingWorkflow"]["protocol4"]
        self.status_at = None
        self._halt("nano_reset", review=bool(data.get("pending")))

    def _log(self, payload, stamp):
        line = payload.get("nano_line")
        line = line if isinstance(line, str) else ""
        kind = payload.get("event") or payload.get("event_type") or payload.get("type")
        if kind == "NANO_PONG":
            self.pong_at = stamp
            return
        if not self._heartbeat_fresh():
            return
        tokens = line.split("|")
        if kind not in ("CUT_START", "CUT_DONE", "CYCLE_UNCERTAIN"):
            kind = next((token for token in tokens[:2] if token in ("CUT_START", "CUT_DONE", "CYCLE_UNCERTAIN")), kind)
        if kind in ("CUT_START", "CUT_DONE", "CYCLE_UNCERTAIN"):
            self._event(kind, payload, line, stamp)
            return
        if payload.get("session_id", self.session) != self.session:
            return
        if kind == "NANO_BOOT":
            self._device_reset()
            return
        write = self.write
        if write is None:
            return
        if kind == "NANO_ACK":
            ack = PERMIT_ACK.fullmatch(line)
            if ack and write.action == "PERMIT" and (int(ack[1]), int(ack[2])) == (write.number, write.permit):
                write.ack = True
            elif write.action == "CALIBRATE" and line.startswith("ACK|CALIBRATE|revision="):
                write.revision = line.split("|")[2].partition("=")[2]
                write.ack = bool(write.revision)
        elif kind in ("COMMAND_REJECTED", "NANO_COMMAND_REJECTED"):
            rejected = payload.get("permit_id", payload.get("command_id"))
            if rejected is not None and str(rejected) != str(write.number):
                return
            reason = payload.get("reason") or line
            self.rejection = reason[:180] if isinstance(reason, str) else None
            if write.action == "CALIBRATE":
                self.calibration = "rejected"
                self.write = None
            elif write.permit == 0:
                self.write = None
            else:
                self._halt("command_rejected", review=True)

    def _event(self, kind, payload, line, stamp):
        fields = dict(part.split("=", 1) for part in line.split("|") if "=" in part)
        raw_id = fields.get("event_id") or payload.get("event_id")
        event_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None

        credited = False

        def save(state, data):
            nonlocal credited
            permit = event_permit(data, payload, line, event_id, self.session)
            if kind == "CUT_START":
                if permit and permit["state"] in {"issued", "started"} and not permit.get("startedAt"):
                    permit.update(state="started", startedAt=stamp)
                    return False, True
                return False, False
            events = data.setdefault("events", {})
            if event_id and event_id in events:
                return bool(not events[event_id].get("unresolved")), False
            if kind == "CYCLE_UNCERTAIN" or not permit or not event_id:
                reason = "cycle_uncertain" if kind == "CYCLE_UNCERTAIN" else "unmatched_event"
                key = f'{permit["sessionId"]}:{permit["permitId"]}' if permit else None
                review = data.get("review")
                if event_id:
                    events[event_id] = {"eventId": event_id, "recordedAt": stamp, "count": 0, "unresolved": True,
                                        "reason": reason, "atUptimeMs": payload.get("at_uptime_ms"), "permit": key}
                if not review:
                    data["review"] = {"id": uuid4().hex, "reason": reason, "permit": key,
                                      "eventId": event_id, "receivedAt": stamp}
                elif not review.get("eventId") and (key == review.get("permit") or kind == "CYCLE_UNCERTAIN"):
                    review.update(eventId=event_id, receivedAt=stamp)
                return None, True
            credited = permit["state"] not in {"done", "reconciled"}
            if credited:
                record_tape(state, permit)
                permit.update(state="done", eventId=event_id)
            events[event_id] = {**permit, "eventId": event_id, "recordedAt": stamp, "count": int(credited),
                                "atUptimeMs": payload.get("at_uptime_ms")}
            if data.get("pending") == f'{permit["sessionId"]}:{permit["permitId"]}':
                data.pop("pending")
            return True, True

        ack = self.manager.edit_giyotin(save)
        if credited and self.on_production:
            self.on_production(stamp)
        if ack is None:
            self._halt("cycle_uncertain" if kind == "CYCLE_UNCERTAIN" else "unmatched_event")
        elif ack:
            self.event_acks.add(event_id)
            if self.write and self.write.permit == 1:
                data = self.manager.read_state()["cuttingWorkflow"]["protocol4"]
                if not data.get("pending"):
                    self.write = None
                    self.status_required = self.status_version + 1

    def _advance(self):
        state = self.manager.read_state()
        data = state["cuttingWorkflow"]["protocol4"]
        if not self.initialized:
            self.initialized = True
            if data.get("pending"):
                self._halt("backend_restart", review=True)
        transport = self._transport()
        if not transport:
            if self.links_were_ready:
                self.status_at = None
                if self.run or self.write or data.get("pending"):
                    self._halt("connection_lost", review=bool(data.get("pending")))
            self.links_were_ready = False
            return
        self.links_were_ready = True
        now = self.clock()
        for event_id in sorted(self.event_acks):
            if self._send({"session_id": self.session, "event_ack_id": event_id}):
                self.event_acks.remove(event_id)
        if now - self.last_query >= self.config.heartbeat_timeout_sec:
            self.last_query = now
            self._send({"action": "STATUS"})
        progress = order_progress(state)
        shift = self.read_shift() if self.run else None
        if self.run:
            if not progress or not shift or self.run != (progress["order_id"], progress["order_key"], shift["startedAt"]):
                self._halt("order_or_shift_ended")
            elif progress["cutting"]["cut_tapes"] >= progress["cutting"]["target_tapes"]:
                self._halt("target_reached")
            elif self.status_at is None or now - self.status_at > self.config.bridge_stale_after_sec:
                self._halt("connection_lost", review=bool(data.get("pending")))
        if (data.get("pending") and self.pending_until is not None and now >= self.pending_until
                and not (self._fresh_status() and self.status.get("cycle_busy") is True)):
            self.pending_until = None
            self._halt("cycle_unconfirmed", review=True)
        if (self.config.publish_enabled and self._fresh_status() and not self.revoke and not self.write and not data.get("pending")
                and self.status.get("permit_active") is True):
            self._halt("unknown_permit")
        write = self.write
        if write:
            self._confirm_write(write, now, data)
        if self.write is None and self.revoke and self.config.publish_enabled and now >= self.revoke_after:
            self._start_write(permit=0)
        elif (self.write is None and self.run and not self.event_acks and not data.get("review")
              and not data.get("pending") and self._ready()):
            self._start_write(permit=1, expected=self.run)

    def _confirm_write(self, write, now, data):
        after = self._fresh_status() and self.status_version > write.status_version
        expired = now - write.sent_at >= ACK_SECONDS
        if write.action == "CALIBRATE":
            if (write.ack and after and str(self.status.get("config_revision")) == write.revision
                    and all(self.status.get(key) == value for key, value in write.calibration.items())):
                self.calibration, self.write = "confirmed", None
            elif expired:
                self.calibration, self.write = "unconfirmed", None
        elif write.permit == 0:
            if write.ack and after and self.status.get("permit_active") is False:
                self.revoke, self.write = False, None
                if self._idle():
                    self._close_pending()
            elif expired:
                self.write = None
        else:
            key = data.get("pending")
            if not key:
                self.write = None
                return
            if data["permits"][key]["state"] == "started":
                return
            if write.ack and after and self.status.get("permit_active") is True:
                write.confirmed = True
            if now - write.sent_at >= PERMIT_SECONDS:
                self._halt("permit_expired")
            elif expired and not write.confirmed:
                self._halt("permit_unconfirmed", review=True)

    def _fail(self):
        self.run, self.write, self.revoke = None, None, True
        self.reason = "publish_failed"

    def tick(self):
        with self.lock:
            try:
                self._advance()
            except (GiyotinError, OSError):
                self._fail()

    def receive_mqtt(self, topic, raw, received_at, *, retained=False):
        try:
            self.handle(topic, raw, received_at, retained=retained)
        except (OSError, GiyotinError):
            LOG.exception("Giyotin telemetry could not be processed")
            with self.lock:
                self._fail()

    def control(self, action, fields):
        with self.lock:
            if action in {"giyotin-pause", "giyotin-stop"}:
                if not self.revoke:
                    self._halt("paused" if action == "giyotin-pause" else "stopped")
                    self.tick()
                return
            if action == "giyotin-reconcile":
                self._reconcile(fields)
                self.tick()
                return
            if action in {"giyotin-ping", "giyotin-status"}:
                if not self._send({"action": action.split("-")[1].upper()}):
                    raise GiyotinError("publish_failed")
                return
            self._advance()
            state = self.manager.read_state()
            data = state["cuttingWorkflow"]["protocol4"]
            if not self.config.publish_enabled or not self._transport():
                raise GiyotinError("offline")
            if data.get("review") or data.get("pending") or self.write or self.revoke or self.run:
                raise GiyotinError("blocked")
            if action == "giyotin-calibrate":
                if not self._quiet_status() or self.status.get("nano_state") not in (*READY_STATES, "CONFIG_REQUIRED"):
                    raise GiyotinError("not_ready")
                settings = {name: fields.get(name) for name in ("home_angle", "cycle_angle", "servo_speed_dps")}
                home, cycle, speed = settings.values()
                if (any(type(value) is not int for value in settings.values()) or not 0 <= home <= 180
                        or not 0 <= cycle <= 180 or home == cycle or not 5 <= speed <= 360):
                    raise GiyotinError("invalid_calibration")
                self._start_write(calibration=settings)
                self.calibration = "pending"
                return
            shift, progress = self.read_shift(), order_progress(state)
            if not shift or not progress:
                raise GiyotinError("order_or_shift_ended")
            if (fields.get("orderId"), fields.get("orderKey")) != (progress["order_id"], progress["order_key"]):
                raise GiyotinError("order_changed")
            if progress["cutting"]["legacy_blocked"] or progress["cutting"]["cut_tapes"] >= progress["cutting"]["target_tapes"]:
                raise GiyotinError("target_unavailable")
            if not self._ready():
                raise GiyotinError("not_ready")
            binding = (progress["order_id"], progress["order_key"], shift["startedAt"])
            if not self._start_write(permit=1, expected=binding):
                raise GiyotinError("order_changed")
            self.run, self.reason = binding, None

    def _reconcile(self, fields):
        outcome = fields.get("outcome")
        confirmed = fields.get("confirmed")
        if outcome not in ("completed", "no_credit") or not (confirmed is True or confirmed == "on"):
            raise GiyotinError("invalid_resolution")

        stamp = datetime.now(timezone.utc).isoformat()

        def resolve(state, data):
            review = data.get("review")
            if not review or fields.get("reviewId") != review["id"]:
                raise GiyotinError("invalid_resolution")
            permit = data.get("permits", {}).get(review.get("permit"))
            credited = outcome == "completed"
            if credited and (not permit or permit["state"] in {"done", "reconciled"}):
                raise GiyotinError("invalid_resolution")
            event_id = review.get("eventId")
            logged_id = event_id or f'mes:{review["id"]}'
            if credited:
                record_tape(state, permit)
            if permit and permit["state"] != "done":
                permit["state"] = "reconciled"
                if data.get("pending") == review["permit"]:
                    data.pop("pending")
            data.setdefault("events", {})[logged_id] = {
                **(permit or {}), "eventId": logged_id, "count": int(credited),
                "recordedAt": stamp, "resolution": outcome,
                "receivedAt": review.get("receivedAt"), "reason": review["reason"],
            }
            data.pop("review")
            for orphan in data["events"].values():
                if orphan.get("unresolved"):
                    data["review"] = {"id": uuid4().hex, "reason": orphan["reason"], "eventId": orphan["eventId"],
                                      "permit": orphan["permit"], "receivedAt": orphan["recordedAt"]}
                    break
            return event_id, True

        event_id = self.manager.edit_giyotin(resolve)
        if outcome == "completed" and self.on_production:
            self.on_production(stamp)
        if event_id:
            self.event_acks.add(event_id)
        self._halt("stopped")
        self.status_required = self.status_version + 1

    def board(self, shift):
        with self.lock:
            state = self.manager.read_state()
            data = state["cuttingWorkflow"]["protocol4"]
            progress = order_progress(state)
            order = state["workOrders"]["ordersById"].get(progress["order_id"]) if progress else None
            online = bool(self._transport())
            status = self.status if online and self._fresh_status() else {}
            pending = data.get("permits", {}).get(data.get("pending"))
            review = data.get("review")
            mode = "ready"
            if review:
                mode = "review"
            elif not online:
                mode = "offline"
            elif self.revoke:
                mode = "revoking"
            elif status.get("cycle_busy") is True or pending and pending["state"] == "started":
                mode = "running"
            elif self.write and self.write.permit == 1:
                confirmed = self.write.ack and self.status_version > self.write.status_version and status.get("permit_active") is True
                mode = "permitted" if confirmed else "awaiting_event" if self.write.confirmed else "awaiting_permit"
            elif status.get("event_pending") is True or self.run:
                mode = "awaiting_event"
            elif not self._ready():
                mode = "not_ready"
            events = sorted(data.get("events", {}).values(), key=lambda row: row["recordedAt"], reverse=True)
            cutting = progress["cutting"] if progress else {}
            return {
                "online": online, "mode": mode, "reason": self.reason, "nanoState": status.get("nano_state"),
                "nanoReady": status.get("nano_ready") is True, "buttons": [status.get("d2_pressed"), status.get("d3_pressed")],
                "order": {"id": progress["order_id"], "key": progress["order_key"],
                          "name": order.get("stockName") or "", "completed": cutting["cut_tapes"],
                          "stationOrderId": (cutting.get("station_order") or {}).get("station_order_id", ""),
                          "target": cutting["target_tapes"]} if order else None,
                "canStart": bool(shift and mode == "ready" and cutting and not self.write and not pending
                                 and not cutting["legacy_blocked"] and cutting["cut_tapes"] < cutting["target_tapes"]
                                 and self.config.publish_enabled),
                "canStop": bool(self.run or pending or self.write and self.write.permit == 1),
                "review": {**review, "canCredit": bool(data.get("permits", {}).get(review.get("permit"), {}).get("state")
                                                      in {"issued", "started", "closed"})} if review else None,
                "calibration": self.calibration, "rejection": self.rejection, "pongAt": self.pong_at, "events": events[:12],
            }

    def production_records(self):
        data = self.manager.read_state()["cuttingWorkflow"]["protocol4"]
        return [{**row, "result": None} for row in data.get("events", {}).values() if row["count"]]
