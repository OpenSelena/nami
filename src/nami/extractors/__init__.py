"""Extractor engines module for Nami."""

from nami.extractors.base import BaseExtractor
from nami.extractors.gallery_dl import GalleryDlExtractor
from nami.extractors.yt_dlp import YtDlpExtractor

GALLERY_DL_EXTRACTOR = GalleryDlExtractor()
YT_DLP_EXTRACTOR = YtDlpExtractor()

EXTRACTORS = {
    "gallery-dl": GALLERY_DL_EXTRACTOR,
    "yt-dlp": YT_DLP_EXTRACTOR,
}

__all__ = [
    "BaseExtractor",
    "GalleryDlExtractor",
    "YtDlpExtractor",
    "EXTRACTORS",
    "GALLERY_DL_EXTRACTOR",
    "YT_DLP_EXTRACTOR",
]
