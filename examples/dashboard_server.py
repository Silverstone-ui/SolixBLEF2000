"""Live web dashboard for the Anker 767 PowerHouse (alternate BLE protocol).

Keeps a single persistent BLE connection (does not reconnect between polls,
to avoid stressing the BLE stack) and polls periodically, pushing decoded
telemetry to any connected browser over a WebSocket.

Run:
    python examples/dashboard_server.py

Then open http://localhost:8765 in a browser.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from aiohttp import web, WSMsgType
from bleak import BleakScanner, BleakClient

CHAR_WRITE = "00007777-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00008888-0000-1000-8000-00805f9b34fb"
POLL_TELEMETRY = bytes.fromhex("08ee00000001010a0002")
POLL_INTERVAL_SECONDS = 10
HISTORY_LENGTH = 60

LIGHT_MODES = {0: "off", 1: "low", 2: "medium", 3: "high", 4: "sos"}
TEMP_UNITS = {0: "C", 1: "F"}

STATIC_DIR = Path(__file__).parent / "dashboard_static"

clients: set[web.WebSocketResponse] = set()
latest_state: dict = {"connected": False}
power_history: list[dict] = []


def decode_telemetry(data: bytes) -> dict:
    result = {
        "battery_percent": data[70],
        "temperature_c": data[66],
        "firmware_version": ".".join(str(data[47])),
        "power_watts": data[41],
        "ac_input_watts": int.from_bytes(data[19:21], "little"),
        "time_remaining_hours": round(int.from_bytes(data[57:59], "little") / 10.0, 1),
        "ac_output": bool(data[63]),
        "ac_cable_connected": data[65] != 0,
        "ac_charge_state": data[68],
        "dc_output": bool(data[80]) or bool(data[81]),
        "usb_c": [
            {"label": "top", "watts": data[23], "active": bool(data[75])},
            {"label": "middle", "watts": data[25], "active": bool(data[76])},
            {"label": "bottom", "watts": data[27], "active": bool(data[77])},
        ],
        "usb_a": [
            {"label": "top", "watts": data[29], "active": bool(data[78])},
            {"label": "bottom", "watts": data[31], "active": bool(data[79])},
        ],
        "serial_number": data[85:101].decode("ascii", errors="replace").rstrip("\x00"),
    }
    if len(data) >= 120:
        result.update(
            {
                "ac_charging_power_limit": int.from_bytes(data[101:103], "little"),
                "display_timeout_seconds": int.from_bytes(data[105:107], "little"),
                "display_brightness": data[115],
                "light_mode": LIGHT_MODES.get(data[118], f"unknown({data[118]})"),
                "temperature_unit": TEMP_UNITS.get(data[119], "?"),
            }
        )
    return result


async def broadcast():
    payload = json.dumps(latest_state)
    dead = set()
    for ws in clients:
        try:
            await ws.send_str(payload)
        except ConnectionResetError:
            dead.add(ws)
    clients.difference_update(dead)


async def ble_loop(app):
    print("Scanning for 767 PowerHouse...")
    found = await BleakScanner.discover(timeout=8.0, return_adv=True)
    target = None
    for address, (d, adv) in found.items():
        if d.name and "767" in d.name:
            target = d
            break

    if target is None:
        print("Device not found!")
        latest_state.update({"connected": False, "error": "Device not found"})
        await broadcast()
        return

    print(f"Connecting to {target.name} ({target.address})...")

    have_extended = asyncio.Event()

    def on_notify(sender, data: bytearray):
        if len(data) < 100:
            return
        decoded = decode_telemetry(bytes(data))
        latest_state.update(decoded)
        latest_state["connected"] = True
        latest_state["last_update"] = datetime.now().strftime("%H:%M:%S")
        latest_state.pop("error", None)
        if len(data) >= 120:
            power_history.append({"t": time.time(), "w": decoded["power_watts"]})
            del power_history[:-HISTORY_LENGTH]
            latest_state["power_history"] = power_history
            have_extended.set()

    async with BleakClient(target) as client:
        await client.start_notify(CHAR_NOTIFY, on_notify)
        latest_state["device_name"] = target.name
        latest_state["device_address"] = target.address
        print(f"Connected. Polling every {POLL_INTERVAL_SECONDS}s.")

        while True:
            have_extended.clear()
            try:
                await client.write_gatt_char(CHAR_WRITE, POLL_TELEMETRY, response=False)
                await asyncio.wait_for(have_extended.wait(), timeout=10)
                await broadcast()
            except TimeoutError:
                print("Poll timed out, retrying...")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    await ws.send_str(json.dumps(latest_state))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
    return ws


async def start_background_ble(app):
    app["ble_task"] = asyncio.create_task(ble_loop(app))


def main():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC_DIR)
    app.on_startup.append(start_background_ble)
    web.run_app(app, host="0.0.0.0", port=8765)


if __name__ == "__main__":
    main()
