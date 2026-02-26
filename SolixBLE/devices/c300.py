"""C300(X) power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from datetime import datetime, timedelta

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus, LightStatus, PortStatus


class C300(SolixBLEDevice):
    """
    C300(X) Power Station.

    Use this class to connect and monitor a C300(X) power station.
    This model is also known as the A1722.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

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
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
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
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("ae", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b1", begin=1))])

    @property
    def ac_on(self) -> bool:
        """Is the AC output on.

        :returns: AC output on or default bool value.
        """
        return (
            bool(self._parse_int("b7", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("b9", begin=1, signed=True)

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int("ba", begin=1))

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("bb", begin=1)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("bd", begin=1))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("be", begin=1))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("bf", begin=1))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("c0", begin=1))

    @property
    def dc_port(self) -> PortStatus:
        """DC Port Status.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("c1", begin=1))

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int("cf", begin=1))

    @property
    def serial_number(self) -> str:
        """Serial number.

        :returns: The serial number of the device.
        """
        return self._parse_string("c5", begin=1)
