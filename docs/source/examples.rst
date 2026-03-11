========
Examples
========

.. _basic_example:

Monitoring Example
------------------

Simple demonstration of connecting to a known device and printing
out telemetry updates.

.. literalinclude:: ../../examples/monitor.py
    :language: python
    :linenos:



.. _control_example:

Control Example
---------------

Simple demonstration of connecting to a known device and sending
commands to control its outputs.

.. literalinclude:: ../../examples/control.py
    :language: python
    :linenos:



.. _complex_example:

Complex Example
---------------

This is a more advanced demonstration program which prompts the user for
the device to connect to, its model, and then prints out the telemetry data 
on demand and when there is an update. This can be used to add support
for new devices, see :doc:`new_devices`.

.. literalinclude:: ../../examples/demo.py
    :language: python
    :linenos:

