Limitations
===========

Bluetooth and Wi-Fi
-------------------

.. note::
    It is not currently possible to use Bluetooth and Wi-Fi at the same time.
    
Setting up Wi-Fi causes power stations to stop transmitting on Bluetooth, and turning the Bluetooth
connection back on by pressing the connection button causes it to disconnect from Wi-Fi.
It may be possible to send a special command to the power station to use both at the same time, but this has not been experimented with.


Control
-------

.. note::
    It is not currently possible to control devices, only receive telemetry.
    
This functionality may be added in future, and work done by the `anker-solix-api <https://github.com/thomluther/anker-solix-api>`_
project has decoded the format used by many devices and the Bluetooth and Cloud APIs use the same format.
This is not currently being worked on though.


Device support
--------------

.. note::
    Not all devices are supported and support for devices is reliant on the work done by `anker-solix-api <https://github.com/thomluther/anker-solix-api>`_
    and device owners adding support themselves. See :doc:`new_devices` for information on how to add support for a device.

Each power station encodes different information in the telemetry data, including in different orders,
this requires investigation work to decode what each value and command does on a per device basis.
I only have a C300X and C1000X to test with, so I am reliant on others adding support and 
the large database of the `anker-solix-api <https://github.com/thomluther/anker-solix-api>`_ project.
See :doc:`new_devices` for information on how to add support.
