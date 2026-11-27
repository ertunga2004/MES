"""Run the workshop's isolated AnyLogic export over a private process pipe."""

import atexit
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from subprocess import PIPE, STDOUT, Popen, TimeoutExpired
from threading import RLock, Thread
from uuid import UUID, uuid4

from .prepare_anylogic import EXPORT_NAME, WORKBOOK


SCENARIOS = tuple(f'T{index:02d}' for index in range(1, 15))


class SimulationError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class AnyLogicRunner:
    def __init__(self, workspace, state_path):
        self.local = (workspace / '.local' / 'anylogic').resolve()
        self.runs = state_path.resolve().parent / 'anylogic-runs'
        self.runtime = self.local / 'export' / EXPORT_NAME
        self.process = None
        self.active = None
        self.lock = RLock()
        self.replies = None
        self.last_report = None
        self._read_previous_runs = False

    def _installation(self):
        info = read_json(self.local / 'manifest.json')
        executable = Path(info.get('java') or '')
        if (info.get('schema') != 1 or not executable.is_file() or
                not all(path.is_file() for path in (self.local / 'MesEngineBridge.class', self.runtime / 'model.jar', self.local / 'model' / WORKBOOK))):
            return None
        return info

    def _read_process(self, process, replies, log_path):
        try:
            with log_path.open('a', encoding='utf-8') as log:
                for line in process.stdout:
                    if line.startswith('@MES@'):
                        replies.put(json.loads(line.removeprefix('@MES@')))
                    else:
                        log.write(line)
                log.flush()
        except (OSError, ValueError):
            pass
        finally:
            replies.put({'error': 'Motor süreci sona erdi.'})

    def _exchange(self, action, timeout=8):
        try:
            self.process.stdin.write(json.dumps({'action': action}) + '\n')
            self.process.stdin.flush()
            response = self.replies.get(timeout=timeout)
        except (Empty, OSError) as exc:
            self.close()
            raise SimulationError('AnyLogic motoru yanıt vermedi.', 504) from exc
        if response.get('error'):
            self.close()
            raise SimulationError('AnyLogic motoru komutu tamamlayamadı. Koşunun motor günlüğüne bakın.', 502)
        if response.get('state') == 'error':
            self.close()
            raise SimulationError('AnyLogic modeli yürütme sırasında durdu. Koşunun motor günlüğüne bakın.', 502)
        return response

    def _snapshot(self, response):
        active = self.active
        folder = self.runs / active['id']
        live = read_json(folder / 'live' / 'live-state.json')
        if live.get('schemaVersion') != 1 or live.get('runId') != response.get('engineRunId') or not response.get('engineRunId'):
            live = {}
        metrics = {key: live[key] for key in ('simTime', 'counters', 'inventory', 'conveyor', 'camera', 'robot', 'stations') if key in live}
        if 'counters' in metrics and isinstance(live.get('products'), list):
            metrics['counters']['onConveyor'] = sum(row.get('phase') in {'belt', 'robot'} for row in live['products'])
        metrics['events'] = live.get('events', [])[-12:]
        has_report = self._report_file(folder, active).is_file()
        if has_report:
            self.last_report = active['id']
        return {'available': True, 'state': response['state'], 'run': active, 'modelTime': response.get('modelTime'),
                'target': response.get('target') or None, 'verdict': response.get('verdict'), 'metrics': metrics,
                'has_report': has_report}

    @staticmethod
    def _report_file(folder, run):
        suffix = 'AKIS' if run.get('mode') == 'SUREKLI' else run.get('scenario')
        return folder / f'sonuc_{suffix}.csv'

    def status(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                try:
                    return self._snapshot(self._exchange('status'))
                except SimulationError as exc:
                    return {'available': True, 'state': 'error', 'detail': str(exc)}
            if self.process is not None:
                self.close()
                return {'available': True, 'state': 'error', 'detail': 'AnyLogic süreci kapandı.'}
            available = self._installation() is not None
            if not self._read_previous_runs:
                self._read_previous_runs = True
                self.last_report = self.last_report or self._find_last_report()
            return {'available': available, 'state': 'ready' if available else 'unavailable', 'run': None,
                    'lastReport': self.last_report,
                    'detail': None if available else 'Yerel AnyLogic dışa aktarımı veya Java köprüsü bulunamadı.'}

    def command(self, action, *, run_id, mode, scenario):
        with self.lock:
            if action == 'start':
                return self._start(mode, scenario)
            if not self.active or self.active['id'] != run_id:
                raise SimulationError('Koşu değişti. Ekranı güncelleyin.', 409)
            current = self._exchange('status')
            if action == 'reset':
                self.close()
                return self.status()
            expected = {'pause': ('running', 'paused'), 'resume': ('paused', 'running')}[action]
            if current['state'] != expected[0]:
                raise SimulationError('Bu komut mevcut koşu durumunda kullanılamıyor.', 409)
            response = self._exchange(action)
            if response['state'] not in {expected[1], 'completed'}:
                raise SimulationError('Motorun yeni durumu doğrulanamadı.', 502)
            return self._snapshot(response)

    def _start(self, mode, scenario):
        if mode not in {'TEST', 'SUREKLI'} or scenario not in SCENARIOS:
            raise SimulationError('Geçerli bir çalışma modu ve Excel senaryosu seçin.', 422)
        if self.process is not None and self.process.poll() is None:
            raise SimulationError('Yeni koşu için açık koşuyu sıfırlayın.', 409)
        self.close()
        installation = self._installation()
        if not installation:
            raise SimulationError('Yerel AnyLogic modeli hazır değil.')
        run = {'id': uuid4().hex, 'mode': mode, 'scenario': scenario,
               'startedAt': datetime.now(timezone.utc).isoformat(), 'modelSha256': installation.get('model_sha256')}
        folder = self.runs / run['id']
        classpath = os.pathsep.join(str(path) for path in (self.local, self.runtime / 'model.jar', self.runtime / 'lib' / '*'))
        try:
            folder.mkdir(parents=True)
            (folder / 'run.json').write_text(json.dumps(run), encoding='utf-8')
            (folder / 'senaryo.txt').write_text(scenario, encoding='utf-8')
            (folder / 'uretim_modu.txt').write_text(mode, encoding='utf-8')
            self.process = Popen([installation['java'], '-Djava.awt.headless=true', '-Dfile.encoding=UTF-8', '-Xmx512m',
                                  f'-Dmes.anylogic.modelDir={self.local / "model"}', f'-Dmes.anylogic.runDir={folder}',
                                  '-cp', classpath, 'MesEngineBridge'], cwd=folder, stdin=PIPE, stdout=PIPE, stderr=STDOUT,
                                 encoding='utf-8', errors='replace', text=True, bufsize=1,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError as exc:
            raise SimulationError('AnyLogic çalışma dosyaları veya Java süreci açılamadı.') from exc
        self.active = run
        self.replies = Queue()
        atexit.register(self.close)
        Thread(target=self._read_process, args=(self.process, self.replies, folder / 'engine.log'), daemon=True).start()
        if self._exchange('status', timeout=25)['state'] != 'ready':
            self.close()
            raise SimulationError('Model başlangıç durumu doğrulanamadı.', 502)
        response = self._exchange('start')
        if response['state'] not in {'running', 'completed'}:
            self.close()
            raise SimulationError('Model başlatılamadı.', 502)
        return self._snapshot(response)

    def report(self, run_id):
        folder = self.runs / run_id.hex
        run = read_json(folder / 'run.json')
        if run.get('id') != run_id.hex or run.get('scenario') not in SCENARIOS:
            return None
        report = self._report_file(folder, run)
        return report if report.is_file() else None

    def _find_last_report(self):
        candidates = []
        for path in self.runs.glob('*/run.json'):
            try:
                identifier = UUID(path.parent.name)
            except ValueError:
                continue
            run = read_json(path)
            if self.report(identifier):
                candidates.append((str(run.get('startedAt') or ''), identifier.hex))
        return max(candidates)[1] if candidates else None

    def close(self):
        with self.lock:
            process = self.process
            if process is None:
                return
            self.process = None
            self.active = None
            atexit.unregister(self.close)
            try:
                if process.poll() is None:
                    process.stdin.close()
                    process.wait(timeout=4)
            except (TimeoutExpired, OSError):
                process.kill()
                process.wait(timeout=4)
            finally:
                process.stdin.close()
                process.stdout.close()
