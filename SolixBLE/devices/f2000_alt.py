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

#: Fixed bytes following the field ID in every control command observed so far.
_CONTROL_MIDDLE = bytes.fromhex("0b00")

#: Minimum notification length to be considered a real telemetry frame,
#: filtering out the small ~14 byte heartbeat/ack frames this device also
#: sends periodically.
_MIN_TELEMETRY_LENGTH = 100

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

        Ignores the small heartbeat/ack frames this device also sends. Base
        telemetry (present in every real frame) updates :attr:`_data`; the
        settings block (only present in the extended ~122 byte response to
        a poll) updates :attr:`_extended_data` separately, so a later small
        passive push doesn't wipe out settings-block properties.
        """
        if len(data) < _MIN_TELEMETRY_LENGTH:
            return

        self._data = bytes(data)
        self._last_data_timestamp = datetime.now()

        if len(data) >= _MIN_EXTENDED_LENGTH:
            self._extended_data = bytes(data)

        self._first_frame_event.set()
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
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C or default int value.
        """
        return self._byte(66)

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
            the closest available approximation. Also single-byte (max 255W)
            unlike offset 17-18's LE16 - a high-wattage AC load could wrap.

        :returns: AC + light bar power out or default int value.
        """
        return self._byte(41)

    @property
    def ac_output_power(self) -> int:
        """AC output power only, excluding the light bar (watts).

        Confirmed via a live-hardware test: matched the unit's own screen
        display within 1W under a real AC (fan) load, and was unaffected by
        light bar mode changes that did move :attr:`power_out`. Does not
        include DC/car-socket or light bar output. See
        :doc:`/f2000_hardware_variant` for the full writeup.

        :returns: AC output power or default int value.
        """
        return self._byte(21)

    @property
    def ac_power_in(self) -> int:
        """AC Power In while charging (watts).

        :returns: AC power in or default int value.
        """
        return self._le16(19)

    @property
    def time_remaining(self) -> float:
        """Time remaining to empty, on battery discharge, in hours.

        .. note::
            This does not reflect "time to full charge" while charging - it
            keeps showing the last discharge estimate. That field has not
            been located yet.

        :returns: Hours remaining or default float value.
        """
        raw = self._le16(57)
        if raw == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_FLOAT
        return round(raw / 10.0, 1)

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

        :returns: USB-C 1 power or default int value.
        """
        return self._byte(23)

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

        :returns: USB-C 2 power or default int value.
        """
        return self._byte(25)

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

        :returns: USB-C 3 power or default int value.
        """
        return self._byte(27)

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

        :returns: USB-A 1 power or default int value.
        """
        return self._byte(29)

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

        :returns: USB-A 2 power or default int value.
        """
        return self._byte(31)

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

    async def _send_control(self, field_id: int, value: int) -> None:
        """Send a control command.

        Control commands share a common shape with :data:`CMD_POLL_TELEMETRY`:
        a fixed prefix, a single field-ID byte selecting what is being set, a
        fixed middle section, a one-byte value, and a trailing checksum byte
        (the unweighted sum of every preceding byte, mod 256 - not the XOR
        checksum used by the encrypted-protocol devices).

        :param field_id: Field ID byte selecting which control to set.
        :param value: Value byte to set the field to.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not self.connected:
            raise ConnectionError(f"Not connected to '{self.name}'!")

        body = _CMD_CONTROL_PREFIX + bytes([field_id]) + _CONTROL_MIDDLE + bytes([value])
        checksum = sum(body) % 256
        command = body + bytes([checksum])

        await self._client.write_gatt_char(UUID_COMMAND, command, response=False)

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_AC_OUTPUT, 1)

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_AC_OUTPUT, 0)

    async def turn_dc_on(self) -> None:
        """Turn the DC/Car socket output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_DC_OUTPUT, 1)

    async def turn_dc_off(self) -> None:
        """Turn the DC/Car socket output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_DC_OUTPUT, 0)

    async def turn_power_saving_mode_on(self) -> None:
        """Turn power saving mode on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_POWER_SAVING_MODE, 1)

    async def turn_power_saving_mode_off(self) -> None:
        """Turn power saving mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_control(_FIELD_POWER_SAVING_MODE, 0)

    async def set_light_mode(self, mode: LightStatus) -> None:
        """Set the light bar mode.

        :param mode: Mode to set the light bar to.
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the light status to unknown")
        await self._send_control(_FIELD_LIGHT_MODE, mode.value)
