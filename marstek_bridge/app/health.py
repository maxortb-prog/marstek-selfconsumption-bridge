"""HTTP-Health-Endpoint fuer den Supervisor-Watchdog.

Der Supervisor-Watchdog (``watchdog:`` in config.yaml) prueft eine URL des
Add-ons. Antwortet sie nicht mit HTTP 200, startet der Supervisor das Add-on
neu. Genau das nutzen wir als "Watchdog = true" Funktion:

* ``/health``  -> 200 solange MQTT verbunden UND die Geraetekommunikation ok
                  ist; sonst 503.
* ``/status``  -> immer 200, liefert den Detailstatus als JSON (fuer Menschen).
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_LOGGER = logging.getLogger("marstek.health")


class HealthState:
    """Threadsicherer Zustandscontainer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, object] = {
            "mqtt_connected": False,
            "device_ok": False,
            "initialized": False,
            "watchdog_failures": 0,
            "last_error": None,
            "last_success": None,
        }

    def update(self, **kwargs: object) -> None:
        with self._lock:
            self._state.update(kwargs)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return dict(self._state)

    @property
    def healthy(self) -> bool:
        with self._lock:
            return bool(self._state["mqtt_connected"]) and bool(
                self._state["device_ok"]
            )


class _Handler(BaseHTTPRequestHandler):
    state: HealthState

    def _respond(self, code: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - Vorgabe der Basisklasse
        snap = self.state.snapshot()
        if self.path.rstrip("/") in ("", "/status"):
            self._respond(200, snap)
            return
        if self.path.rstrip("/") == "/health":
            healthy = self.state.healthy
            self._respond(200 if healthy else 503, {"healthy": healthy, **snap})
            return
        self._respond(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:  # pragma: no cover
        _LOGGER.trace("health %s", fmt % args)  # type: ignore[attr-defined]


class HealthServer:
    def __init__(self, port: int, state: HealthState) -> None:
        self._port = port
        self._state = state
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = type("BoundHandler", (_Handler,), {"state": self._state})
        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", self._port), handler)
        except OSError as err:  # pragma: no cover - defensiv
            _LOGGER.error("Health-Server konnte nicht starten: %s", err)
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="health", daemon=True
        )
        self._thread.start()
        _LOGGER.info("Health-Endpoint laeuft auf Port %s (/health, /status)", self._port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
