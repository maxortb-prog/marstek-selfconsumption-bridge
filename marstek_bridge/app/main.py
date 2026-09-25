"""Einstiegspunkt des Add-ons."""

from __future__ import annotations

import signal
import sys
from types import FrameType

from .bridge import Bridge
from .health import HealthServer, HealthState
from .logging_setup import setup_logging
from .settings import load_settings


def main() -> int:
    settings = load_settings()
    log = setup_logging(settings.log_level, settings.log_full_line_color)
    log.debug("Log-Level: %s", settings.log_level)

    health = HealthState()
    server = HealthServer(settings.health_port, health)
    server.start()

    bridge = Bridge(settings, health)

    def _handle_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("Signal %s empfangen", signal.Signals(signum).name)
        bridge.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        bridge.run()
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
