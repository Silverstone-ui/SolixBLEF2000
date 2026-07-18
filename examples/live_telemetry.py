"""Replay the real GATT handshake captured from the Anker app to pull live
telemetry from a 767 PowerHouse (F2000), bypassing the SolixBLE library's
built-in (incompatible) negotiation protocol.

Reverse-engineered from a Bluetooth HCI snoop capture of the official
Anker app talking to the device:
  - Vendor service 014bf5da-0000-1000-8000-00805f9b34fb
  - Write char:  00007777-0000-1000-8000-00805f9b34fb (write-without-response)
  - Notify char: 00008888-0000-1000-8000-00805f9b34fb
"""

import asyncio
from bleak import BleakScanner, BleakClient

CHAR_WRITE = "00007777-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00008888-0000-1000-8000-00805f9b34fb"

# Captured from the real app: triggers a full telemetry notification.
POLL_TELEMETRY = bytes.fromhex("08ee00000001010a0002")


def on_notify(sender, data: bytearray):
    print(f"\n--- Notification ({len(data)} bytes) ---")
    print(data.hex())
    # try to spot an embedded ASCII serial/string
    ascii_chars = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    print(f"ascii: {ascii_chars}")


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
    async with BleakClient(target) as client:
        print(f"Connected: {client.is_connected}")

        await client.start_notify(CHAR_NOTIFY, on_notify)
        print("Subscribed to notifications.")

        await asyncio.sleep(0.5)

        print("Sending telemetry poll command...")
        await client.write_gatt_char(CHAR_WRITE, POLL_TELEMETRY, response=False)

        print("Waiting for response...")
        await asyncio.sleep(5)

        print("\nDone. Disconnecting.")


if __name__ == "__main__":
    asyncio.run(main())
