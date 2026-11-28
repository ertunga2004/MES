"""Run an optional loopback-only MQTT broker for the simulation."""

import asyncio
from pathlib import Path

from .anylogic_mqtt import SimMqttConfig


async def serve():
    from amqtt.broker import Broker

    config = SimMqttConfig.from_env(Path(__file__).resolve().parent.parent)
    broker = Broker({
        'listeners': {'default': {'type': 'tcp', 'bind': f'127.0.0.1:{config.port}'}},
        'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True}},
    })
    await broker.start()
    try:
        await asyncio.Future()
    finally:
        await broker.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
