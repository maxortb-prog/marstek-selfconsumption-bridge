"""UDP-Client fuer die Marstek Device Open API (JSON ueber UDP)."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any

from .const import INSTANCE_IDS, MSG_ID_MAX, MSG_ID_MIN

_LOGGER = logging.getLogger("marstek.udp")


class UdpError(Exception):
    """Basisfehler der UDP-Kommunikation."""

    def __init__(self, message: str, *, trigger_watchdog: bool = False) -> None:
        super().__init__(message)
        self.trigger_watchdog = trigger_watchdog


class UdpTimeout(UdpError):
    """Keine (gueltige) Antwort innerhalb des Zeitfensters."""


class ApiError(UdpError):
    """Das Geraet hat eine JSON-RPC Fehlerantwort geliefert."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"API-Fehler {code}: {message} (data={data})")
        self.code = code
        self.message = message
        self.data = data


class MarstekUdpClient:
    """Serialisierter Request/Response-Client.

    * Jede gesendete Nachricht bekommt eine eigene, laufende ID (0..999).
    * Jede Methode verwendet ihre eigene Instance-ID (``params.id``).
    * ``retries == 0``  -> genau ein Versuch, Timeout wird verworfen,
      der Watchdog wird NICHT ausgeloest.
    * ``retries > 0``   -> Wiederholungen; scheitern alle bzw. laeuft das
      maximale Zeitfenster ab, wird der Watchdog ausgeloest.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        local_port: int = 0,
        timeout: float = 1.0,
        retries: int = 2,
        max_time: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.local_port = local_port
        self.timeout = timeout
        self.retries = retries
        self.max_time = max_time

        self._lock = threading.Lock()
        self._msg_id = MSG_ID_MIN - 1
        self._sock: socket.socket | None = None

    # ------------------------------------------------------------------
    def _ensure_socket(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", self.local_port))
        sock.settimeout(self.timeout)
        self._sock = sock
        _LOGGER.debug("UDP-Socket gebunden auf 0.0.0.0:%s", sock.getsockname()[1])
        return sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # ------------------------------------------------------------------
    def next_msg_id(self) -> int:
        with self._lock:
            self._msg_id += 1
            if self._msg_id > MSG_ID_MAX:
                self._msg_id = MSG_ID_MIN
            return self._msg_id

    @staticmethod
    def instance_id(method: str) -> int:
        return INSTANCE_IDS.get(method, 0)

    # ------------------------------------------------------------------
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        target: tuple[str, int] | None = None,
        with_instance: bool = True,
    ) -> dict[str, Any]:
        """Eine Anfrage senden und das ``result``-Objekt zurueckliefern."""
        payload_params: dict[str, Any] = {}
        if with_instance:
            payload_params["id"] = self.instance_id(method)
        if params:
            payload_params.update(params)

        addr = target or (self.host, self.port)
        attempts = 1 + max(0, self.retries)
        started = time.monotonic()
        last_error: UdpError | None = None

        with self._lock_free_request():
            for attempt in range(1, attempts + 1):
                if time.monotonic() - started > self.max_time:
                    raise UdpTimeout(
                        f"{method}: maximales Zeitfenster von {self.max_time}s "
                        f"ueberschritten",
                        trigger_watchdog=True,
                    )
                msg_id = self.next_msg_id()
                message = {"id": msg_id, "method": method, "params": payload_params}
                try:
                    return self._exchange(message, addr, method, attempt, attempts)
                except ApiError:
                    raise
                except UdpError as err:
                    last_error = err
                    _LOGGER.warning(
                        "%s Versuch %s/%s fehlgeschlagen: %s",
                        method,
                        attempt,
                        attempts,
                        err,
                    )

        trigger = self.retries > 0
        raise UdpTimeout(
            f"{method}: keine Antwort nach {attempts} Versuch(en)"
            f"{'' if last_error is None else f' ({last_error})'}",
            trigger_watchdog=trigger,
        )

    # ------------------------------------------------------------------
    def _lock_free_request(self):
        """Serialisiert die Requests (das Geraet mag keine Parallelitaet)."""
        return _RequestGuard(self._request_lock)

    _request_lock = threading.Lock()

    # ------------------------------------------------------------------
    def _exchange(
        self,
        message: dict[str, Any],
        addr: tuple[str, int],
        method: str,
        attempt: int,
        attempts: int,
    ) -> dict[str, Any]:
        sock = self._ensure_socket()
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        _LOGGER.trace("TX %s:%s %s", addr[0], addr[1], raw.decode("utf-8"))  # type: ignore[attr-defined]
        try:
            sock.sendto(raw, addr)
        except OSError as err:
            raise UdpError(f"Senden fehlgeschlagen: {err}") from err

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UdpTimeout(
                    f"Timeout nach {self.timeout}s (id={message['id']})"
                )
            sock.settimeout(remaining)
            try:
                data, sender = sock.recvfrom(8192)
            except TimeoutError as err:
                raise UdpTimeout(
                    f"Timeout nach {self.timeout}s (id={message['id']})"
                ) from err
            except OSError as err:
                raise UdpError(f"Empfangen fehlgeschlagen: {err}") from err

            text = data.decode("utf-8", errors="replace").strip()
            _LOGGER.trace("RX %s:%s %s", sender[0], sender[1], text)  # type: ignore[attr-defined]
            try:
                response = json.loads(text)
            except ValueError:
                _LOGGER.debug("Ignoriere nicht-JSON Paket von %s", sender[0])
                continue
            if not isinstance(response, dict):
                continue
            if response.get("id") != message["id"]:
                _LOGGER.debug(
                    "Ignoriere Antwort mit fremder id=%s (erwartet %s)",
                    response.get("id"),
                    message["id"],
                )
                continue

            if "error" in response:
                err_obj = response["error"] or {}
                raise ApiError(
                    int(err_obj.get("code", 0)),
                    str(err_obj.get("message", "unknown")),
                    err_obj.get("data"),
                )

            result = response.get("result")
            if not isinstance(result, dict):
                raise UdpError(f"{method}: Antwort ohne 'result'")
            result.setdefault("_src", response.get("src"))
            result.setdefault("_sender_ip", sender[0])
            _LOGGER.debug(
                "%s ok (id=%s, Versuch %s/%s)", method, message["id"], attempt, attempts
            )
            return result

    # ------------------------------------------------------------------
    def discover(self, ble_mac: str | None, broadcast_port: int | None = None) -> dict[str, Any]:
        """``Marstek.GetDevice`` - unicast, mit Broadcast-Fallback."""
        params = {"ble_mac": ble_mac or "0"}
        try:
            return self.request(
                "Marstek.GetDevice", params, with_instance=False
            )
        except UdpError as err:
            _LOGGER.warning("Unicast-Discovery fehlgeschlagen (%s) - versuche Broadcast", err)
            port = broadcast_port or self.port
            return self.request(
                "Marstek.GetDevice",
                {"ble_mac": "0"},
                target=("255.255.255.255", port),
                with_instance=False,
            )


class _RequestGuard:
    """Kleiner Context-Manager um einen Lock (besser lesbar im Code oben)."""

    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def __enter__(self) -> _RequestGuard:
        self._lock.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._lock.release()
