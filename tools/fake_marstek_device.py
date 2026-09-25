#!/usr/bin/env python3
"""Kleiner Marstek-Geraetesimulator fuer lokale Tests.

Beantwortet die UDP-Kommandos der Open API mit plausiblen Beispielwerten.

    python3 tools/fake_marstek_device.py --port 30000

Danach die Bridge z. B. so starten:

    MARSTEK_DEVICE_IP=127.0.0.1 MARSTEK_MQTT_HOST=127.0.0.1 \
    MARSTEK_LOG_LEVEL=trace python3 -m app.main
"""

from __future__ import annotations

import argparse
import json
import random
import socket

SRC = "VenusC-123456789012"


def handle(msg: dict) -> dict:
    method = msg.get("method")
    mid = msg.get("id", 0)
    params = msg.get("params") or {}
    inst = params.get("id", 0)

    if method == "Marstek.GetDevice":
        result = {
            "device": "VenusC",
            "ver": 111,
            "ble_mac": "123456789012",
            "wifi_mac": "012123456789",
            "wifi_name": "MY_HOME",
            "ip": "192.168.0.45",
        }
    elif method == "Wifi.GetStatus":
        result = {
            "id": inst,
            "wifi_mac": "620b0c877705",
            "ssid": "Hame",
            "rssi": random.randint(-75, -45),
            "sta_ip": "192.168.0.45",
            "sta_gate": "192.168.0.1",
            "sta_mask": "255.255.255.0",
            "sta_dns": "192.168.0.1",
        }
    elif method == "BLE.GetStatus":
        result = {"id": inst, "state": "connect", "ble_mac": "50cf14640fac"}
    elif method == "Bat.GetStatus":
        result = {
            "id": inst,
            "soc": random.randint(20, 99),
            "charg_flag": True,
            "dischrg_flag": True,
            "bat_temp": 25.0,
            "bat_capacity": 2560.0,
            "rated_capacity": 5120.0,
        }
    elif method == "PV.GetStatus":
        result = {"id": inst}
        for i in range(1, 5):
            result[f"pv{i}_power"] = random.randint(0, 400)
            result[f"pv{i}_voltage"] = random.randint(8, 40)
            result[f"pv{i}_current"] = 0
            result[f"pv{i}_state"] = random.choice([0, 1])
    elif method == "ES.GetStatus":
        result = {
            "id": inst,
            "bat_soc": 98,
            "bat_cap": 5120,
            "pv_power": 0,
            "ongrid_power": random.randint(-800, 800),
            "offgrid_power": 0,
            "bat_power": random.randint(-800, 800),
            "total_pv_energy": 0,
            "total_grid_output_energy": 2548,
            "total_grid_input_energy": 3273,
            "total_load_energy": 0,
        }
    elif method == "ES.GetMode":
        result = {
            "id": inst,
            "mode": "Auto",
            "ongrid_power": 100,
            "offgrid_power": 0,
            "bat_soc": 98,
            "ct_state": 1,
            "a_power": 0,
            "b_power": 0,
            "c_power": 0,
            "total_power": 0,
            "input_energy": 3086320,
            "output_energy": 4487510,
        }
    elif method == "EM.GetStatus":
        result = {
            "id": inst,
            "ct_state": 1,
            "a_power": 0,
            "b_power": 0,
            "c_power": 0,
            "total_power": random.randint(-500, 500),
            "input_energy": 0,
            "output_energy": 0,
        }
    elif method in ("ES.SetMode", "DOD.SET", "Ble.Adv", "Led.Ctrl"):
        result = {"id": inst, "set_result": True}
    else:
        return {
            "id": mid,
            "src": SRC,
            "error": {"code": -32601, "message": "Method not found", "data": 404},
        }

    return {"id": mid, "src": SRC, "result": result}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    print(f"Fake Marstek device auf {args.bind}:{args.port}")

    while True:
        data, addr = sock.recvfrom(8192)
        try:
            msg = json.loads(data.decode("utf-8"))
        except ValueError:
            continue
        print(f"<- {addr[0]}:{addr[1]} {data.decode('utf-8')}")
        response = handle(msg)
        out = json.dumps(response, separators=(",", ":")).encode("utf-8")
        sock.sendto(out, addr)
        print(f"-> {addr[0]}:{addr[1]} {out.decode('utf-8')}")


if __name__ == "__main__":
    main()
