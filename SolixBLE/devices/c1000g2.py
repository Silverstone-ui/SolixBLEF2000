"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_BOOL
from ..device import SolixBLEDevice
from ..states import PortStatus


class C1000G2(SolixBLEDevice):
    """
    C1000(X) Gen 2 Power Station.

    Use this class to connect and monitor a Gen 2 C1000(X) power station.
    This model is also known as the A1763.

    .. note::
        This model was added using data from anker-solix-api. It has not been
        tested!

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=3, end=20)

    @property
    def part_number(self) -> str:
        """Device part number.

        :returns: Device part number or default str value.
        """
        return self._parse_string("a2", begin=22, end=27)

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("a5", begin=1, end=2, signed=True)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a5", begin=3, end=4)

    @property
    def battery_health(self) -> int:
        """Battery health.

        :returns: Percentage battery health or default int value.
        """
        return self._parse_int("a5", begin=4, end=5)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("a6", begin=1, end=3)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("a6", begin=3, end=5)

    @property
    def ac_on(self) -> bool:
        """Is the AC output on.

        :returns: AC output on or default bool value.
        """
        return (
            bool(self._parse_int("a7", begin=1, end=2))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int("a7", begin=2, end=4)

    @property
    def dc_input_on(self) -> bool:
        """Is DC input on.

        :returns: DC input on or default bool value.
        """
        return (
            bool(self._parse_int("a8", begin=1, end=2))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def dc_power_in(self) -> int:
        """DC Power In.

        :returns: DC power in or default int value.
        """
        return self._parse_int("a8", begin=2)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("aa", begin=1, end=2))

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int("aa", begin=2)

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("ab", begin=1, end=2))

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int("ab", begin=2)

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("ac", begin=1, end=2))

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int("ac", begin=2)

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("ae", begin=1, end=2))

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int("ae", begin=2)

    @property
    def dc_port(self) -> PortStatus:
        """DC Port Status.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("b2", begin=1, end=2))

    @property
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return self._parse_int("b2", begin=2)

    @property
    def max_battery_percentage(self) -> int:
        """Maximum charge percentage.

        :returns: Battery charge percentage upper limit or default int value.
        """
        return self._parse_int("d9", begin=4, end=5)

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        return self._parse_int("d9", begin=5, end=6)
