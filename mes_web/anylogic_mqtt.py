"""MQTT transport for simulation telemetry and operator commands."""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import RLock
from time import monotonic, time
from uuid import uuid4

from .anylogic_runner import AnyLogicRunner, SimulationError


log = logging.getLogger(__name__)
COMMAND_LIFETIME = 25
HEARTBEAT_TIMEOUT = 4
IDENTIFIER = re.compile(r'[a-f0-9]{32}')


@dataclass(frozen=True)
class SimMqttConfig:
    host: str
    port: int
    root: str
    directory: Path

    @classmethod
    def from_env(cls, workspace):
        host = os.getenv('MES_ANYLOGIC_MQTT_HOST', '127.0.0.1')
        port = int(os.getenv('MES_ANYLOGIC_MQTT_PORT', '18883'))
        root = os.getenv('MES_ANYLOGIC_MQTT_TOPIC', 'at-zeze/anylogic/v1')
        if host not in {'127.0.0.1', 'localhost'} or not 1 <= port <= 65535:
            raise ValueError('AnyLogic MQTT için yerel broker adresi ve geçerli bir port kullanın.')
        if not re.fullmatch(r'at-zeze/anylogic/[A-Za-z0-9_-]+', root):
            raise ValueError('AnyLogic MQTT konu kökü at-zeze/anylogic/ ile başlamalı.')
        return cls(host, port, root, (workspace / '.local' / 'anylogic-mqtt').resolve())

    def topic(self, name):
        return f'{self.root}/{name}'


def mqtt_anylogic_enabled():
    return os.getenv('MES_ANYLOGIC_MQTT_ENABLED') == '1'


def identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


class SimMqttPeer:
    def __init__(self, config, topics, receive, disconnected=lambda: None):
        self.config = config
        self.topics = topics
        self.receive = receive
        self.disconnected = disconnected
        self.connected = False
        self.client = None

    def start(self):
        import paho.mqtt.client as mqtt

        options = {'client_id': f'mes-sim-{uuid4().hex[:16]}'}
        if hasattr(mqtt, 'CallbackAPIVersion'):
            options['callback_api_version'] = mqtt.CallbackAPIVersion.VERSION2
        self.client = mqtt.Client(**options)
        self.client.max_queued_messages_set(32)
        self.client.reconnect_delay_set(1, 8)
        self.client.on_connect = self._connect
        self.client.on_disconnect = self._disconnect
        self.client.on_message = self._message
        self.client.connect_async(self.config.host, self.config.port, keepalive=10)
        self.client.loop_start()

    def close(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
            self.client = None
        self.connected = False

    def _connect(self, client, userdata, flags, reason, properties=None):
        self.connected = getattr(reason, 'value', reason) == 0
        if self.connected:
            client.subscribe([(self.config.topic(name), 0 if name == 'telemetry' else 1) for name in self.topics])

    def _disconnect(self, *_args):
        self.connected = False
        self.disconnected()

    def _message(self, client, userdata, message):
        if message.retain or len(message.payload) > 1_048_576:
            return
        try:
            packet = json.loads(message.payload)
            topic = message.topic.removeprefix(f'{self.config.root}/')
            if isinstance(packet, dict) and packet.get('schema') == 1 and topic in self.topics:
                self.receive(topic, packet)
        except (UnicodeError, ValueError, TypeError) as exc:
            log.debug('AnyLogic MQTT mesajı atlandı: %s', exc)

    def publish(self, name, packet):
        if not self.connected or not self.client:
            return False
        try:
            payload = json.dumps({'schema': 1, **packet}, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            log.warning('Geçersiz AnyLogic MQTT verisi atlandı.')
            return False
        event = self.client.publish(self.config.topic(name), payload,
                                    qos=0 if name == 'telemetry' else 1, retain=False)
        return event.rc == 0


class AnyLogicMqttClient:
    """MES-side proxy. Simulation messages never enter the physical MQTT ingest."""

    def __init__(self, workspace):
        self.config = SimMqttConfig.from_env(workspace)
        self.reports = AnyLogicRunner(workspace, self.config.directory / 'state.json')
        self.peer = SimMqttPeer(self.config, ('telemetry', 'ack'), self._receive, self._disconnected)
        self.lock = RLock()
        self.packet = {}
        self.last_packet = 0
        self.last_frame_key = None
        self.last_data_at = None
        self.waiting = {}

    def start(self):
        self.peer.start()

    def close(self):
        self.peer.close()

    def _disconnected(self):
        with self.lock:
            self.last_packet = 0

    def _receive(self, topic, packet):
        bridge = packet.get('bridgeId')
        if not identifier(bridge):
            return
        with self.lock:
            if topic == 'ack':
                request_id = packet.get('requestId')
                if not identifier(request_id):
                    return
                pending = self.waiting.get(request_id)
                if pending and bridge == pending[0] and pending[1].empty():
                    pending[1].put_nowait(packet)
                return
            sequence = packet.get('seq')
            status = packet.get('status')
            frame = packet.get('frame')
            if not isinstance(sequence, int) or sequence < 1 or not isinstance(status, dict):
                return
            run = status.get('run')
            if run is not None and (not isinstance(run, dict) or not identifier(run.get('id'))):
                return
            if frame is not None and (run is None or not isinstance(frame, dict) or not isinstance(frame.get('seq'), int)):
                return
            if bridge == self.packet.get('bridgeId') and sequence <= self.packet['seq']:
                return
            key = (bridge, run['id'], frame['seq']) if frame else None
            if key != self.last_frame_key:
                self.last_frame_key = key
                self.last_data_at = datetime.now(timezone.utc).isoformat() if key else None
            self.packet = packet
            self.last_packet = monotonic()

    def status(self):
        with self.lock:
            online = self.peer.connected and monotonic() - self.last_packet <= HEARTBEAT_TIMEOUT and bool(self.packet)
            connection = {'transport': 'mqtt', 'mqttConnected': self.peer.connected, 'bridgeConnected': online,
                          'lastDataAt': self.last_data_at}
            if not online:
                detail = 'Simülasyon MQTT bağlantısı bekleniyor.' if not self.peer.connected else 'AnyLogic köprüsünden veri alınamıyor.'
                return {'available': False, 'state': 'unavailable', 'run': None, 'speed': None, 'detail': detail, **connection}
            return {**self.packet['status'], **connection}

    def frame(self):
        with self.lock:
            status = self.status()
            connected = status['bridgeConnected']
            return {key: status.get(key) for key in ('run', 'state', 'speed', 'detail', 'transport', 'mqttConnected',
                    'bridgeConnected', 'engineConnected', 'lastDataAt')} | {'frame': self.packet.get('frame') if connected else None}

    def command(self, action, *, run_id, mode, scenario, speed=None):
        with self.lock:
            if not self.status()['bridgeConnected']:
                raise SimulationError('AnyLogic MQTT köprüsü bağlı değil.')
            bridge = self.packet['bridgeId']
            request_id = uuid4().hex
            response = Queue(maxsize=1)
            self.waiting[request_id] = (bridge, response)
        try:
            command = {'bridgeId': bridge, 'requestId': request_id, 'issuedAt': time(), 'action': action,
                       'runId': run_id, 'mode': mode, 'scenario': scenario, 'speed': speed}
            if not self.peer.publish('command', command):
                raise SimulationError('Simülasyon MQTT komutu gönderilemedi.')
            try:
                ack = response.get(timeout=COMMAND_LIFETIME + 3)
            except Empty:
                raise SimulationError('AnyLogic komutu doğrulanamadı. Tekrar denemeden önce koşu durumunu kontrol edin.', 504) from None
            if ack.get('ok') is not True:
                raise SimulationError(str(ack.get('detail') or 'AnyLogic komutu uygulanamadı.'), ack.get('code', 502))
            return {**self.status(), **ack['status']}
        finally:
            with self.lock:
                self.waiting.pop(request_id, None)

    def report(self, run_id):
        return self.reports.report(run_id)
