"""Nami - Multi-platform media downloader."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nami")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]
