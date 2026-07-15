# Source Generated with Decompyle++
# File: image_info.pyc (Python 3.11)

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ImageInfo:
    filename: str
    path: str
    full_path: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: float = 0.0
    has_gps: bool = False
    capture_time: Optional[str] = None

    def to_dict(self):
        return asdict(self)
