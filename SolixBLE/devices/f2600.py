"""F2600 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
.. moduleauthor:: github.com/unex

"""

from ..states import PortStatus

from . import F2000


class F2600(F2000):
    """
    F2600 Power Station.

    Use this class to connect and monitor a F2600 power station.
    This model is also known as the A1781.
    """

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: AC socket output power in watts or default int value.
        """
        return self._parse_int("a6", begin=1)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total output power (AC + USB + DC) in watts or default int value.
        """
        return self._parse_int("b0", begin=1)

    @property
    def solar_port(self) -> PortStatus:
        """Solar/DC input port status.

        Note: remains INPUT after the Anderson connector loses power until
        AC wall charging takes over, at which point it clears to NOT_CONNECTED.

        :returns: Status of the solar/DC input port.
        """
        return (
            PortStatus.INPUT
            if self._parse_int("bf", begin=1) == 1
            else PortStatus.NOT_CONNECTED
        )

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total input power in watts or default int value.
        """
        return self._parse_int("af", begin=1)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        On F2600, key ``a5`` tracks total AC wall input. Key ``af`` tracks combined total of all
        inputs.

        :returns: Total AC wall input power in watts or default int value.
        """
        return self._parse_int("a5", begin=1)
