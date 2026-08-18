# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). This file starts
from the F2000Alt work below — earlier releases aren't retroactively documented here.

## [3.9.7] - 2026-08-18

### Fixed

- `F2000Alt`'s control-command builder (`_send_control`) now computes its length byte
  dynamically instead of hardcoding a fixed "middle" constant (`0b00`). Only ever looked
  fixed because every command implemented so far (AC/DC/power-save/light, all single-byte
  values) happens to produce the same 11-byte frame. Flagged by `impala454` (see #10) -
  their independently-built library's command definitions show this is a genuine
  length-of-frame field that varies for commands with larger parameters. No behavior
  change for existing commands (output is byte-identical, verified by the existing test
  suite) - this unblocks implementing the timer/recharge-power/screen-brightness commands
  correctly whenever those get a real HCI capture.

## [3.9.6] - 2026-08-15

### Fixed

- `F2000Alt.time_remaining` (and `hours_remaining`/`days_remaining`/`timestamp_remaining`,
  all downstream of it) now read the correct offsets. Previously read offset 57-58 as a
  16-bit LE value, which was found completely frozen across wildly different live
  conditions in one session while the unit's own screen moved a lot — documented as
  unreliable in 3.9.4. Root cause found by cross-referencing an independent third-party
  open-source HA integration for this exact device (`yun-s-oh/ha-anker-solix-f2000`),
  which reads this as two separate single bytes: offset 17 (hours, value/10) and offset
  18 (whole days) — not the same offsets read as a combined 16-bit pair. Verified against
  three live readings from earlier this session, paired with the unit's own screen at that
  exact moment: two exact matches (16.5h, 7.0h) and one close match (16.6h vs 16.4h, same
  small tolerance seen elsewhere in this project).

## [3.9.5] - 2026-08-15

### Fixed

- Cherry-picked 5 reliability/logging commits from `javier-omar/SolixBLEF2000` (a sibling
  fork of this project, itself forked from `flip-dots/SolixBLE`): malformed telemetry
  packets no longer overwrite good cached data, unknown/undecodable message types log at
  debug instead of error+traceback, and the background reconnect loop backs off less
  aggressively while logging quietly instead of flooding errors on every retry. Verified
  with a full test-suite run before merging (no regressions; one pre-existing flaky test
  confirmed unrelated by reproducing it on `main` before these changes too). Two of the
  five directly benefit `F2000Alt` (it inherits the shared reconnect loop); the other
  three touch the base encrypted-protocol parser, which `F2000Alt` doesn't use, but still
  improve the library for every other device class it supports.

## [3.9.4] - 2026-08-15

### Fixed

- Documented `F2000Alt.time_remaining` (and `hours_remaining`/`days_remaining`/
  `timestamp_remaining`, which all depend on it) as confirmed unreliable. Offset
  57-58 was found completely frozen at the same raw value across 5 very different
  live conditions in one session (load 67W-287W, battery 100%->99%, solar
  0W-303W), while the unit's own screen moved a lot (16.4h -> 7h) over the same
  period - not a divisor problem, the byte itself doesn't move. No code change
  (still returns `raw / 10.0`, unchanged pending a real fix) - this is a
  documentation-only release so downstream consumers (HaSolixBLE) know not to
  trust it.

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
