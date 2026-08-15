# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). This file starts
from the F2000Alt work below — earlier releases aren't retroactively documented here.

## [3.9.3] - 2026-08-15

### Fixed

- `F2000Alt.solar_power_in` and `F2000Alt.power_in` are now confirmed live, not just
  cross-referenced: `solar_power_in` jumped from 0 to 105W the moment a solar panel
  started actively producing power, matching a ~95W reading from the unit's own
  app/screen at the same moment; `power_in` read exactly `ac_power_in + solar_power_in`
  (0 + 105 = 105), confirming it's genuinely "AC + solar combined," not a duplicate of
  `ac_power_in` as previously assumed. Docstrings/docs updated accordingly - no code
  change, the offsets were already correct as of 3.9.2.

## [3.9.2] - 2026-08-15

### Added

- `F2000Alt.solar_power_in` — solar input power (offset 37-38). Not yet confirmed
  against a live solar load on this project's own hardware.
- `F2000Alt.power_in` — total input power, all sources combined (offset 39-40).
  Previously assumed to duplicate `ac_power_in`; a third-party library documents it
  as a distinct field, indistinguishable from `ac_power_in` in every test run here
  so far because solar was never connected.
- `F2000Alt.dc1_power` / `F2000Alt.dc2_power` — per-port DC/car-socket output power
  (offset 33-34 / 35-36).
- `F2000Alt.external_battery_percentage` / `F2000Alt.total_battery_percentage` /
  `F2000Alt.external_battery_temperature` — expansion-battery fields (offset 71,
  72, 67). Not confirmed on this project's own hardware (no expansion battery
  available to test with).

All of the above are cross-referenced from a third-party independently-built
library's field map, the same source that identified the `ac_output_power`/
`power_out` 16-bit LE bug fixed in 3.9.1.

### Fixed

- `F2000Alt.usb_c1_power`/`usb_c2_power`/`usb_c3_power`/`usb_a1_power`/`usb_a2_power`
  had the same single-byte-vs-16-bit-LE bug as `ac_output_power`/`power_out` (fixed
  in 3.9.1) — found this session while cross-referencing the third-party library
  above, before any load actually triggered it in practice.

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
