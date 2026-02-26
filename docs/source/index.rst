Welcome to SolixBLE's documentation!
====================================

.. image:: https://img.shields.io/pypi/v/SolixBLE.svg
    :target: https://pypi.python.org/pypi/SolixBLE

.. image:: https://readthedocs.org/projects/solixble/badge/?version=latest
    :target: https://solixble.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status
      
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Black

This Python module enables you to monitor Anker Solix devices directly
from your computer, without the need for any cloud services or Anker app.
It leverages the Bleak library to interact with Bluetooth Anker Solix power stations.
No pairing is required in order to receive telemetry data.


.. note::

   This project is under active development.


Device support
--------------

======================= ======== =========
Parameter               C300(X)  C1000(X)   
======================= ======== =========
AC Timer.               ✅        ✅
DC Timer.               ✅        ❌
Time remaining.         ✅        ✅
AC Power in.            ✅        ✅
AC Power out.           ✅        ✅
USB Power out.          ✅        ✅
DC Power Out.           ✅        ❌
DC Power In.            ✅        ✅
DC Power In status.     ✅        ✅
Total Power In.         ✅        ✅
Total Power Out.        ✅        ✅
Firmware version        ✅        ✅
Expansion firmware      N/A       ✅
AC on/off state         ✅        ✅
Temperature             ✅        ✅
Expansion temperature   N/A       ✅
Charging status         ✅        ❌
Battery percentage      ✅        ✅
Expansion percentage    N/A       ✅
Battery health          ❌        ✅
Expansion health        N/A       ✅
Expansion num           N/A       ✅
USB Port status         ✅        ❌
DC Port status          ✅        ❌
Light status            ✅        ❌
Serial number           ✅        ❌
======================= ======== =========


Contents
--------

.. toctree::

   Home <self>
   examples
   usage
   api
   limitations
   new_devices
   source
