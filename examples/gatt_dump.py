"""Dump the GATT services/characteristics of the 767 PowerHouse (F2000).

Useful when a device doesn't match this library's expected protocol - see
docs/source/f2000_hardware_variant.rst for how this was used to discover
this device's alternate BLE protocol.
"""

import asyncio
from bleak import BleakScanner, BleakClient


async def main():
    found = await BleakScanner.discover(timeout=8.0, return_adv=True)
    target = None
    for address, (d, adv) in found.items():
        if d.name and "767" in d.name:
            target = d
            break
    if target is None:
        print("Not found")
        return

    async with BleakClient(target) as client:
        print(f"Connected: {client.is_connected}")
        for service in client.services:
            print(f"[Service] {service.uuid} - {service.description}")
            for char in service.characteristics:
                print(f"    [Char] {char.uuid} - props={char.properties} - {char.description}")


if __name__ == "__main__":
    asyncio.run(main())
