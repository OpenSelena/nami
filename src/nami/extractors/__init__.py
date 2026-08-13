"""Extractor engines module for Nami."""

from nami.extractors.base import BaseExtractor
from nami.extractors.gallery_dl import GalleryDlExtractor
from nami.extractors.instaloader import InstaloaderExtractor
from nami.extractors.yt_dlp import YtDlpExtractor

INSTALOADER_EXTRACTOR = InstaloaderExtractor()
GALLERY_DL_EXTRACTOR = GalleryDlExtractor()
YT_DLP_EXTRACTOR = YtDlpExtractor()

EXTRACTORS = {
    "instaloader": INSTALOADER_EXTRACTOR,
    "gallery-dl": GALLERY_DL_EXTRACTOR,
    "yt-dlp": YT_DLP_EXTRACTOR,
}

__all__ = [
    "BaseExtractor",
    "GalleryDlExtractor",
    "InstaloaderExtractor",
    "YtDlpExtractor",
    "EXTRACTORS",
    "INSTALOADER_EXTRACTOR",
    "GALLERY_DL_EXTRACTOR",
    "YT_DLP_EXTRACTOR",
]
