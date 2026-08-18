"""F2000(P) / 767 PowerHouse power station model - alternate hardware variant.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
from datetime import datetime, timedelta

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus, LightStatus, PortStatus, TemperatureUnit

#: Vendor GATT service exposed by this hardware variant. Different from the
#: standard F2000's encrypted-protocol service.
UUID_SERVICE = "014bf5da-0000-1000-8000-00805f9b34fb"

#: Write characteristic (write-without-response). Commands are sent here.
UUID_COMMAND = "00007777-0000-1000-8000-00805f9b34fb"

#: Notify characteristic. Telemetry is pushed here, both passively and in
#: direct response to a poll command.
UUID_TELEMETRY = "00008888-0000-1000-8000-00805f9b34fb"

#: Sent to request a telemetry update. Triggers an extended (~122 byte)
#: response containing the settings block, in addition to base telemetry.
CMD_POLL_TELEMETRY = bytes.fromhex("08ee00000001010a0002")

#: Common prefix for all control (as opposed to poll) commands.
_CMD_CONTROL_PREFIX = bytes.fromhex("08ee00000002")

#: Field IDs for the byte following :data:`_CMD_CONTROL_PREFIX` in a control
#: command, identifying which control is being set.
_FIELD_AC_OUTPUT = 0x86
_FIELD_DC_OUTPUT = 0x87
_FIELD_POWER_SAVING_MODE = 0x8A
_FIELD_LIGHT_MODE = 0x8B

#: Minimum notification length to be considered a real telemetry frame,
#: filtering out the small ~14 byte StateAck frames this device also
#: sends (see :data:`_STATE_ACK_TELEMETRY_ID` - these used to be assumed
#: to be no-op heartbeat noise and were discarded unread; they aren't,
#: see issue #9).
_MIN_TELEMETRY_LENGTH = 100

#: Byte at offset 6 identifying a StateAck packet - sent whenever a
#: physical button on the unit is pressed (or a command changes output/
#: LED state), carrying just the changed state rather than a full
#: telemetry frame. Cross-referenced from two independent third-party
#: libraries for this device (see issue #9); not yet confirmed against
#: this project's own hardware.
_STATE_ACK_TELEMETRY_ID = 0x48

#: Minimum length to safely read every StateAck field below.
_MIN_STATE_ACK_LENGTH = 13

#: Minimum length for the *extended* frame (base telemetry + settings block),
#: only sent in direct response to :data:`CMD_POLL_TELEMETRY`.
_MIN_EXTENDED_LENGTH = 120

_LOGGER = logging.getLogger(__name__)

_LIGHT_MODES = {
    0: LightStatus.OFF,
    1: LightStatus.LOW,
    2: LightStatus.MEDIUM,
    3: LightStatus.HIGH,
    4: LightStatus.SOS,
}

_DISPLAY_BRIGHTNESS = {
    0: LightStatus.OFF,
    1: LightStatus.LOW,
    2: LightStatus.MEDIUM,
    3: LightStatus.HIGH,
}


class F2000Alt(SolixBLEDevice):
    """
    F2000(P) Power Station - alternate hardware variant.

    Some 767 PowerHouse units do not implement the encrypted protocol used by
    :class:`~SolixBLE.F2000` (and most other devices in this library). This
    class implements the alternate, unencrypted request/notify protocol
    those units speak instead, reverse-engineered from a Bluetooth HCI snoop
    capture of the official Anker app. See
    :doc:`the hardware variant documentation </f2000_hardware_variant>` for
    the full byte-level field map, capture methodology, and how to tell
    which variant a given unit has.

    .. note::
        This class does not share :class:`~SolixBLE.F2000`'s connection
        negotiation, encryption, or telemetry framing - it overrides
        :meth:`connect` entirely rather than reusing that machinery, since
        this device's transport is fundamentally different (no encryption,
        different GATT characteristics, fixed-offset payload instead of a
        TLV scheme).

    .. note::
        Control commands (AC output, DC/Car socket output, power saving mode,
        light bar mode) have been captured and confirmed working against real
        hardware - see :doc:`the hardware variant documentation
        </f2000_hardware_variant>` for the command format. Display, timers,
        and AC charging power have not been captured yet.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._extended_data: bytes | None = None
        self._handshake_done: bool = False
        self._first_frame_event: asyncio.Event = asyncio.Event()

    async def connect(self, max_attempts: int = 3, run_callbacks: bool = True) -> bool:
        """Connect to device.

        Unlike the base implementation this performs no encrypted session
        negotiation - it subscribes to telemetry notifications, sends one
        poll command, and waits for the first response.

        :param max_attempts: Maximum number of attempts to try to connect (default=3).
        :param run_callbacks: Execute registered callbacks on successful connection (default=True).
        """
        self._connection_attempts = self._connection_attempts + 1
        self._handshake_done = False
        self._first_frame_event = asyncio.Event()

        try:
            if self._client is not None:
                await self._dispose_of_client()

            self._reset_session(reset_data=False)

            self._client = await establish_connection(
                BleakClient,
                device=self._ble_device,
                name=self.address,
                max_attempts=max_attempts,
                use_services_cache=False,
                disconnected_callback=self._disconnect_callback,
            )
        except BleakError:
            _LOGGER.exception(
                f"Error establishing initial connection to '{self.name}'!"
            )

        if not self.connected:
            _LOGGER.error(
                f"Failed to establish initial connection to '{self.name}' on attempt {self._connection_attempts}!"
            )
            return False

        try:
            _LOGGER.debug(f"Subscribing to notifications from device '{self.name}'!")
            await self._client.start_notify(UUID_TELEMETRY, self._on_notify)
        except BleakError:
            _LOGGER.exception(f"Error subscribing to notifications from '{self.name}'!")
            return False

        try:
            await self._client.write_gatt_char(
                UUID_COMMAND, CMD_POLL_TELEMETRY, response=False
            )
            async with asyncio.timeout(10):
                await self._first_frame_event.wait()
        except (TimeoutError, BleakError):
            _LOGGER.exception(f"Timed out waiting for telemetry from '{self.name}'!")
            return False

        self._handshake_done = True
        self._connection_attempts = 0

        if self._disconnect_event.is_set():
            self._disconnect_event.clear()

        try:
            await self._post_connect()
        except Exception:
            _LOGGER.exception(f"Error running post-connect setup for '{self.name}'!")

        if self._auto_reconnect_task is None:
            self._auto_reconnect_task = asyncio.create_task(self._auto_reconnect())

        if run_callbacks:
            self._run_state_changed_callbacks()

        return True

    def _on_notify(self, sender, data: bytearray) -> None:
        """Handle an incoming telemetry notification.

        Base telemetry (present in every real frame) updates :attr:`_data`;
        the settings block (only present in the extended ~122 byte response
        to a poll) updates :attr:`_extended_data` separately, so a later
        small passive push doesn't wipe out settings-block properties.

        Small (~14 byte) StateAck frames - previously assumed to be no-op
        heartbeat noise and discarded unread - are handled separately by
        :meth:`_handle_state_ack` before the length check below, since they
        carry real state (see issue #9).
        """
        if (
            len(data) >= _MIN_STATE_ACK_LENGTH
            and len(data) < _MIN_TELEMETRY_LENGTH
            and data[6] == _STATE_ACK_TELEMETRY_ID
        ):
            self._handle_state_ack(data)
            return

        if len(data) < _MIN_TELEMETRY_LENGTH:
            return

        self._data = bytes(data)
        self._last_data_timestamp = datetime.now()

        if len(data) >= _MIN_EXTENDED_LENGTH:
            self._extended_data = bytes(data)

        self._first_frame_event.set()
        self._run_state_changed_callbacks()

    def _handle_state_ack(self, data: bytearray) -> None:
        """Handle a StateAck notification (physical button press or command ack).

        Patches the affected bytes into the already-cached :attr:`_data`/
        :attr:`_extended_data` frames, at the same offsets the relevant
        properties already read, rather than replacing the whole frame -
        a StateAck only carries 4 changed fields, not a full telemetry
        snapshot. No-ops if a frame hasn't been cached yet (nothing to
        patch onto until the first real poll response arrives).

        .. note::
            Cross-referenced from two independent third-party libraries for
            this device, not yet confirmed against this project's own
            hardware - see issue #9. The DC/car-socket pair (offset 80/81)
            is patched from a single StateAck bit, consistent with this
            project's own finding that they always move together (see
            :attr:`dc_output`) - if that assumption is ever found wrong
            (issue #4), this will need to change too.
        """
        ac_outlet_on = data[9]
        twelve_volt_on = data[10]
        power_save_on = data[11]
        led_state = data[12]

        if self._data is not None:
            patched = bytearray(self._data)
            if len(patched) > 63:
                patched[63] = ac_outlet_on
            if len(patched) > 81:
                patched[80] = twelve_volt_on
                patched[81] = twelve_volt_on
            self._data = bytes(patched)

        if self._extended_data is not None:
            patched_extended = bytearray(self._extended_data)
            if len(patched_extended) > 117:
                patched_extended[117] = power_save_on
            if len(patched_extended) > 118:
                patched_extended[118] = led_state
            self._extended_data = bytes(patched_extended)

        self._last_data_timestamp = datetime.now()
        self._run_state_changed_callbacks()

    async def get_status_update(self) -> None:
        """Request a fresh status update, including the settings block.

        Settings-block properties (:attr:`ac_charging_power`,
        :attr:`display_timeout_seconds`, :attr:`display_mode`, :attr:`light`,
        :attr:`temperature_unit`) are only populated by the extended response
        to this poll, not by ordinary passive telemetry pushes.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        """
        if not self.connected:
            raise ConnectionError(f"Not connected to '{self.name}'!")

        event = asyncio.Event()
        original_notify = self._on_notify

        def _wait_for_extended(sender, data: bytearray) -> None:
            original_notify(sender, data)
            if len(data) >= _MIN_EXTENDED_LENGTH:
                event.set()

        await self._client.stop_notify(UUID_TELEMETRY)
        await self._client.start_notify(UUID_TELEMETRY, _wait_for_extended)
        try:
            await self._client.write_gatt_char(
                UUID_COMMAND, CMD_POLL_TELEMETRY, response=False
            )
            async with asyncio.timeout(10):
                await event.wait()
        finally:
            await self._client.stop_notify(UUID_TELEMETRY)
            await self._client.start_notify(UUID_TELEMETRY, self._on_notify)

    @property
    def negotiated(self) -> bool:
        """Has the initial handshake (subscribe + first telemetry) completed.

        This device has no encrypted session to negotiate; this reflects
        connection + first-frame-received instead, so the base class's
        :attr:`available` property and automatic-reconnect logic (both of
        which depend on this) work correctly.

        :returns: True/False if connected and handshake has completed.
        """
        return self.connected and self._handshake_done

    def _byte(self, offset: int, extended: bool = False) -> int:
        data = self._extended_data if extended else self._data
        if data is None or len(data) <= offset:
            return DEFAULT_METADATA_INT
        return data[offset]

    def _le16(self, offset: int, extended: bool = False) -> int:
        data = self._extended_data if extended else self._data
        if data is None or len(data) < offset + 2:
            return DEFAULT_METADATA_INT
        return int.from_bytes(data[offset : offset + 2], "little")

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._byte(70)

    @property
    def external_battery_percentage(self) -> int:
        """Expansion/external battery percentage, if one is attached.

        .. note::
            Offset cross-referenced from a third-party independently-built
            library, not yet confirmed on this project's own hardware (no
            expansion battery available to test with).

        :returns: External battery percentage or default int value.
        """
        return self._byte(71)

    @property
    def total_battery_percentage(self) -> int:
        """Combined battery percentage across main + any expansion battery.

        .. note::
            Offset cross-referenced from a third-party independently-built
            library, not yet confirmed on this project's own hardware.

        :returns: Total battery percentage or default int value.
        """
        return self._byte(72)

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C or default int value.
        """
        return self._byte(66)

    @property
    def external_battery_temperature(self) -> int:
        """Expansion/external battery temperature (C), if one is attached.

        .. note::
            Offset cross-referenced from a third-party independently-built
            library, not yet confirmed on this project's own hardware (no
            expansion battery available to test with).

        :returns: External battery temperature or default int value.
        """
        return self._byte(67)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        value = self._byte(47)
        if value == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_STRING
        return ".".join(str(value))

    @property
    def power_out(self) -> int:
        """AC output + light bar power combined (watts).

        .. note::
            Previously read offset 17-18, based on a DC-only (vacuum) load
            test that was never actually cross-checked against the unit's
            own screen. A later live session, with the unit's screen visible
            during an AC (fan) load test, found offset 17-18 reads ~3.3x too
            high and does not respond to light-bar power changes - it does
            not track real output power. Offset 41 does: it matched the
            screen's displayed wattage within 1W under an AC load, and
            tracked exact +2/+3/+4W increments as the light bar was set to
            LOW/MEDIUM/HIGH on top of that - consistent with the light bar's
            own real power draw. This also reconciles two earlier sessions'
            tests that looked contradictory: a DC-only (vacuum) test where
            this offset stayed constant (AC and light were both off, and
            this offset doesn't include DC/car-socket output), and an
            idle-except-light sweep where it tracked 0/2/3/4 exactly
            (with AC off, that was 100% the light bar's own draw). See
            :attr:`ac_output_power` for the AC-only component (offset 21),
            and :doc:`/f2000_hardware_variant` for the full writeup.

        .. warning::
            Does **not** include DC/car-socket output - a real DC load left
            this value unchanged in testing. There is currently no known
            field that sums every output (AC + DC + light + USB); this is
            the closest available approximation.

        .. note::
            Read as a single byte (max 255W) until a community report
            (a third-party owner's independently-verified library plus
            direct confirmation on their own hardware - see GitHub issue
            tracker) identified this as a 16-bit LE field at offset 41-42,
            matching the sibling field at offset 21-22. All values observed
            during this project's own live testing were under 100W, so the
            high byte (42) was always 0 and the single-byte read happened
            to produce the same result - meaning this was silently wrong
            for any load at or above 256W, not caught by testing so far.

        :returns: AC + light bar power out or default int value.
        """
        return self._le16(41)

    @property
    def ac_output_power(self) -> int:
        """AC output power only, excluding the light bar (watts).

        Confirmed via a live-hardware test: matched the unit's own screen
        display within 1W under a real AC (fan) load, and was unaffected by
        light bar mode changes that did move :attr:`power_out`. Does not
        include DC/car-socket or light bar output. See
        :doc:`/f2000_hardware_variant` for the full writeup.

        .. note::
            Read as a single byte (max 255W) until a community report
            identified this as a 16-bit LE field spanning offset 21-22 -
            see the note on :attr:`power_out` for the full story. All
            values observed during this project's own live testing were
            under 100W, so this was silently wrong above 256W without
            being caught by testing so far.

        :returns: AC output power or default int value.
        """
        return self._le16(21)

    @property
    def ac_power_in(self) -> int:
        """AC Power In while charging (watts).

        :returns: AC power in or default int value.
        """
        return self._le16(19)

    @property
    def solar_power_in(self) -> int:
        """Solar input power (watts).

        Offset cross-referenced from a third-party independently-built
        library (the same source that identified the offset 21/41 16-bit
        LE bug - see the note on :attr:`power_out`). Confirmed live: read
        0 in every capture with no solar connected, then jumped to 105W
        the moment a panel was actively producing power, matching a ~95W
        reading from the unit's own app/screen at the same moment (small
        gap, same order of magnitude - the first movement this field
        showed all session). :attr:`charging_status` also flipped from
        ``DISCHARGING`` to ``IDLE`` at the same time, consistent with
        solar (105W) roughly covering the concurrent AC load (84W).

        :returns: Solar power in or default int value.
        """
        return self._le16(37)

    @property
    def power_in(self) -> int:
        """Total input power, all sources combined (watts).

        This project's docs previously assumed this offset duplicated
        :attr:`ac_power_in` (offset 19-20), because they always matched in
        testing - every test run here so far had solar disconnected, which
        would make the two indistinguishable. Confirmed distinct live: with
        :attr:`ac_power_in` at 0 and :attr:`solar_power_in` at 105W, this
        field read exactly 105W (``0 + 105``) - genuinely AC + solar
        combined, not a duplicate.

        :returns: Total power in or default int value.
        """
        return self._le16(39)

    @property
    def time_remaining(self) -> float:
        """Time remaining to empty, on battery discharge, in hours.

        .. note::
            **Fixed - was reading the wrong offset entirely.** Previously
            read offset 57-58 as a 16-bit LE value, which was found
            completely frozen across wildly different live conditions in
            one session (load 67W-287W, battery 100%->99%, solar 0W-303W)
            while the unit's own screen moved a lot (16.4h -> 7h). An
            independent third-party implementation (a separate open-source
            HA integration for this exact device) reads this field as two
            *single bytes*: offset 17 (hours, value/10) and offset 18
            (whole days) - not related to offset 17-18 as a combined LE16
            pair, which is a different, still-unidentified field. Verified
            against three live readings captured earlier this session,
            paired with the unit's own screen at that exact moment: 16.5h
            (exact match), 7.0h (exact match), and 16.6h vs the screen's
            16.4h (same small tolerance seen elsewhere in this project).
            See :doc:`/f2000_hardware_variant` for the full writeup.

        .. note::
            This does not reflect "time to full charge" while charging - it
            keeps showing the last discharge estimate. That field has not
            been located yet.

        :returns: Hours remaining or default float value.
        """
        hours = self._byte(17)
        days = self._byte(18)
        if hours == DEFAULT_METADATA_INT or days == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_FLOAT
        return round(days * 24 + hours / 10.0, 1)

    @property
    def hours_remaining(self) -> float:
        """Time remaining to empty, in hours.

        Note that any hours over 24 are overflowed to the days remaining.
        Use :attr:`time_remaining` if you want days included.

        :returns: Hours remaining or default float value.
        """
        total = self.time_remaining
        if total == DEFAULT_METADATA_FLOAT:
            return DEFAULT_METADATA_FLOAT
        return round(divmod(total, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        """Time remaining to empty, in whole days.

        Note that any partial days are overflowed into the hours remaining.
        Use :attr:`time_remaining` if you want hours included.

        :returns: Days remaining or default int value.
        """
        total = self.time_remaining
        if total == DEFAULT_METADATA_FLOAT:
            return DEFAULT_METADATA_INT
        return round(divmod(total, 24)[0])

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be empty (discharge estimate only).

        :returns: Timestamp of when will be empty or None.
        """
        total = self.time_remaining
        if total == DEFAULT_METADATA_FLOAT:
            return None
        return datetime.now() + timedelta(hours=total)

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        :returns: Status of the AC port.
        """
        value = self._byte(63)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def ac_cable_connected(self) -> bool | None:
        """Whether an AC power cable is physically connected.

        Confirmed to track cable presence, not active charging current - it
        stays true even once the battery reaches 100% and charge current has
        dropped to zero.

        :returns: True if an AC cable is connected, False if not, or default bool value.
        """
        value = self._byte(65)
        if value == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_BOOL
        return value != 0

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        .. note::
            ``DISCHARGING`` here specifically means "AC output is actively
            delivering power" (this variant has no solar input in scope),
            not solar-insufficient discharge as on other models.

        :returns: Status of charging.
        """
        value = self._byte(68)
        if value == DEFAULT_METADATA_INT:
            return ChargingStatus.UNKNOWN
        try:
            return ChargingStatus(value)
        except ValueError:
            return ChargingStatus.UNKNOWN

    @property
    def dc_output(self) -> PortStatus:
        """DC / Car socket output status.

        .. note::
            This unit has two physical Car socket ports, but they have only
            ever been observed flipping together - not yet confirmed whether
            they're independently controllable.

        :returns: Status of the DC output.
        """
        value = self._byte(80)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def dc1_power(self) -> int:
        """DC/Car socket port 1 power (watts).

        .. note::
            Offset cross-referenced from a third-party independently-built
            library, not yet confirmed against a live DC load on this
            project's own hardware.

        :returns: DC port 1 power or default int value.
        """
        return self._le16(33)

    @property
    def dc2_power(self) -> int:
        """DC/Car socket port 2 power (watts).

        .. note::
            Offset cross-referenced from a third-party independently-built
            library, not yet confirmed against a live DC load on this
            project's own hardware.

        :returns: DC port 2 power or default int value.
        """
        return self._le16(35)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB-C port 1 status.

        .. note::
            Physical position (top/middle/bottom) not confirmed for this
            specific port - see the hardware variant docs.

        :returns: Status of the USB-C 1 port.
        """
        value = self._byte(75)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def usb_c1_power(self) -> int:
        """USB-C port 1 power (watts).

        .. note::
            Read as a single byte (max 255W) until this session cross-
            referenced a third-party library's field map (the same source
            that identified the offset 21/41 bug - see the note on
            :attr:`power_out`) and found this offset pair documented as
            16-bit LE. The high byte (24) was always 0 in every reserved-
            byte sweep performed so far - the exact same silent-truncation
            pattern as the confirmed offset 21/41 bug - so fixed
            proactively, though not yet independently confirmed with a
            load above 255W on this project's own hardware.

        :returns: USB-C 1 power or default int value.
        """
        return self._le16(23)

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB-C port 2 (middle) status.

        :returns: Status of the USB-C 2 port.
        """
        value = self._byte(76)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def usb_c2_power(self) -> int:
        """USB-C port 2 (middle) power (watts).

        .. note::
            Same single-byte -> 16-bit LE fix as :attr:`usb_c1_power` - see
            its note for the full story.

        :returns: USB-C 2 power or default int value.
        """
        return self._le16(25)

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB-C port 3 (bottom) status.

        :returns: Status of the USB-C 3 port.
        """
        value = self._byte(77)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def usb_c3_power(self) -> int:
        """USB-C port 3 (bottom) power (watts).

        .. note::
            Same single-byte -> 16-bit LE fix as :attr:`usb_c1_power` - see
            its note for the full story.

        :returns: USB-C 3 power or default int value.
        """
        return self._le16(27)

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB-A port 1 (top) status.

        :returns: Status of the USB-A 1 port.
        """
        value = self._byte(78)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def usb_a1_power(self) -> int:
        """USB-A port 1 (top) power (watts).

        .. note::
            Same single-byte -> 16-bit LE fix as :attr:`usb_c1_power` - see
            its note for the full story.

        :returns: USB-A 1 power or default int value.
        """
        return self._le16(29)

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB-A port 2 (bottom) status.

        :returns: Status of the USB-A 2 port.
        """
        value = self._byte(79)
        if value == DEFAULT_METADATA_INT:
            return PortStatus.UNKNOWN
        return PortStatus(value)

    @property
    def usb_a2_power(self) -> int:
        """USB-A port 2 (bottom) power (watts).

        .. note::
            Same single-byte -> 16-bit LE fix as :attr:`usb_c1_power` - see
            its note for the full story.

        :returns: USB-A 2 power or default int value.
        """
        return self._le16(31)

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        if self._data is None or len(self._data) < 101:
            return DEFAULT_METADATA_STRING
        raw = self._data[85:101].decode("ascii", errors="replace").rstrip("\x00")
        return raw or DEFAULT_METADATA_STRING

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        Only populated after :meth:`get_status_update`.

        :returns: AC charging power limit or default int value.
        """
        return self._le16(101, extended=True)

    @property
    def display_timeout_seconds(self) -> int:
        """Configured display timeout in seconds.

        Only populated after :meth:`get_status_update`.

        :returns: Display timeout in seconds or default int value.
        """
        return self._le16(105, extended=True)

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        Only populated after :meth:`get_status_update`.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        return _DISPLAY_BRIGHTNESS.get(self._byte(115, extended=True), LightStatus.UNKNOWN)

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled.

        Confirmed via a live-hardware test: toggling
        :meth:`turn_power_saving_mode_on`/:meth:`turn_power_saving_mode_off`
        through two full cycles produced a clean 0/1/0/1/0 pattern at this
        offset and nowhere else in the settings block. Only populated after
        :meth:`get_status_update`.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        value = self._byte(117, extended=True)
        if value == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_BOOL
        return value != 0

    @property
    def light(self) -> LightStatus:
        """Light bar status.

        Only populated after :meth:`get_status_update`.

        :returns: Status of the light bar.
        """
        return _LIGHT_MODES.get(self._byte(118, extended=True), LightStatus.UNKNOWN)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Configured temperature display unit.

        Only populated after :meth:`get_status_update`.

        :returns: Configured temperature unit.
        """
        value = self._byte(119, extended=True)
        if value == 0:
            return TemperatureUnit.CELSIUS
        if value == 1:
            return TemperatureUnit.FAHRENHEIT
        return TemperatureUnit.UNKNOWN

    async def _send_control(self, field_id: int, parameters: bytes) -> None:
        """Send a control command.

        Control commands share a common shape with :data:`CMD_POLL_TELEMETRY`:
        a fixed prefix, a single field-ID byte selecting what is being set, a
        length byte, the parameter bytes, and a trailing checksum byte (the
        unweighted sum of every preceding byte, mod 256 - not the XOR
        checksum used by the encrypted-protocol devices).

        .. note::
            The length byte was previously hardcoded as part of a fixed
            "middle" constant (``0b00``), since every command implemented so
            far (simple on/off/mode toggles) happens to produce the same
            11-byte frame. A third-party independently-built library
            documents this as a genuine length-of-frame field that varies
            for commands with larger parameters (timers, recharge power,
            screen brightness/timeout) - see issue #10. Fixed proactively;
            computing it dynamically produces byte-identical output for
            every command implemented so far.

        :param field_id: Field ID byte selecting which control to set.
        :param parameters: Parameter bytes for this command (e.g.
            ``b"\\x00\\x01"`` for a simple on/off toggle - a
            reserved/padding byte followed by the value). Length varies by
            command; the frame's length byte is computed from this
            automatically.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not self.connected:
            raise ConnectionError(f"Not connected to '{self.name}'!")

        length = len(_CMD_CONTROL_PREFIX) + 1 + 1 + len(parameters) + 1
        body = _CMD_CONTROL_PREFIX + bytes([field_id, length]) + parameters
        checksum = sum(body) % 256
        command = body + bytes([checksum])

        await self._client.write_gatt_char(UUID_COMMAND, command, response=False)

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_AC_OUTPUT, bytes([0x00, 1]))

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_AC_OUTPUT, bytes([0x00, 0]))

    async def turn_dc_on(self) -> None:
        """Turn the DC/Car socket output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_DC_OUTPUT, bytes([0x00, 1]))

    async def turn_dc_off(self) -> None:
        """Turn the DC/Car socket output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_DC_OUTPUT, bytes([0x00, 0]))

    async def turn_power_saving_mode_on(self) -> None:
        """Turn power saving mode on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_POWER_SAVING_MODE, bytes([0x00, 1]))

    async def turn_power_saving_mode_off(self) -> None:
        """Turn power saving mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_POWER_SAVING_MODE, bytes([0x00, 0]))

    async def set_light_mode(self, mode: LightStatus) -> None:
        """Set the light bar mode.

        :param mode: Mode to set the light bar to.
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the light status to unknown")
        await self._send_control(_FIELD_LIGHT_MODE, bytes([0x00, mode.value]))
