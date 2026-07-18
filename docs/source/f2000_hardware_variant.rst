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

It is not currently known exactly what distinguishes hardware/firmware revisions that speak
this protocol from ones that speak the standard encrypted protocol — only one unit has been
examined so far. If you own a 767 PowerHouse, the methods below (ordered from easiest/most
reliable to more speculative) let you check which protocol yours speaks.


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

**4. Weaker, single-sample clues** (not confirmed as reliable — only one unit examined):

- BLE MAC address OUI ``E8:EE:CC:...`` (identifies the Bluetooth chip vendor used in this unit).
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
Total output power (W)                  41 (duplicated at 21)            Sum of all active outputs (AC+DC+USB+light).
AC input power while charging (W)       19-20, LE16 (dup. 39-40)         Only nonzero while charging.
Time remaining — discharge (hours)      57-58, LE16, value ÷ 10          Does **not** update for "time to full charge"
                                                                          while charging — that field is not yet
                                                                          located.
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
USB-C port power (W) — port A           23
USB-C port power (W) — middle           25
USB-C port power (W) — bottom           27
USB-A port power (W) — top              29
USB-A port power (W) — bottom           31
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

Bytes 17-18 (and their duplicate at 37-38) fluctuate on every poll regardless of load
(observed with literally nothing connected to any output) and are **not understood**. They
were ruled out as an output-power reading by comparing readings with vs. without a known load.


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
Light bar mode                          118               0=off, 1=low, 2=medium, 3=high, 4=SOS.
                                                            Matches :class:`~SolixBLE.states.LightStatus`
                                                            exactly. Verified across all 5 states.
Temperature display unit                119               0=Celsius, 1=Fahrenheit. Matches
                                                            :class:`~SolixBLE.states.TemperatureUnit`
                                                            exactly.
======================================= ================= ==========================================

Unidentified in this block: bytes 103, 107, 116 (constant ``60`` in every capture so far) and
bytes 109, 111 (constant ``1``). Candidates not yet tested: AC auto-off timer, DC auto-off
timer, power-saving mode toggle.


Known unknowns
---------------

- **Time to full charge** — the app displays this, but it is not the same field as "time
  remaining" (byte 57-58 stays fixed at its last discharge estimate while charging). Not
  located.
- Bytes 8-16, 22, 24, 26, 28, 30, 32-38, 42-46, 59-60, 62, 64, 67, 69, 71, 73-74, 82-84 —
  read as ``0`` in every test performed. Either unused/reserved, or fields for states not
  yet triggered (e.g. battery health %, expansion battery data, per-port negotiated
  voltage/current, error/fault codes).
- Fixed constant bytes 47, 49, 51, 53, 61, 72 — never observed to change; purpose unknown
  (possibly a device/model/protocol-version identifier).
- Settings block bytes 103, 107, 109, 111, 116 — see above.
- The two Car socket outputs (bytes 80/81) have only been tested as a pair, never
  independently.
- **Control commands are not yet captured.** Every finding above comes from observing
  telemetry in response to physical button presses / app-driven display changes — the actual
  BLE write payloads the app uses to *command* the device (turn AC/DC/light on/off remotely)
  have not been captured. This would require repeating the capture methodology above while
  driving control (not just monitoring) from the Anker app.


Reference implementation
--------------------------

A working, standalone (not yet integrated into the :class:`~SolixBLE.F2000` class) decoder
implementing everything in this document is in ``examples/test_f2000.py`` in the project
repository, along with ``examples/live_telemetry.py`` (minimal raw poll/print) and
``examples/monitor_recharge.py`` (continuous polling loop with charge-complete detection).
