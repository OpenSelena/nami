"""Downloader engine adapters."""

from nami.engines.base import Engine, EngineAnalysis, EngineRequest
from nami.engines.gallery_dl import GalleryDlEngine
from nami.engines.yt_dlp import YtDlpEngine

__all__ = [
    "Engine",
    "EngineAnalysis",
    "EngineRequest",
    "GalleryDlEngine",
    "YtDlpEngine",
]
