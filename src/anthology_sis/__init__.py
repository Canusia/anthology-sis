"""Anthology Student (CampusNexus) Query API client."""

from .client import ODataClient
from .config import Config, load_config

__all__ = ["ODataClient", "Config", "load_config"]
__version__ = "0.1.0"
