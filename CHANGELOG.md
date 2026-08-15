# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). This file starts
from the F2000Alt work below — earlier releases aren't retroactively documented here.

## [3.9.1] - 2026-08-15

### Fixed

- `F2000Alt.ac_output_power` and `F2000Alt.power_out` were reading offset 21 and 41 as
  single bytes (max 255W each), silently wrapping/misreading any AC or combined load at
  or above 256W. Both are 16-bit little-endian fields spanning offset 21-22 and 41-42
  respectively. All values seen during this project's own live testing were under 100W,
  so the bug went uncaught until a community member (`impala454`, cross-referencing an
  independently-built third-party library) reported and confirmed it on their own
  hardware — see issue #8.

## [3.9.0] - 2026-07-20

### Added

- `F2000Alt` device class for the alternate-protocol 767 PowerHouse hardware variant —
  some units speak a different, unencrypted BLE protocol instead of this library's
  standard encrypted one. Reverse-engineered from an HCI snoop capture; see
  `docs/source/f2000_hardware_variant.rst` for the full protocol writeup.
- `F2000Alt` control methods: `turn_ac_on`/`turn_ac_off`, `turn_dc_on`/`turn_dc_off`,
  `turn_power_saving_mode_on`/`turn_power_saving_mode_off`, `set_light_mode()`.
- `F2000Alt.ac_output_power` — AC output power only, in watts.
- `F2000Alt.power_saving_mode_enabled` — power saving mode status readback.
- `examples/f2000_alt_diagnostics.py` — interactive connect/toggle/inspect tool for
  verifying `F2000Alt` behavior against real hardware.
- `examples/parse_hci_snoop.py` — decodes an Android Bluetooth HCI snoop log (e.g.
  from a bug report) into a readable GATT write/notify timeline, with fragment
  reassembly and a warning when the capture was taken in "Filtered" logging mode.

### Fixed

- `discover_devices()` was filtering by the wrong service UUID for this variant
  (`0000ff09` instead of `00001780`) — it would never have shown up in discovery.
- `F2000Alt.power_out` did not track real output power. It now correctly reads AC
  output + light bar power combined (offset 41) — independently validated
  byte-for-byte against a real HCI snoop capture of the official Anker app.

### Documentation

- Full field map, control command reference, and identification methods for the
  F2000Alt hardware variant.
- Evidence that the alt-protocol variant is most likely a distinct hardware/BOM
  revision rather than a firmware-gated feature (a second unit's Bluetooth chip
  vendor and WiFi hardware both differ).
