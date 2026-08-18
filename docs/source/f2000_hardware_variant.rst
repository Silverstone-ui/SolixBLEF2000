F2000 hardware variant (alternate BLE protocol)
================================================

Background
----------

The :class:`~SolixBLE.F2000` class implements a protocol based on the encrypted, negotiated
command/telemetry scheme used by most other devices in this library (characteristics
``8c850002``/``8c850003``, packets prefixed with ``ff09``, session negotiation, etc).

At least one real-world 767 PowerHouse unit does **not** speak that protocol at all. Its BLE
GATT server does not expose the ``8c850002``/``8c850003`` characteristics, and does not respond
to the standard negotiation handshake. Instead it exposes a much simpler, unencrypted
request/notify protocol on a different vendor service.

This page documents that alternate protocol so it can be added as a variant/subclass, and so
other owners of the same hardware revision can identify it and contribute further findings,
per the process described in :doc:`new_devices` and :ref:`new_device_control`.

This is most likely a genuine hardware/BOM revision, not just a firmware branch. The one
alt-protocol unit examined has BLE MAC OUI ``E8:EE:CC:...``. A second owner (of the upstream
project this was forked from) checked two of their own units for comparison — a C1000 and a
standard-protocol F2000 — and both reported OUI ``F4:9D:8A:...`` instead, a different Bluetooth
chip vendor. Their F2000 also has WiFi hardware in addition to Bluetooth; nothing in this
alt-protocol unit's capture ever showed WiFi. A firmware update doesn't swap the physical BT
chip or add a WiFi radio, so this is real evidence of a distinct hardware revision rather than
a firmware-gated feature — though it's still only one alt-protocol unit vs. two standard-protocol
ones, so treat this as strong-but-not-conclusive. If you own a 767 PowerHouse, the methods below
(ordered from easiest/most reliable to more speculative) let you check which protocol yours
speaks.


Identifying your hardware
--------------------------

**1. Firmware version (easiest — no BLE tooling required).**
The one unit examined so far reports firmware version **2.1.5** (readable in the Anker app's
device settings, and also present in the BLE payload itself — see
:ref:`f2000_variant_firmware`). If Anker gates this protocol behind a firmware version
threshold, checking your version in the app before doing anything else may be enough to tell
you which variant you have. This is a single data point, not a confirmed cutoff — if you check
your own unit's firmware version and protocol, please contribute that pairing (see
:ref:`new_device_control`) so a real boundary can be established.

**2. BLE advertising data (before connecting).**
This variant advertises service UUID ``00001780-0000-1000-8000-00805f9b34fb`` in its BLE
advertisement packet. The standard :func:`~SolixBLE.discover_devices` helper only matches
``0000ff09-0000-1000-8000-00805f9b34fb``, so a 767 PowerHouse advertising ``0x1780`` instead
(or in addition) is a strong signal you have this variant — checkable with a plain BLE scan,
no connection attempt needed.

**3. GATT service (after connecting, before any commands).**
This variant exposes vendor service ``014bf5da-0000-1000-8000-00805f9b34fb`` with
characteristics ``00007777``/``00008888``. A standard F2000 instead exposes
``8c850002``/``8c850003``. Enumerating services immediately after connecting (before
attempting negotiation) distinguishes them cleanly. Equivalently, if you just try connecting
with the existing :class:`~SolixBLE.F2000` class, ``connect()`` will fail at the
notification-subscription step with a ``BleakCharacteristicNotFoundError`` for ``8c850003``.

**4. BLE MAC address OUI.** ``E8:EE:CC:...`` on the one alt-protocol unit examined, vs.
``F4:9D:8A:...`` confirmed on two standard-protocol units (a C1000 and a F2000) from a second
owner. Different Bluetooth chip vendor — a real signal, though still based on a small sample.

**5. WiFi hardware presence.** The standard-protocol F2000 checked above has WiFi in addition
to Bluetooth. Nothing in the alt-protocol unit's capture ever indicated WiFi capability. Not
independently confirmed as a reliable distinguishing method yet, but consistent with the OUI
evidence above.

**6. Weaker, single-sample clue** (not confirmed as reliable — only one unit examined):

- Serial number prefix ``AZVX2Y0E...``.


Capture methodology
--------------------

Unlike the Frida-based approach in :doc:`app_decoding`, this protocol was reverse-engineered
using a much simpler method available on any Android phone without root or app patching:

1. Enable **Developer options → Bluetooth HCI snoop log**, and set it to **Enabled** (the
   non-"Filtered" option — the default "Filtered" mode truncates and zero-pads ACL payloads
   beyond ~10 bytes and is not usable for this purpose).
2. Toggle Bluetooth off/on so the new logging mode takes effect.
3. Use the official Anker app normally against the device (view status, toggle outputs).
4. Generate a **Full** Android bug report (Developer options → Bug report → Full report).
5. Extract ``FS/data/misc/bluetooth/logs/btsnoop_hci.log`` from the resulting zip. This is a
   standard BTSnoop v1 (H4) capture readable with any generic BTSnoop parser — no Wireshark
   or specialized tooling required, though Wireshark works too.

From that capture, the GATT service/characteristic layout and command sequence were identified
by locating the LE connection to the device's advertised address, then walking the ATT
protocol exchange (service/characteristic discovery, CCCD write, and the write/notify traffic).

Every field below was then verified empirically against real hardware: toggling a physical
control (AC, DC, USB port, light) or checking the device's own screen/app, then polling and
diffing the raw payload byte-by-byte against a baseline to isolate exactly which byte(s)
changed. This is the same "diff on state change" methodology described in :doc:`new_devices`.


GATT layout
-----------

======================= =======================================
Service                 ``014bf5da-0000-1000-8000-00805f9b34fb``
Write characteristic    ``00007777-0000-1000-8000-00805f9b34fb`` (write-without-response)
Notify characteristic   ``00008888-0000-1000-8000-00805f9b34fb``
======================= =======================================

Handshake:

1. Subscribe to notifications on ``00008888...`` (writes ``0x0001`` to its CCCD).
2. Write ``08ee00000001010a0002`` to ``00007777...`` (write-without-response) to request a
   telemetry update.
3. The device replies on ``00008888...`` with either:

   - A **~102-byte** passive/base telemetry frame, or
   - A **~122-byte** extended frame (only in direct response to the poll command above),
     which contains everything the base frame does plus a 20-byte settings/configuration
     block appended before the final checksum byte.

There is also a small ~14-byte heartbeat/ack frame observed periodically; its contents are
not decoded and it can be ignored by consumers (filter on payload length >= 100 bytes).


.. _f2000_variant_firmware:

Telemetry field map
--------------------

Byte offsets are into the notification **value** as delivered by a BLE stack (i.e. *after*
stripping the ATT opcode and attribute handle — offset 0 is the first byte of the actual
characteristic value, which happens to start with ``09 ff`` as a frame-type marker).

======================================= ================================ ==========================================
Field                                   Offset(s)                        Notes
======================================= ================================ ==========================================
Battery percentage                      70                               Single byte, direct percentage.
Temperature (°C)                        66                               Single byte.
Firmware version                        47 (duplicated at 61)            Single byte; decode as ``".".join(str(byte))``
                                                                          (e.g. 215 -> "2.1.5"). Same convention as
                                                                          :attr:`SolixBLE.F2000.software_version` in
                                                                          the standard protocol. See
                                                                          :ref:`f2000_variant_firmware`.
AC output power (W)                     21-22, LE16                     Live-hardware re-test (AC fan load, cross-
                                                                          checked against the unit's own screen) found
                                                                          this matches the displayed wattage within 1W,
                                                                          and is unaffected by light bar changes - used
                                                                          by :attr:`~SolixBLE.F2000Alt.ac_output_power`.
                                                                          Originally implemented as a single byte
                                                                          (loads tested were all under 100W, so this
                                                                          wasn't caught) - a third-party owner's
                                                                          independently-built library documented this
                                                                          as 16-bit LE, and confirmed on their own
                                                                          hardware that values above 255W were being
                                                                          misread. Fixed to LE16. A DC-only load left
                                                                          this at 0. Previously thought to always read
                                                                          0 - that was only true because that earlier
                                                                          test had AC off.
AC + light bar output power (W)         41-42, LE16                     Same re-test found this equals offset 21 plus
                                                                          the light bar's own draw (+2W low, +3W medium,
                                                                          +4W high) - used by
                                                                          :attr:`~SolixBLE.F2000Alt.power_out`. A
                                                                          DC-only load left this unchanged too, so it
                                                                          does not include DC/car-socket output.
                                                                          Originally implemented as a single byte, same
                                                                          as offset 21 above and for the same reason
                                                                          (loads tested were under 100W) - fixed to
                                                                          LE16 alongside it.
                                                                          Previously documented as a light-bar status
                                                                          enum (off=0, low=2, medium=3, high=4) - that
                                                                          was a coincidental misread: the light-sweep
                                                                          test that produced those numbers had AC off,
                                                                          so this offset was showing 100% the light
                                                                          bar's own power draw, not a status code. The
                                                                          real light-bar mode readback is offset 118 in
                                                                          the settings block (see below), unrelated to
                                                                          this offset. SOS mode settles to a steady
                                                                          value equal to LOW's (2) at this offset,
                                                                          not an alternating one - see
                                                                          :ref:`f2000_alt_app_snoop_validation`.
Total output power (W), offset 17-18    17-18, LE16 (dup. 37-38)         Formerly used by :attr:`power_out`. The same
(meaning unidentified)                                                   re-test found this reads ~3.3x higher than
                                                                          the AC load actually measured (both by the
                                                                          screen and by offset 21/41 above), and does
                                                                          not respond to light bar power changes at
                                                                          all - it is not tracking real output power,
                                                                          contrary to the previous session's conclusion
                                                                          (which was based on a plausible-looking
                                                                          settle pattern during a DC load test, never
                                                                          cross-checked against the unit's own screen).
                                                                          Its real meaning is unidentified again.
AC input power while charging (W)       19-20, LE16                     Only nonzero while charging. Previously
                                                                          annotated "dup. 39-40" — confirmed wrong,
                                                                          see the "Total input power" row above:
                                                                          39-40 is AC + solar combined, not a
                                                                          duplicate, they only matched because every
                                                                          earlier test had solar disconnected.
Time remaining — discharge (hours)      17 (hours, ÷10) +               **Fixed — was reading the wrong offset
                                         18 (whole days), both           entirely.** Previously read offset 57-58
                                         single bytes                    as a 16-bit LE value, which was found
                                                                          completely frozen at the same raw value
                                                                          across 5 very different live conditions in
                                                                          one session (load 67W-287W, battery
                                                                          100%->99%, solar 0W-303W), while the
                                                                          unit's own screen moved a lot (16.4h -> 7h)
                                                                          over the same period — the real field lives
                                                                          elsewhere. An independent third-party
                                                                          implementation (a separate open-source HA
                                                                          integration for this exact device) reads
                                                                          offset 17 as hours (value ÷ 10) and offset
                                                                          18 as whole days — both single bytes, not
                                                                          related to offset 17-18 as a combined LE16
                                                                          pair (a different, still-unidentified
                                                                          field — see the note below the table).
                                                                          Verified against three live readings this
                                                                          session, paired with the unit's own screen
                                                                          at that exact moment: 16.5h (exact match),
                                                                          7.0h (exact match), 16.6h vs the screen's
                                                                          16.4h (small tolerance, same margin seen
                                                                          elsewhere in this project). Re-added to
                                                                          `HaSolixBLE`'s sensors now that it's
                                                                          confirmed. Still does **not** update for
                                                                          "time to full charge" while charging — that
                                                                          field is not yet located either.
AC output on/off                        63                               0/1.
AC/charging state                       68                               Not a simple mirror of byte 63 — observed
                                                                          values: 0 = idle, 1 = AC output active,
                                                                          2 = AC charging active. Also flips to 1
                                                                          when the "USB-C bottom" port (see below)
                                                                          is active, suggesting a shared power rail
                                                                          on the PCB between AC and that port.
AC power cable connected                65                               0 = no AC cable plugged in, 2 = AC cable
                                                                          plugged in. Confirmed to stay at 2 even
                                                                          once the battery reaches 100% and charge
                                                                          current has stopped — this tracks cable
                                                                          presence, not active charging current.
DC/Car socket output on/off             80, 81                           Both flip together in every test so far;
                                                                          only tested as a combined pair (this unit
                                                                          has two physical Car socket ports — not
                                                                          yet tested individually).
DC/Car socket port power (W) — port 1   33-34, LE16                     Cross-referenced from a third-party
                                                                          independently-built library (same source
                                                                          as the offset 21/41 fix), not yet confirmed
                                                                          against a live DC load on this project's
                                                                          own hardware — used by
                                                                          :attr:`~SolixBLE.F2000Alt.dc1_power`.
DC/Car socket port power (W) — port 2   35-36, LE16                     Same source/caveat as port 1 above — used by
                                                                          :attr:`~SolixBLE.F2000Alt.dc2_power`.
Solar input power (W)                   37-38, LE16                     Cross-referenced from a third-party
                                                                          independently-built library — used by
                                                                          :attr:`~SolixBLE.F2000Alt.solar_power_in`.
                                                                          **Confirmed live**: read 0 in every capture
                                                                          with no solar connected, then jumped to
                                                                          105W the moment a panel was actively
                                                                          producing power, matching a ~95W reading
                                                                          from the unit's own app/screen at the same
                                                                          moment. ``charging_status`` also flipped
                                                                          DISCHARGING → IDLE at the same time,
                                                                          consistent with solar roughly covering the
                                                                          concurrent 84W AC load.
Total input power (W), all sources      39-40, LE16                     Previously assumed to duplicate offset
combined                                                                 19-20 (AC input) because they always
                                                                          matched in testing (solar was always
                                                                          disconnected). **Confirmed live**: with AC
                                                                          input at 0 and solar input at 105W, this
                                                                          field read exactly 105W — genuinely AC +
                                                                          solar combined, not a duplicate. Used by
                                                                          :attr:`~SolixBLE.F2000Alt.power_in`.
External/expansion battery temp (°C)    67                               Cross-referenced from the same third-party
                                                                          source, not yet confirmed — no expansion
                                                                          battery available to test with. Used by
                                                                          :attr:`~SolixBLE.F2000Alt.external_battery_temperature`.
External/expansion battery %            71                               Same source/caveat as above — used by
                                                                          :attr:`~SolixBLE.F2000Alt.external_battery_percentage`.
                                                                          Read 0 in every capture so far, consistent
                                                                          with no expansion battery attached.
Total battery % (main + expansion)      72                               Same source — used by
                                                                          :attr:`~SolixBLE.F2000Alt.total_battery_percentage`.
                                                                          Matched :attr:`battery_percentage` (100) in
                                                                          every capture so far, consistent with a
                                                                          single-battery unit, though not a live
                                                                          confirmation of the offset itself.
USB-C port power (W) — port A           23-24, LE16                     Read as a single byte (max 255W) until
                                                                          this session cross-referenced the same
                                                                          third-party source and found the high byte
                                                                          (24) always read 0 in every reserved-byte
                                                                          sweep — the same silent-truncation pattern
                                                                          as the offset 21/41 bug. Fixed proactively;
                                                                          not yet independently confirmed with a load
                                                                          above 255W on this project's own hardware.
USB-C port power (W) — middle           25-26, LE16                     Same fix/caveat as port A above.
USB-C port power (W) — bottom           27-28, LE16                     Same fix/caveat as port A above.
USB-A port power (W) — top              29-30, LE16                     Same fix/caveat as port A above.
USB-A port power (W) — bottom           31-32, LE16                     Same fix/caveat as port A above.
USB-C port active — port A              75
USB-C port active — middle              76
USB-C port active — bottom              77
USB-A port active — top                 78
USB-A port active — bottom              79
Serial number (ASCII)                   85-100
Checksum                                Last byte (101 for ~102-byte     Not a sensor value; changes whenever the
                                         frames, 121 for ~122-byte)       rest of the frame content changes.
======================================= ================================ ==========================================

.. note::
    "USB-C port A" was the first port tested and its physical position (top/middle/bottom) was
    not recorded at the time — the middle and bottom ports were identified afterward and are
    confirmed. By elimination it is most likely the remaining ("top") port, but this has not
    been independently re-verified.

Offsets 21 and 41 are now identified as AC-only and AC+light-bar output power respectively -
see the field map above. Offset 17-18 (this library's ``power_out`` field until this
correction) does not track real output power; its actual meaning is unidentified again.


Settings/configuration block
-----------------------------

Only present in the ~122-byte frame returned in direct response to the poll command (not in
passive pushes). Starts immediately after the base ~102-byte telemetry content.

======================================= ================= ==========================================
Field                                   Offset(s)         Notes
======================================= ================= ==========================================
AC charging power limit (W)             101-102, LE16     Verified exact match (1440).
Display timeout (seconds)               105-106, LE16     Verified exact match (60 → 30).
Display brightness                      115               Verified exact match (1=low → 2=medium).
Power saving mode enabled               117               0=off, 1=on. Confirmed via two full live
                                                            ON/OFF cycles producing a clean 0/1/0/1/0
                                                            pattern - the only offset in the frame that
                                                            did. Used by
                                                            :attr:`~SolixBLE.F2000Alt.power_saving_mode_enabled`.
Light bar mode                          118               0=off, 1=low, 2=medium, 3=high, 4=SOS.
                                                            Matches :class:`~SolixBLE.states.LightStatus`
                                                            exactly. Verified across all 5 states.
Temperature display unit                119               0=Celsius, 1=Fahrenheit. Matches
                                                            :class:`~SolixBLE.states.TemperatureUnit`
                                                            exactly.
======================================= ================= ==========================================

Unidentified in this block: bytes 103, 107, 116 (constant ``60`` in every capture so far) and
bytes 109, 111 (constant ``1``). Candidates not yet tested: AC auto-off timer, DC auto-off
timer. The power saving mode *control command* (see :ref:`f2000_alt_control`) and its
readback (offset 117, see the field map above) have both since been confirmed.


.. _f2000_alt_control:

Control commands
-----------------

Captured by repeating the capture methodology above while driving control (not just
monitoring) from the Anker app — same HCI snoop technique, but toggling outputs/settings
instead of just viewing status. All four below have been verified byte-for-byte against
``SolixBLE``'s own command construction and against real hardware.

Every control command shares the same shape as :data:`CMD_POLL_TELEMETRY`, written to
``00007777...`` write-without-response:

======================= ===================================================
Prefix (6 bytes)        ``08ee000000 02`` (``02`` marks this as a control command,
                         vs. ``01`` for the poll command)
Field ID (1 byte)       Selects which control is being set — see table below
Length (1 byte)         Total frame length in bytes, including this byte and the
                         trailing checksum. Always ``0x0b`` (11) for every command
                         implemented so far, since all four are single-byte on/off/
                         mode values with a fixed 2-byte parameter section — this
                         looked like a fixed constant (previously documented as
                         "Middle (2 bytes): fixed 0b00") until a third-party
                         independently-built library's command definitions showed
                         it's a genuine length field, confirmed by checking all 8 of
                         its command types (11 for on/off/mode, 12 for
                         recharge-power/screen-timeout, 14 for AC/12V timers - see
                         issue #10). Not yet an issue for any command actually
                         implemented here — only matters once a longer command
                         (timers, recharge power, screen brightness/timeout) is
                         added, at which point this byte must be computed rather
                         than hardcoded.
Parameters (2+ bytes)   A reserved/padding byte (``0x00``) followed by the value
                         being set. 2 bytes total for every command implemented so
                         far; longer for commands not yet implemented (see above).
Checksum (1 byte)       Unweighted sum of all preceding bytes, mod 256 — **not**
                         the XOR checksum used by the encrypted-protocol devices
                         (:meth:`SolixBLEDevice._checksum`)
======================= ===================================================

======================= ============ =====================================
Control                 Field ID     Value
======================= ============ =====================================
AC output on/off        ``0x86``     ``0x01`` = on, ``0x00`` = off. Confirmed
                                      live end-to-end via
                                      :meth:`~SolixBLE.F2000Alt.turn_ac_on`/
                                      :meth:`~SolixBLE.F2000Alt.turn_ac_off` against
                                      real hardware — the base-frame AC output flag
                                      (offset 63) flips immediately in both directions.
DC/Car socket on/off    ``0x87``     ``0x01`` = on, ``0x00`` = off. Confirmed live
                                      end-to-end via :meth:`~SolixBLE.F2000Alt.turn_dc_on`/
                                      :meth:`~SolixBLE.F2000Alt.turn_dc_off` against real
                                      hardware with a real 12V load (portable vacuum)
                                      connected — the vacuum itself powered on/off with the
                                      command, the base-frame DC output flag (offset 80/81)
                                      flipped 0/1 in lockstep, and offset 17-18 (LE16) showed
                                      a clear startup-inrush-then-settle current pattern while
                                      the vacuum ran (later found to not actually track real
                                      output power — see the field map above; this DC test also
                                      showed offsets 21 and 41 both staying at 0 throughout,
                                      consistent with them being AC-only/AC+light fields that
                                      don't include DC output). Not to be confused with the
                                      field ``0x8a`` right below, which was initially (and
                                      incorrectly) assumed to be this control.
Power saving mode       ``0x8a``     ``0x01`` = on, ``0x00`` = off. Originally guessed to be
                                      DC/Car socket output based on testing order (right after
                                      AC) and adjacency to the AC field ID, but that guess was
                                      **wrong** — with the real load test above, ``0x87`` (not
                                      ``0x8a``) is what actually drives the DC/car socket port.
                                      ``0x8a`` was confirmed by direct observation to instead
                                      toggle the device's own power-saving-mode indicator.
                                      Exposed as
                                      :meth:`~SolixBLE.F2000Alt.turn_power_saving_mode_on`/
                                      :meth:`~SolixBLE.F2000Alt.turn_power_saving_mode_off`.
                                      Its telemetry readback was later found too: offset 117
                                      in the settings block (see the field map above), exposed
                                      as :attr:`~SolixBLE.F2000Alt.power_saving_mode_enabled`.
Light bar mode           ``0x8b``     Matches :class:`~SolixBLE.states.LightStatus`
                                      exactly: ``0``\=off, ``1``\=low, ``2``\=medium,
                                      ``3``\=high, ``4``\=SOS. Confirmed live end-to-end
                                      via :meth:`~SolixBLE.F2000Alt.set_light_mode`
                                      against real hardware. The original test for this
                                      cycled low/medium/high/off and observed offset 41-42 in
                                      the base frame track each change (low=2, medium=3,
                                      high=4, off=0), which was read at the time as a
                                      light-bar status enum. A later re-test with an AC
                                      load also running found offset 41-42 = AC output power
                                      (offset 21-22) **plus** those same +2/+3/+4 values — so
                                      the original test's numbers were real power draw
                                      (watts) from the light bar itself, not a status code;
                                      offset 41-42 just happened to equal the light's own
                                      wattage because AC was off at the time, making it look
                                      like a clean enum. The actual light-bar mode readback
                                      is offset 118 in the settings block (see above), which
                                      is unrelated to offset 41-42. SOS was re-tested twice: a
                                      live ~15s raw-frame log while the light visibly blinked
                                      produced no distinguishable offset 41-42 value at that
                                      polling rate; a later real HCI-snoop capture of the
                                      official app (full/unfiltered, not rate-limited by
                                      polling) resolved this - offset 41-42 settles to a
                                      **steady** value equal to LOW's (2), not an alternating
                                      one, for the whole SOS window. Most likely explanation:
                                      whatever this field samples/averages, SOS's effective
                                      power draw over that window equals LOW's steady draw,
                                      even though the light itself visibly blinks.
======================= ============ =====================================

.. _f2000_alt_app_snoop_validation:

Independent validation against the official app
-------------------------------------------------

All of the above was re-verified byte-for-byte against a real HCI snoop capture of the
official Anker app (not this library) driving a unit through AC on/off, DC on/off, power
saving on/off, and all five light modes. Every command the app sent matched this library's
own command construction exactly - same field ID, same value, same checksum:

======================= ===================================================
App command (hex)      Decoded
======================= ===================================================
``08ee00000002860b00018a``   AC on (field ``0x86``, value ``0x01``)
``08ee00000002860b000089``   AC off
``08ee00000002870b00018b``   DC/car socket on (field ``0x87``, value ``0x01``)
``08ee00000002870b00008a``   DC/car socket off
``08ee000000028a0b00018e``   Power saving on (field ``0x8a``, value ``0x01``)
``08ee000000028a0b00008d``   Power saving off
``08ee000000028b0b00008e``   Light off (field ``0x8b``, value ``0x00``)
``08ee000000028b0b00018f``   Light low (value ``0x01``)
``08ee000000028b0b000290``   Light medium (value ``0x02``)
``08ee000000028b0b000391``   Light high (value ``0x03``)
``08ee000000028b0b000492``   Light SOS (value ``0x04``)
======================= ===================================================

The capture methodology used here (and the one that produces a *usable* capture, unlike an
earlier attempt this session that captured only truncated packets - see
``examples/parse_hci_snoop.py``'s docstring) is: Developer options → Bluetooth HCI snoop log
→ **Full** (not the default "Filtered" mode, which redacts most payload data), then a bug
report taken shortly after the app session.

Known unknowns
---------------

- **Time to full charge** — the app displays this, but it is not the same field as "time
  remaining" (byte 57-58 stays fixed at its last discharge estimate while charging). Not
  located.
- Bytes 8-16, 43-46, 59-60, 62, 64, 69, 73-74, 82-84 — read as ``0`` in every test
  performed. Either unused/reserved, or fields for states not yet triggered (e.g.
  per-port negotiated voltage/current, error/fault codes). Offsets 21/41 (AC output /
  AC + light bar power), 24/26/28/30/32 (USB port power high bytes), 33-36 (DC port
  power), 37-38 (solar input), 39-40 (total input), 67 (external battery temp), and 71
  (external battery %) have all since been identified — see the field map above — and
  moved out of this list. Offsets 37-38 and 39-40 (solar input / total input) are now
  **confirmed live** — see their rows above. The rest still read ``0`` in every capture
  taken so far for the same underlying reason: either a high byte that's genuinely 0
  below 256W, or a field with nothing to report yet (no expansion battery attached) —
  not evidence the offsets themselves are wrong.
- What offset 17-18 (LE16, i.e. read as one combined 16-bit value) actually represents is
  still unidentified — see the field map above. It moves in response to load
  (startup-inrush-then-settle pattern) but does not match real output power in either
  magnitude or behavior. Likely explanation, given offset 17 and offset 18 were separately
  identified this session as the real hours-remaining/days-remaining fields (see the "Time
  remaining" row above): a combined LE16 read of those same two bytes would naturally track
  *something* real (a discharge-time estimate that legitimately changes with load) without
  meaning anything as a single 16-bit number — this note predates that finding and is kept
  for the historical record, not because the mystery independently reproduces elsewhere.
- Fixed constant bytes 47, 49, 51, 53, 61 — never observed to change; purpose unknown
  (possibly a device/model/protocol-version identifier). Byte 72 was previously listed here
  too — since identified as :attr:`~SolixBLE.F2000Alt.total_battery_percentage`, see the
  field map above.
- Settings block bytes 103, 107, 109, 111, 116 — see above.
- The two Car socket outputs (bytes 80/81) have only been observed as a pair, never
  independently. They are now confirmed to flip together 0/1 with DC/Car socket output
  (field ``0x87``, see Control commands) under a real 12V load (portable vacuum).
- Display on/off, AC/DC auto-off timers, and AC charging power limit control commands have
  not been captured yet. Power saving mode's control command has been captured, but its
  telemetry readback byte has not.


Reference implementation
--------------------------

:class:`~SolixBLE.F2000Alt` (see :doc:`f2000_alt`) is a proper library device class
implementing everything in this document, following the same public interface
(``connect()``, ``disconnect()``, properties, callbacks) as :class:`~SolixBLE.F2000` and the
rest of the library - verified working end to end against real hardware, including
``discover_devices()`` finding the device (it required adding a second identifier UUID,
:data:`SolixBLE.const.UUID_IDENTIFIER_F2000_ALT`, since this variant doesn't advertise the
UUID the library normally scans for).

The example scripts used to originally reverse-engineer and prototype this protocol are
still in ``examples/`` for reference: ``test_f2000.py``, ``live_telemetry.py`` (minimal raw
poll/print), and ``monitor_recharge.py`` (continuous polling loop with charge-complete
detection) - but ``F2000Alt`` is the one to actually build on.
