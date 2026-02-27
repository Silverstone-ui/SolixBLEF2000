# SolixBLE

[![PyPI Status](https://img.shields.io/pypi/v/SolixBLE.svg)](https://pypi.python.org/pypi/SolixBLE)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Python module for monitoring Anker Solix power stations and other devices over Bluetooth.
 - 👌 Free software: MIT license
 - 🍝 Sauce: https://github.com/flip-dots/SolixBLE
 - 🖨️ Documentation: https://solixble.readthedocs.io/en/latest/
 - 📦 PIP: https://pypi.org/project/SolixBLE/


This Python module enables you to monitor Anker Solix devices directly
from your computer, without the need for any cloud services or Anker app.
It leverages the Bleak library to interact with Bluetooth Anker Solix devices.
No pairing is required in order to receive telemetry data.


## Features

- 🔋 Battery percentage
- ⚡ Total Power In/Out
- 🔌 AC Power In/Out
- 🚗 DC Power In/Out
- ⏰ AC/DC Timer value
- ⏲️ Time remaining to full/empty
- ☀️ Solar Power In
- 💻 USB Port Power
- 📱 USB Port Status
- ⚙️ Firmware version
- 🩺 Battery health
- 🌡️ Battery temperature
- ↔️ Expansion batteries (Charge, Temperature, Health, Firmware)
- 💡 Light bar status
- 🔂 Simple structure
- ✔️ More emojis than strictly necessary


## Supported Devices

See the [support table](https://solixble.readthedocs.io/en/latest) in the documentation for feature support for particular devices.

- C300(X)
- C300(X) DC
- C1000(X)
- C1000 Gen 2
- F2000 (767 PowerHouse)
- F3800
- Solarbank 2
- Solarbank 3
- Prime Charger 250w
- Maybe more? IDK


## Requirements

- 🐍 Python 3.11+
- 📶 Bleak 0.19.0+
- 📶 bleak-retry-connector


## Supported Operating Systems

- 🐧 Linux (BlueZ)
  - Ubuntu Desktop
  - Arch (HomeAssistant OS)
- 🏢 Windows
  - Windows 10 
- 💾 Mac OSX
  - Maybe?


## Installation


### PIP

```
pip install SolixBLE
```


### Manual

SolixBLE consists of a single file (SolixBLE.py) which you can simply put in the
same directory as your program. If you are using manual installation make sure
the dependencies are installed as well.

```
pip install bleak bleak-retry-connector cryptography pycryptodome
```

## Adding support for new devices

See the `Generic` class inside `SolixBLE.py` for guidance on how to add support for new devices.
