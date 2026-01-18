"""CycloneDX helper functions for reading and manipulating SBOMs.

This module provides a Python-native representation of CycloneDX BOMs
that's easier to work with than the raw JSON structure.
"""

from .bom import Bom
from .cli import main
from .component import Component
from .io import dump, load

__all__ = ["Bom", "Component", "dump", "load", "main"]
