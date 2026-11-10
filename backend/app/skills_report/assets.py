"""
Fonts and images used by the skills report.

The files in `assets/` are copies of the frontend public assets (`frontend-new/public`), so that both sides render with
the same fonts and icons. Logos/icons are referenced by URL in the (shared) report config; the backend resolves them by
file name against the assets directory.

SVG images are rasterized to PNG at 3x their natural size, like the frontend does on a canvas before embedding them.
"""
import io
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PIL import Image as PILImage

ASSETS_DIR = Path(__file__).parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
IMAGES_DIR = ASSETS_DIR / "images"

SVG_RASTERIZE_SCALE = 3

# Icons (frontend: ReportContent.IMAGE_URLS)
LOCATION_ICON = "/location.png"
PHONE_ICON = "/phone.png"
EMAIL_ICON = "/email.png"
EDUCATION_ICON = "/trainee-work.png"
EMPLOYEE_ICON = "/employee.png"
SELF_EMPLOYMENT_ICON = "/self-employment.png"
COMMUNITY_WORK_ICON = "/community-work.png"
TRAINEE_WORK_ICON = "/trainee-work.png"
WARNING_ICON = "/warning.png"
QUIZ_ICON = "/quiz.png"

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FontFiles:
    regular: str = str(FONTS_DIR / "Inter-Regular.ttf")
    bold: str = str(FONTS_DIR / "Inter-Bold.ttf")
    italic: str = str(FONTS_DIR / "Inter-Italic.ttf")


INTER = FontFiles()


@dataclass(frozen=True)
class ReportImage:
    """A raster (PNG) image, ready to be embedded in a PDF or DOCX."""
    data: bytes
    width: int
    height: int


class ImageNotFoundError(Exception):
    pass


def _image_search_dirs() -> list[Path]:
    dirs = [IMAGES_DIR]
    extra = os.getenv("SKILLS_REPORT_EXTRA_IMAGES_DIR")
    if extra:
        dirs.insert(0, Path(extra))
    return dirs


def _resolve_image_path(url: str) -> Path:
    name = os.path.basename(urlparse(url).path)
    for directory in _image_search_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise ImageNotFoundError(f"Skills report image not found: {url} (looked for '{name}' in "
                             f"{', '.join(str(d) for d in _image_search_dirs())})")


def rasterize_svg(svg_bytes: bytes, scale: int = SVG_RASTERIZE_SCALE) -> bytes:
    import resvg_py  # pylint: disable=import-outside-toplevel  # imported lazily, only needed for SVG logos
    return bytes(resvg_py.svg_to_bytes(  # pylint: disable=no-member
        svg_string=svg_bytes.decode("utf-8"), zoom=scale))


@lru_cache(maxsize=64)
def load_image(url: str) -> ReportImage:
    """Load an image by its (frontend) URL; SVGs are rasterized to PNG."""
    path = _resolve_image_path(url)
    data = path.read_bytes()
    if path.suffix.lower() == ".svg":
        data = rasterize_svg(data)
    with PILImage.open(io.BytesIO(data)) as img:
        width, height = img.size
    return ReportImage(data=data, width=width, height=height)


def try_load_image(url: str) -> Optional[ReportImage]:
    try:
        return load_image(url)
    except (ImageNotFoundError, OSError) as e:
        _logger.warning("Skipping skills report image: %s", e)
        return None
