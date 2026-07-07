"""F2000(P) / 767 PowerHouse power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
from datetime import datetime, timedelta

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus

CMD_AC_TIMER = "4042"
CMD_DC_TIMER = "4043"
CMD_AC_CHARGING_POWER = "4044"
CMD_DISPLAY_TIMEOUT = "4046"
CMD_DISPLAY_ON_OFF = "4052"
CMD_AC_OUTPUT = "404a"
CMD_DC_OUTPUT = "404b"
CMD_DISPLAY_MODE = "404c"
CMD_POWER_SAVING_MODE = "404e"
CMD_LIGHT_MODE = "404f"

PAYLOAD_ON = "a10121a2020101"
PAYLOAD_OFF = "a10121a2020100"
PAYLOAD_LIGHT_MODE = "a10121a20201"
PAYLOAD_TIMEOUT_TIME = "a10121a20302"
PAYLOAD_AC_CHARGING_POWER = "a10121a20302"
PAYLOAD_TIMER = "a10121a20502"

_LOGGER = logging.getLogger(__name__)


class F2000(SolixBLEDevice):
    """
    F2000(P) Power Station.

    Use this class to connect and monitor a F2000(P) power station.
    This model is also known as the A1780 or the 767 PowerHouse.

    .. note::
        Telemetry sensors were added using data from anker-solix-api. Control
        methods (AC/DC output, timers, light, display, power saving mode, AC
        charging power) were ported from the F2600 class and have been
        confirmed working against real F2000 hardware.

    .. note::
        Some status properties (e.g. ``is_display_on``, ``display_mode``,
        ``power_saving_mode_enabled``, ``ac_charging_power``,
        ``display_timeout_seconds``) are not included in every passive
        telemetry push and may read as unknown/default until
        :py:meth:`get_status_update` is called or a push containing them is
        received (this can take up to ~15s if the device is idle).

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty.

        Note that any hours over 24 are overflowed to the
        days remaining. Use time_remaining if you want
        days to be included.

        :returns: Hours remaining or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return round(divmod(self.time_remaining, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty.

        Note that any partial days are overflowed into
        the hours remaining. Use time_remaining if you want
        hours to be included.

        :returns: Days remaining or default int value.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT

        return round(divmod(self.time_remaining, 24)[0])

    @property
    def time_remaining(self) -> float:
        """Time remaining to full/empty in hours.

        :returns: Hours remaining or default float value.
        """
        return (
            self._parse_int("a4", begin=1) / 10.0
            if self._data is not None
            else DEFAULT_METADATA_FLOAT
        )

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be full/empty.

        :returns: Timestamp of when will be full/empty or None.
        """
        if self._data is None:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)

    @property
    def ac_to_battery(self) -> int:
        """AC Power that is going to the battery.

        :returns: Total AC power to battery or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def ac_power_out_sockets(self) -> int:
        """AC Power Out to sockets.

        :returns: AC power out or default int value.
        """
        return self._parse_int("a6", begin=1)

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int("a7", begin=1)

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int("a8", begin=1)

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int("a9", begin=1)

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int("aa", begin=1)

    @property
    def usb_a2_power(self) -> int:
        """USB A2 Power.

        :returns: USB port A2 power or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def dc_1_power_out(self) -> int:
        """DC Power out for port 1.

        :returns: DC power out for port 1 or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def dc_2_power_out(self) -> int:
        """DC Power out for port 2.

        :returns: DC power out for port 2 or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ae", begin=1)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("af", begin=1)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int("b0", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b3", begin=1))])

    @property
    def software_version_expansion(self) -> str:
        """Software version of any expansion batteries.

        If there is no expansion battery then it will be "0".

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b9", begin=1))])

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("ba", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("bd", begin=1, signed=True)

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery if present (C).

        :returns: Temperature of expansion battery in degrees C or 0 if not present or default int value.
        """
        return self._parse_int("be", begin=1, signed=True)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("c1", begin=1)

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery Percentage of the expansion battery.

        :returns: Percentage charge of expansion battery or 0 if not present or default int value.
        """
        return self._parse_int("c2", begin=1)

    @property
    def battery_health(self) -> int:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default int value.
        """
        return self._parse_int("c3", begin=1)

    @property
    def battery_health_expansion(self) -> int:
        """Battery health as a percentage for expansion battery.

        :returns: Percentage of expansion battery health or 0 if not present or default int value.
        """
        return self._parse_int("c4", begin=1)

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        :returns: Number of expansion batteries or default int value.
        """
        return self._parse_int("c5", begin=1)

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("d0", begin=1)

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        - ``IDLE`` (0): no external source connected; this includes
          pure battery-only discharge — the device does *not* emit
          ``DISCHARGING`` in that state.
        - ``DISCHARGING`` (1): a solar source is present but insufficient
          to cover the load; battery is also contributing.
        - ``CHARGING`` (2): AC wall is connected and charging the battery.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int("bc", begin=1))

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a2", begin=1)

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if (
            self.ac_timer_remaining != DEFAULT_METADATA_INT
            and self.ac_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.ac_timer_remaining)

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if (
            self.dc_timer_remaining != DEFAULT_METADATA_INT
            and self.dc_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.dc_timer_remaining)

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int("cf", begin=1))

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the AC port.
        """
        return PortStatus(self._parse_int("bb", begin=1))

    @property
    def dc_output(self) -> PortStatus:
        """DC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("cb", begin=1))

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("c6", begin=1))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("c7", begin=1))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("c8", begin=1))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("c9", begin=1))

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return PortStatus(self._parse_int("ca", begin=1))

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        :returns: AC charging power limit or default int value.
        """
        if self._data is None or "d1" not in self._data:
            return DEFAULT_METADATA_INT
        return self._parse_int("d1", begin=1)

    @property
    def display_timeout_seconds(self) -> int:
        """Configured display timeout in seconds.

        :returns: Display timeout in seconds or default int value.
        """
        if self._data is None or "d3" not in self._data:
            return DEFAULT_METADATA_INT
        return self._parse_int("d3", begin=1)

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        return (
            bool(self._parse_int("db", begin=1))
            if self._data is not None and "db" in self._data
            else DEFAULT_METADATA_BOOL
        )

    @property
    def is_display_on(self) -> bool | None:
        """Whether the LCD display is on.

        :returns: True if on, False if off, or default bool value.
        """
        return (
            bool(self._parse_int("de", begin=1))
            if self._data is not None and "de" in self._data
            else DEFAULT_METADATA_BOOL
        )

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        if self._data is None or "d9" not in self._data:
            return LightStatus.UNKNOWN
        return LightStatus(self._parse_int("d9", begin=1))

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_dc_on(self) -> None:
        """Turn the DC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_dc_off(self) -> None:
        """Turn the DC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_TIMER),
            payload=bytes.fromhex(PAYLOAD_TIMER)
            + seconds.to_bytes(length=4, byteorder="little", signed=False),
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC auto-off timer.

        :param seconds: Seconds until DC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_TIMER),
            payload=bytes.fromhex(PAYLOAD_TIMER)
            + seconds.to_bytes(length=4, byteorder="little", signed=False),
        )

    async def set_light_mode(self, mode: LightStatus) -> None:
        """Set the light mode of the LED bar.

        :param mode: Mode to set light bar to.
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the light status to unknown")
        await self._send_command(
            cmd=bytes.fromhex(CMD_LIGHT_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )

    async def set_display_mode(self, mode: LightStatus) -> None:
        """Set the status/mode of the LCD display.

        :param mode: Mode/status to set display to (off/low/med/high).
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the display brightness status to unknown")
        if mode is LightStatus.SOS:
            raise ValueError("You cannot set the display brightness status to SOS")
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:
        """Set the status/mode of the LCD display.

        :param mode: Mode/timeout to set display to (30s, 5m, 30m, etc).
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """

        if timeout is DisplayTimeout.UNKNOWN:
            raise ValueError("You cannot set the display timeout to unknown")
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_TIMEOUT),
            payload=bytes.fromhex(PAYLOAD_TIMEOUT_TIME)
            + timeout.value.to_bytes(length=2, byteorder="little", signed=False),
        )

    async def turn_display_on(self) -> None:
        """Turn the display on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_display_off(self) -> None:
        """Turn the display off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_power_saving_mode_on(self) -> None:
        """Turn the power saving mode on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_POWER_SAVING_MODE),
            payload=bytes.fromhex(PAYLOAD_ON),
        )

    async def turn_power_saving_mode_off(self) -> None:
        """Turn the power saving mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_POWER_SAVING_MODE),
            payload=bytes.fromhex(PAYLOAD_OFF),
        )

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        :param watts: AC charging power limit in watts.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if watts < 100 or watts > 1440: # below 100 causes max charge, 1440 is max in app.
            raise ValueError("AC charging power must be between 100 and 1440 W")

        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_CHARGING_POWER),
            payload=bytes.fromhex(PAYLOAD_AC_CHARGING_POWER)
            + watts.to_bytes(length=2, byteorder="little", signed=False),
        )

    async def get_status_update(self) -> dict[str, bytes]:
        """Request and retrieve a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: Dictionary containing telemetry parameters.
        """
        await self._send_command(
            cmd=bytes.fromhex("4040"),
            payload=bytes.fromhex("a10121"),
        )

        packet_1 = await self._listen_for_packet(
            bytes.fromhex("03010f"), bytes.fromhex("c840")
        )
        if not packet_1:
            raise TimeoutError("Timed out waiting for packet 1!")

        packet_2 = await self._listen_for_packet(
            bytes.fromhex("03010f"), bytes.fromhex("c840")
        )
        if not packet_2:
            raise TimeoutError("Timed out waiting for packet 2!")

        # We need to ignore the first byte of each packet with these types
        new_payload = packet_1[1:] + packet_2[1:]
        decrypted_payload = self._decrypt_payload(new_payload)
        parameters = self._parse_payload(decrypted_payload)
        _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters, types=True)}")
        await self._process_telemetry(parameters) # update the internal parameters as well
        return parameters
