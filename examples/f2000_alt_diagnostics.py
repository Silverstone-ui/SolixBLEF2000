"""Interactive diagnostics/verification tool for F2000Alt.

For the 767 PowerHouse alternate-protocol hardware variant. Connects to a
real unit, prints full telemetry, and offers to toggle each control (AC
output, DC/car-socket output, power saving mode, light bar modes) one at a
time - showing before/after telemetry so you can confirm behavior against
real hardware without reconstructing the connect/scan/command boilerplate
from scratch.

Written for contributors verifying changes to the reverse-engineered
protocol - see docs/source/f2000_hardware_variant.rst for the full field
map and background.

Usage:
    python examples/f2000_alt_diagnostics.py
"""

import asyncio

from SolixBLE import F2000Alt, discover_devices
from SolixBLE.states import LightStatus


def print_status(device: F2000Alt, label: str) -> None:
    """Print every F2000Alt property plus the raw base frame."""
    print(f"\n--- {label} ---")
    print(f"serial_number:        {device.serial_number}")
    print(f"software_version:     {device.software_version}")
    print(f"battery_percentage:   {device.battery_percentage}")
    print(f"temperature:          {device.temperature}")
    print(f"power_out (AC+light): {device.power_out}")
    print(f"ac_output_power:      {device.ac_output_power}")
    print(f"ac_power_in:          {device.ac_power_in}")
    print(f"ac_output:            {device.ac_output}")
    print(f"ac_cable_connected:   {device.ac_cable_connected}")
    print(f"dc_output:            {device.dc_output}")
    print(f"charging_status:      {device.charging_status}")
    print(f"power_saving_mode_enabled: {device.power_saving_mode_enabled}")
    print(f"light:                {device.light}")
    # Reach into the raw frame directly (not a public API) for byte-level
    # inspection - useful when chasing down a still-unidentified offset.
    raw = device._data
    if raw is not None:
        print(f"raw base frame ({len(raw)} bytes): {raw.hex()}")


async def find_f2000_alt() -> F2000Alt | None:
    """Scan and return the first F2000Alt-looking device found, if any."""
    print("Scanning for a 767 PowerHouse (F2000Alt)...")
    devices = await discover_devices()
    for ble_device in devices:
        if ble_device.name and "767" in ble_device.name:
            return F2000Alt(ble_device)
    return None


async def prompt_yes_no(question: str) -> bool:
    """Ask a y/N question without blocking the event loop."""
    answer = await asyncio.to_thread(input, f"{question} [y/N] ")
    return answer.strip().lower() == "y"


async def main() -> None:
    device = await find_f2000_alt()
    if device is None:
        print("No F2000Alt device found. Make sure it's powered on and in range.")
        return

    print(f"Connecting to {device.address}...")
    if not await device.connect():
        print("Failed to connect!")
        return

    try:
        await device.get_status_update()
        print_status(device, "baseline")

        if await prompt_yes_no("\nToggle AC output on, then off?"):
            await device.turn_ac_on()
            await asyncio.sleep(3)
            await device.get_status_update()
            print_status(device, "AC on")
            await device.turn_ac_off()
            await asyncio.sleep(1)
            await device.get_status_update()
            print_status(device, "AC off")

        if await prompt_yes_no("\nToggle DC/car-socket output on, then off?"):
            await device.turn_dc_on()
            await asyncio.sleep(3)
            await device.get_status_update()
            print_status(device, "DC on")
            await device.turn_dc_off()
            await asyncio.sleep(1)
            await device.get_status_update()
            print_status(device, "DC off")

        if await prompt_yes_no("\nCycle power saving mode on, then off?"):
            await device.turn_power_saving_mode_on()
            await asyncio.sleep(3)
            await device.get_status_update()
            print_status(device, "power saving ON")
            await device.turn_power_saving_mode_off()
            await asyncio.sleep(3)
            await device.get_status_update()
            print_status(device, "power saving OFF")

        if await prompt_yes_no("\nCycle light bar through LOW/MEDIUM/HIGH/OFF?"):
            for mode in (
                LightStatus.LOW,
                LightStatus.MEDIUM,
                LightStatus.HIGH,
                LightStatus.OFF,
            ):
                await device.set_light_mode(mode)
                await asyncio.sleep(2)
                await device.get_status_update()
                print_status(device, f"light={mode.name}")
    finally:
        await device.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(main())
