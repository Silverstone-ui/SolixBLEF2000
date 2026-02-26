=====
Usage
=====

.. _bleak: https://bleak.readthedocs.io/en/latest/usage.html/
.. _BLEDevice: https://bleak.readthedocs.io/en/latest/api/index.html#bleak.backends.device.BLEDevice/


It is recommended you read through the :doc:`examples <examples>` first to obtain an
understanding of the intended usage before diving into the documentation.

General approach
----------------

This module connects to a power station, negotiates a session with it,
and then periodically receives state updates from it and caches the state
of the device. The cached information can be accessed using the properties
of the class. In addition you can register callbacks to be run when the
state of the device changes.

.. note::
    State updates are only sent when something changes, they can vary from every second
    if something is drawing a varying amount of power, to every 15s if the device is 
    relatively idle.


Functions
---------

Finding a power station
^^^^^^^^^^^^^^^^^^^^^^^

Anker power stations can be automatically detected by the 
:py:meth:`discover_devices() <SolixBLE.discover_devices>`
method which looks for 
:py:attr:`UUID_IDENTIFIER <SolixBLE.const.UUID_IDENTIFIER>`
in the Bluetooth service data. This method returns a list of
`BLEDevice`_, each of which have been detected as Solix power stations.

``devices = await SolixBLE.discover_devices()``


.. note::

    This mechanism may not be reliable as it has only been tested with a
    ``C300X`` and ``C1000X``, albeit with a variety of firmware. If automatic 
    detection does not work, you can alternatively obtain a `BLEDevice`_ object
    via the `Bleak`_ library.


Initializing a power station
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to control a power station you must initialize a
:py:class:`.SolixBLE.SolixBLEDevice` object of the correct type for that power station.

``device = C1000(ble_device)``

.. note::

    This code creates a :py:class:`.SolixBLE.C1000` object but does *not*
    automatically connect to the power station.


Connecting to a power station
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The module will not automatically connect to a power station when a 
power station object is initialized, you must call :py:meth:`.connect`
in order to establish a connection.

On a successful *connection* (not instantiation) the program will
negotiate and subscribe to future updates of the power stations state
which may be accessed by the properties of the power station object.

.. note::

    On connection the properties of the device object will be at the
    default values until a telemetry message is received, this can take
    some time (~15s) if the power station is idle. 


Automatic Reconnection 
^^^^^^^^^^^^^^^^^^^^^^

This module will attempt to automatically reconnect to a power station
if the connection is lost. 

.. note::

    If a power station is disconnected for an extended period of time it
    will turn off the Bluetooth connection, requiring a press of the 
    power or pairing button for it to be possible to connect again.
