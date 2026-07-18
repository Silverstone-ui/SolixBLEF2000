"""Monitor for the Anker 767 PowerHouse (F2000) using its reverse-engineered
native BLE protocol.

This device's actual firmware does not implement the SolixBLE library's
built-in F2000 protocol (the encrypted 8c850002/8c850003 characteristic
negotiation). Instead it exposes a simpler vendor service and protocol,
reverse-engineered from a Bluetooth HCI snoop capture of the official
Anker app and confirmed against real hardware by toggling every output,
checking the app/device screen, and diffing telemetry frames byte-by-byte.

Full field map and methodology: docs/source/f2000_hardware_variant.rst

  Service:        014bf5da-0000-1000-8000-00805f9b34fb
  Write char:     00007777-0000-1000-8000-00805f9b34fb (write-without-response)
  Notify char:    00008888-0000-1000-8000-00805f9b34fb

Notification frames come in two sizes:
  - ~102 bytes: base telemetry, sent both passively and in response to a poll.
  - ~122 bytes: extended - only in direct response to POLL_TELEMETRY. Contains
    everything the base frame does, plus a settings/configuration block
    appended before the checksum.

Known unknowns (see the doc above for the full list): "time to full charge"
has not been located, bytes 17-18 fluctuate unexplained regardless of load,
and several settings-block bytes (103, 107, 109, 111, 116) are untested.
"""

import asyncio
from bleak import BleakScanner, BleakClient

CHAR_WRITE = "00007777-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "00008888-0000-1000-8000-00805f9b34fb"

# Triggers a full telemetry notification (reverse-engineered from app capture).
POLL_TELEMETRY = bytes.fromhex("08ee00000001010a0002")

LIGHT_MODES = {0: "off", 1: "low", 2: "medium", 3: "high", 4: "sos"}
TEMP_UNITS = {0: "C", 1: "F"}


def decode_telemetry(data: bytes) -> dict:
    result = {
        "battery_percent": data[70],
        "temperature_c": data[66],
        "firmware_version": ".".join(str(data[47])),
        "power_watts": data[41],
        "ac_input_watts": int.from_bytes(data[19:21], "little"),
        "time_remaining_hours": int.from_bytes(data[57:59], "little") / 10.0,
        "ac_output": bool(data[63]),
        "ac_cable_connected": data[65] != 0,
        "ac_charge_state": data[68],  # 0=idle, 1=AC output active, 2=AC charging
        "dc_output": bool(data[80]) or bool(data[81]),
        "usb_c_power": [data[23], data[25], data[27]],
        "usb_c_active": [bool(data[75]), bool(data[76]), bool(data[77])],
        "usb_a_power": [data[29], data[31]],
        "usb_a_active": [bool(data[78]), bool(data[79])],
        "serial_number": data[85:101].decode("ascii", errors="replace").rstrip("\x00"),
        "_unidentified_bytes_17_18": int.from_bytes(data[17:19], "little"),
    }

    # Settings block - only present in the ~122-byte extended response.
    if len(data) >= 120:
        result.update(
            {
                "ac_charging_power_limit": int.from_bytes(data[101:103], "little"),
                "display_timeout_seconds": int.from_bytes(data[105:107], "little"),
                "display_brightness": data[115],
                "light_mode": LIGHT_MODES.get(data[118], f"unknown({data[118]})"),
                "temperature_unit": TEMP_UNITS.get(data[119], f"unknown({data[119]})"),
            }
        )

    return result


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

    result = {}
    got_extended = asyncio.Event()

    def on_notify(sender, data: bytearray):
        # Ignore the small ~14-byte heartbeat/ack frames.
        if len(data) < 100:
            return
        result.update(decode_telemetry(bytes(data)))
        # Wait specifically for the extended (~122-byte) frame so the
        # settings block is populated before we print.
        if len(data) >= 120:
            got_extended.set()

    async with BleakClient(target) as client:
        await client.start_notify(CHAR_NOTIFY, on_notify)
        await asyncio.sleep(0.5)
        await client.write_gatt_char(CHAR_WRITE, POLL_TELEMETRY, response=False)

        try:
            await asyncio.wait_for(got_extended.wait(), timeout=10)
        except TimeoutError:
            print("Timed out waiting for telemetry.")
            return

    print("\n--- 767 PowerHouse Status ---")
    print(f"Battery:            {result['battery_percent']}%")
    print(f"Temperature:        {result['temperature_c']}C ({result.get('temperature_unit', '?')} display)")
    print(f"Time remaining:     {result['time_remaining_hours']:.1f}h (discharge estimate only)")
    print(f"Power output:       {result['power_watts']}W")
    print(f"AC input (charge):  {result['ac_input_watts']}W")
    print(f"AC output:          {'on' if result['ac_output'] else 'off'}")
    print(f"AC cable connected: {result['ac_cable_connected']}")
    print(f"AC/charge state:    {result['ac_charge_state']}")
    print(f"DC/Car socket:      {'on' if result['dc_output'] else 'off'}")
    print(f"USB-C power (W):    {result['usb_c_power']}  active: {result['usb_c_active']}")
    print(f"USB-A power (W):    {result['usb_a_power']}  active: {result['usb_a_active']}")
    print(f"AC charge limit:    {result.get('ac_charging_power_limit', '?')}W")
    print(f"Display timeout:    {result.get('display_timeout_seconds', '?')}s")
    print(f"Display brightness: {result.get('display_brightness', '?')}")
    print(f"Light bar mode:     {result.get('light_mode', '?')}")
    print(f"Serial:             {result['serial_number']}")
    print(f"Firmware:           {result['firmware_version']}")
    print(f"(unidentified bytes 17-18, raw): {result['_unidentified_bytes_17_18']}")


if __name__ == "__main__":
    asyncio.run(main())
