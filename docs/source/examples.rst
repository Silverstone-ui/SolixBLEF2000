========
Examples
========

.. _basic_example:

Basic Example
-------------

Simple demonstration of connecting to a known device and printing
out telemetry updates.


.. literalinclude:: ../../examples/example.py
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
