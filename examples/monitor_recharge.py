"""Actively monitor the 767 PowerHouse while it finishes AC recharging,
using the confirmed field mapping from live protocol reverse-engineering.

Stays connected the whole time (does not reconnect between polls, to avoid
stressing the BLE stack) and polls periodically, printing status each time
and flagging the moment charging completes.
"""

import asyncio
from datetime import datetime
from bleak import BleakScanner, BleakClient

CHAR_WRITE = "00007777-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00008888-0000-1000-8000-00805f9b34fb"

POLL_TELEMETRY = bytes.fromhex("08ee00000001010a0002")
POLL_INTERVAL_SECONDS = 15


def decode(data: bytes) -> dict:
    return {
        "battery_percent": data[70],
        "temperature_c": data[66],
        "ac_input_watts": int.from_bytes(data[19:21], "little"),
        "ac_plus_light_out_watts": data[41],  # AC output + light bar combined, not DC
        "ac_output": bool(data[63]),
        "charging_flag": data[65],
        "ac_charge_state": data[68],
    }


async def main():
    print("Scanning for 767 PowerHouse...")
    found = await BleakScanner.discover(timeout=8.0, return_adv=True)
    target = None
    for address, (d, adv) in found.items():
        if d.name and "767" in d.name:
            target = d
            break
    if target is None:
        print("Device not found! Make sure it's powered on and in range.")
        return

    print(f"Connecting to {target.name} ({target.address})...")

    latest = {}
    got_telemetry = asyncio.Event()

    def on_notify(sender, data: bytearray):
        if len(data) >= 100:
            latest.update(decode(bytes(data)))
            got_telemetry.set()

    was_charging = None

    async with BleakClient(target) as client:
        await client.start_notify(CHAR_NOTIFY, on_notify)
        print(f"Connected. Polling every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.\n")

        while True:
            got_telemetry.clear()
            try:
                await client.write_gatt_char(CHAR_WRITE, POLL_TELEMETRY, response=False)
                await asyncio.wait_for(got_telemetry.wait(), timeout=10)
            except TimeoutError:
                print(f"[{datetime.now():%H:%M:%S}] poll timed out, retrying...")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            is_charging = latest["charging_flag"] != 0
            ts = datetime.now().strftime("%H:%M:%S")

            print(
                f"[{ts}] battery={latest['battery_percent']}%  "
                f"ac_in={latest['ac_input_watts']}W  "
                f"temp={latest['temperature_c']}C  "
                f"charging={'yes' if is_charging else 'no'}"
            )

            if was_charging and not is_charging:
                print(
                    f"\n*** CHARGING COMPLETE at [{ts}] — "
                    f"battery={latest['battery_percent']}%, ac_in={latest['ac_input_watts']}W ***\n"
                )
                break

            was_charging = is_charging
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        print("Done monitoring. Disconnecting.")


if __name__ == "__main__":
    asyncio.run(main())
