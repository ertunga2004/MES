"""Local AnyLogic gateway. MQTT is the only path from the MES to the gateway."""

import argparse
import json
import logging
import os
import signal
from collections import OrderedDict
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event
from time import monotonic, sleep, time
from uuid import UUID, uuid4

from .anylogic_mqtt import COMMAND_LIFETIME, SimMqttConfig, SimMqttPeer, identifier
from .anylogic_runner import AnyLogicRunner, FRAME_FIELDS, SCENARIOS, SimulationError, frame_metrics, read_json


log = logging.getLogger(__name__)
ACTIVE = {'running', 'paused'}
ACTIONS = {'start', 'pause', 'resume', 'speed', 'stop', 'reset'}


def acquire_lease(path):
    """Hold the same one-byte lock as the desktop Java worker."""
    file = path.open('a+b')
    try:
        file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.lockf(file, fcntl.LOCK_EX | fcntl.LOCK_NB, 1)
    except OSError:
        file.close()
        return None
    return file


class AnyLogicGateway:
    def __init__(self, workspace):
        self.config = SimMqttConfig.from_env(workspace)
        self.directory = self.config.directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.runner = AnyLogicRunner(workspace, self.directory / 'state.json', installation=self.directory / 'runtime')
        self.commands = Queue(maxsize=16)
        self.peer = SimMqttPeer(self.config, ('command',), self._enqueue)
        self.id = uuid4().hex
        self.sequence = 0
        self.acks = OrderedDict()
        self.lease = None
        self.last = None
        self.dismissed_desktop = None
        self.desktop_run = None
        self.desktop_frame = {}
        self.desktop_version = None

    def _enqueue(self, _topic, packet):
        if packet.get('bridgeId') != self.id or not identifier(packet.get('requestId')):
            return
        try:
            self.commands.put_nowait(packet)
        except Full:
            self._ack(packet['requestId'], ok=False, code=503, detail='AnyLogic komut kuyruğu dolu.')

    def _ack(self, request_id, **result):
        self.peer.publish('ack', {'bridgeId': self.id, 'requestId': request_id, **result})

    def _desktop_status(self):
        path = self.directory / 'desktop.json'
        try:
            if time() - path.stat().st_mtime > 3:
                return {}
        except OSError:
            return {}
        status = read_json(path)
        run_id = status.get('id')
        if not identifier(run_id) or run_id == self.dismissed_desktop:
            return {}
        return status

    def _desktop_packet(self, status):
        run_id = status['id']
        folder = self.runner.runs / run_id
        path = folder / 'live' / 'live-state.json'
        if self.desktop_run != run_id:
            self.desktop_run = run_id
            self.desktop_frame = {}
            self.desktop_version = None
        try:
            stat = path.stat()
            version = (stat.st_mtime_ns, stat.st_ino, stat.st_size)
        except OSError:
            version = None
        if version is not None and version != self.desktop_version:
            frame = read_json(path)
            if (frame.get('schemaVersion') == 1 and frame.get('type') == 'anylogic-state'
                    and frame.get('runId') == status.get('engineRunId')
                    and frame.get('seq', 0) >= self.desktop_frame.get('seq', 0)):
                self.desktop_frame = frame
                self.desktop_version = version
        live = self.desktop_frame
        run = {'id': run_id, 'mode': live.get('productionMode'), 'scenario': live.get('scenario'),
               'startedAt': status.get('startedAt'), 'origin': 'desktop'}
        if run['scenario'] in SCENARIOS and run['mode'] in {'TEST', 'SUREKLI'} and not (folder / 'run.json').is_file():
            (folder / 'run.json').write_text(json.dumps(run), encoding='utf-8')
        if not run['scenario']:
            run['scenario'] = '—'
        state = status.get('state')
        snapshot = {'run': run, 'state': state, 'speed': status.get('speed'), 'modelTime': live.get('simTime'),
                    'target': status.get('target'), 'verdict': status.get('verdict'), 'metrics': frame_metrics(live),
                    'available': True, 'engineConnected': state not in {'stopped', 'error'},
                    'has_report': self.runner.report(UUID(run_id)) is not None}
        frame = {key: live[key] for key in FRAME_FIELDS + ('events',) if key in live}
        return snapshot, frame or None

    def _ready(self):
        return {**self.runner.status(), 'engineConnected': False}, None

    def _release(self):
        if self.lease is not None:
            self.lease.close()
            self.lease = None

    def packet(self):
        if self.lease is not None:
            state = self.runner.status()
            if not self.runner.active:
                self._release()
                previous, frame = self.last or (state, None)
                self.last = {**previous, 'state': 'stopped', 'engineConnected': False, 'detail': state.get('detail')}, frame
                return self.last
            state['run'] = {**state['run'], 'origin': 'mes'}
            self.last = {**state, 'engineConnected': True}, self.runner.frame(include_events=True)['frame']
            return self.last
        desktop = self._desktop_status()
        if desktop:
            self.last = self._desktop_packet(desktop)
        elif self.last and self.last[0]['engineConnected']:
            state, frame = self.last
            self.last = {**state, 'state': 'stopped', 'engineConnected': False,
                         'detail': 'Masaüstü AnyLogic bağlantısı kesildi.'}, frame
        return self.last or self._ready()

    def _validate(self, command):
        action = command.get('action')
        mode = command.get('mode')
        scenario = command.get('scenario')
        speed = command.get('speed')
        issued = command.get('issuedAt')
        if type(issued) not in (int, float) or not -3 <= time() - issued <= COMMAND_LIFETIME:
            raise SimulationError('MQTT komutunun süresi doldu.', 408)
        if not isinstance(action, str) or action not in ACTIONS or mode not in ('TEST', 'SUREKLI') or scenario not in SCENARIOS:
            raise SimulationError('Geçersiz AnyLogic komutu.', 422)
        if (speed is not None and (type(speed) is not int or speed not in (1, 2, 5, 10))) or (action == 'speed' and speed is None):
            raise SimulationError('Geçersiz simülasyon hızı.', 422)
        return action, mode, scenario, speed

    def _desktop_command(self, action, command, run, speed):
        path = self.runner.runs / run['id'] / 'command.txt'
        request_id = command['requestId']
        temp = path.with_name(f'{request_id}.tmp')
        temp.write_text(f"{request_id}\n{action}\n{speed or 1}\n{int(time() * 1000) + 3500}\n", encoding='utf-8')
        try:
            for _ in range(6):
                try:
                    temp.replace(path)
                    break
                except PermissionError:
                    sleep(.04)
            else:
                raise SimulationError('Masaüstü komutu kaydedilemedi.', 502)
        finally:
            temp.unlink(missing_ok=True)
        end = monotonic() + 4
        while monotonic() < end:
            status = self._desktop_status()
            if status.get('id') == run['id'] and status.get('requestId') == request_id:
                if status.get('ok') is not True:
                    raise SimulationError('Masaüstü AnyLogic komutu mevcut durumda uygulayamadı.', 409)
                self.last = self._desktop_packet(status)
                if action == 'reset':
                    self.dismissed_desktop = run['id']
                    self.last = None
                return self.packet()[0]
            sleep(.08)
        raise SimulationError('Masaüstü AnyLogic komutu onaylamadı.', 504)

    def _apply(self, command):
        action, mode, scenario, speed = self._validate(command)
        current, frame = self.packet()
        run = current.get('run')
        if action == 'start':
            if current['engineConnected']:
                raise SimulationError('AnyLogic koşusu zaten açık. Aynı koşuyu kullanın.', 409)
            self.lease = acquire_lease(self.directory / 'engine.lock')
            if not self.lease:
                raise SimulationError('AnyLogic masaüstü veya MES koşusu zaten başlıyor.', 409)
            desktop = self._desktop_status()
            if desktop:
                self.dismissed_desktop = desktop['id']
            try:
                self.runner.command(action, run_id=None, mode=mode, scenario=scenario, speed=speed)
            except Exception:
                self._release()
                raise
        elif not run or run['id'] != command.get('runId'):
            raise SimulationError('Koşu değişti. Ekranı güncelleyin.', 409)
        elif action == 'reset' and current['state'] == 'stopped':
            if run.get('origin') == 'desktop':
                self.dismissed_desktop = run['id']
            self.last = None
        elif self.lease is not None:
            result = self.runner.command(action, run_id=run['id'], mode=mode, scenario=scenario, speed=speed)
            if action in {'stop', 'reset'}:
                self._release()
                self.last = ({**result, 'run': run, 'engineConnected': False}, frame) if action == 'stop' else None
        elif run.get('origin') == 'desktop' and current['engineConnected']:
            return self._desktop_command(action, command, run, speed)
        else:
            raise SimulationError('Komut için bağlı bir AnyLogic koşusu gerekli.', 409)
        return self.packet()[0]

    def _handle(self, command):
        request_id = command['requestId']
        if request_id not in self.acks:
            try:
                result = {'ok': True, 'status': self._apply(command)}
            except SimulationError as exc:
                result = {'ok': False, 'code': exc.status, 'detail': str(exc)}
            except (OSError, ValueError) as exc:
                log.exception('AnyLogic yerel komut hatası')
                result = {'ok': False, 'code': 502, 'detail': str(exc)}
            self.acks[request_id] = result
            if len(self.acks) > 256:
                self.acks.popitem(last=False)
            self._publish()
        self._ack(request_id, **self.acks[request_id])

    def _publish(self):
        if self.peer.connected:
            status, frame = self.packet()
            self.sequence += 1
            self.peer.publish('telemetry', {'bridgeId': self.id, 'seq': self.sequence, 'status': status, 'frame': frame})

    def run(self, stopped):
        exclusive = acquire_lease(self.directory / 'gateway.lock')
        if not exclusive:
            raise RuntimeError('Bu çalışma alanında AnyLogic MQTT köprüsü zaten açık.')
        try:
            self.peer.start()
            while not stopped.is_set():
                try:
                    self._handle(self.commands.get(timeout=.20))
                except Empty:
                    self._publish()
        finally:
            self.peer.close()
            self.runner.close()
            self._release()
            exclusive.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stopped = Event()
    for name in ('SIGINT', 'SIGTERM'):
        signal.signal(getattr(signal, name), lambda *_args: stopped.set())
    AnyLogicGateway(Path(__file__).resolve().parent.parent).run(stopped)


if __name__ == '__main__':
    main()
