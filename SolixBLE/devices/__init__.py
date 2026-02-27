"""Anker Solix device models supported by the module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .c300 import C300
from .c300dc import C300DC
from .c1000 import C1000
from .c1000g2 import C1000G2
from .f2000 import F2000
from .f3800 import F3800
from .generic import Generic
from .solarbank2 import Solarbank2

__all__ = [
    "C300",
    "C300DC",
    "C1000",
    "C1000G2",
    "F2000",
    "F3800",
    "Solarbank2",
    "Generic",
]
