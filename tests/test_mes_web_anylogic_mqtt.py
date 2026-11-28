from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from mes_web.anylogic_gateway import AnyLogicGateway
from mes_web.anylogic_mqtt import AnyLogicMqttClient
from mes_web.anylogic_runner import SimulationError


class AnyLogicMqttTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)

    def test_packets_cannot_roll_back_frame_or_report_data_after_disconnect(self):
        client = AnyLogicMqttClient(self.workspace)
        client.peer.connected = True
        run = {'id': uuid4().hex}
        status = {'available': True, 'state': 'running', 'run': run}
        bridge = uuid4().hex
        client._receive('telemetry', {'bridgeId': bridge, 'seq': 3, 'status': status, 'frame': {'seq': 9}})
        client._receive('telemetry', {'bridgeId': bridge, 'seq': 2, 'status': status, 'frame': {'seq': 8}})
        self.assertEqual(client.frame()['frame'], {'seq': 9})
        self.assertIsNotNone(client.status()['lastDataAt'])
        client._disconnected()
        self.assertFalse(client.status()['bridgeConnected'])
        self.assertIsNone(client.frame()['frame'])

    def test_duplicate_command_republishes_ack_without_repeating_operation(self):
        gateway = AnyLogicGateway(self.workspace)
        request_id = uuid4().hex
        command = {'requestId': request_id}
        with (
            patch.object(gateway, '_apply', return_value={'state': 'running'}) as apply,
            patch.object(gateway, '_ack') as ack,
        ):
            gateway._handle(command)
            gateway._handle(command)
        apply.assert_called_once_with(command)
        self.assertEqual(ack.call_count, 2)
        self.assertEqual(ack.call_args_list[0], ack.call_args_list[1])

    def test_expired_and_invalid_commands_are_rejected(self):
        gateway = AnyLogicGateway(self.workspace)
        command = {'action': 'start', 'mode': 'TEST', 'scenario': 'T07', 'speed': 2, 'issuedAt': time() - 90}
        with self.assertRaises(SimulationError) as expired:
            gateway._validate(command)
        self.assertEqual(expired.exception.status, 408)
        with self.assertRaises(SimulationError) as invalid:
            gateway._validate({**command, 'issuedAt': time(), 'speed': True})
        self.assertEqual(invalid.exception.status, 422)
