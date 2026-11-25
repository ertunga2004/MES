"""Run the main MES and the station ports with one application lifecycle."""

from contextlib import ExitStack
import socket

import uvicorn

from .station_access import STATION_PORTS


def run_station_ports(app, host: str, main_port: int, *, lifespan: str = 'auto', log_level: str = 'info'):
    if main_port in STATION_PORTS.values():
        raise ValueError('MES ana paneli istasyon portlarından ayrı olmalı.')
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with ExitStack() as resources:
        listeners = []
        for port in (main_port, *STATION_PORTS.values()):
            try:
                listener = resources.enter_context(socket.create_server((host, port), family=family))
            except OSError as error:
                raise OSError(f'MES {host}:{port} adresini açamadı: {error}') from error
            listeners.append(listener)
        config = uvicorn.Config(app, host=host, port=main_port, lifespan=lifespan, log_level=log_level)
        uvicorn.Server(config).run(sockets=listeners)
