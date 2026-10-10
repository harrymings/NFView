"""Resources functionality for NFView."""
from __future__ import annotations
import base64
from pathlib import Path



SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".nef", ".cr2", ".arw", ".dng"}

RAW_EXTENSIONS = {".nef", ".cr2", ".arw", ".dng"}

CACHE_FILENAME = ".image-screener-cache.json"

APP_NAME = "NFView"

APP_ICON_ICO = base64.b64encode((Path(__file__).parent / "assets" / "NFView.ico").read_bytes()).decode("ascii")

APP_ICON_PNG = base64.b64encode((Path(__file__).parent / "assets" / "NFView.png").read_bytes()).decode("ascii")

CACHE_VERSION = 3

CONFIG_FILENAME = ".image-screener-settings.json"
