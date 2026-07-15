"""水印服务 - 为照片添加水印、Logo 和 GPS 信息。"""
from __future__ import annotations

import base64
import io
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import (
    DEFAULT_CENTER_FONT_RATIO,
    DEFAULT_CENTER_OPACITY,
    DEFAULT_CENTER_TEXT,
    DEFAULT_LEFT_FONT_SIZE,
)
from services.geocode_service import get_address_from_latlng
from services.image_service import read_img_gps

# 嵌入式 Logo PNG（base64），作为文件不存在时的后备
_EMBEDDED_LOGO_PNG_B64: str = ""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class WatermarkOptions:
    center_text: str = DEFAULT_CENTER_TEXT
    center_enabled: bool = True
    center_font_ratio: float = DEFAULT_CENTER_FONT_RATIO
    center_opacity: float = DEFAULT_CENTER_OPACITY
    center_color: str = '#646464'
    center_stroke_color: str = '#ffffff'
    left_enabled: bool = True
    left_font_size: int = DEFAULT_LEFT_FONT_SIZE
    left_color: str = '#ffffff'
    left_stroke_color: str = '#000000'
    left_stroke_width: int = 1
    include_lonlat: bool = True
    include_address: bool = False
    include_time: bool = True
    include_filename: bool = False
    custom_lines: str = ''
    logo_enabled: bool = False
    logo_width_ratio: float = 0.14


# ---------------------------------------------------------------------------
# 资源路径解析
# ---------------------------------------------------------------------------
def resource_path(filename: str) -> str:
    """返回首个存在的资源路径，兼容源码、PyInstaller onedir 和安装目录。"""
    candidates: list[Path] = []

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / filename)

    if getattr(sys, 'frozen', False):
        candidates.append(Path(sys.executable).resolve().parent / filename)
        candidates.append(Path(sys.executable).resolve().parent / '_internal' / filename)

    candidates.append(Path(__file__).resolve().parent.parent / filename)
    candidates.append(Path.cwd() / filename)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(candidates[0]) if candidates else str(Path(filename))


# ---------------------------------------------------------------------------
# Logo 加载
# ---------------------------------------------------------------------------
def _load_logo() -> Image.Image | None:
    for filename in ('logo.png', 'logo.ico'):
        path = resource_path(filename)
        if not os.path.exists(path):
            continue
        try:
            with Image.open(path) as source:
                if getattr(source, 'n_frames', 1) > 1:
                    source.seek(source.n_frames - 1)
                return source.convert('RGBA').copy()
        except Exception:
            continue

    # 回退到嵌入式 base64
    try:
        raw = base64.b64decode(_EMBEDDED_LOGO_PNG_B64)
        with Image.open(io.BytesIO(raw)) as source:
            return source.convert('RGBA').copy()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Logo 合成
# ---------------------------------------------------------------------------
def add_logo_to_rgba(image: Image.Image, width_ratio: float = 0.14) -> Image.Image:
    """Place the application logo in the top-left corner without modifying the source object."""
    base = image.convert('RGBA').copy()
    logo = _load_logo()
    if logo is None:
        return base

    width, height = base.size
    target_w = max(
        48,
        min(
            int(width * max(0.04, min(0.3, width_ratio)) * width),
            int(width * 0.3),
        ),
    )
    scale = max(1, target_w) / max(1, logo.width)
    target_h = max(1, int(logo.height * scale))
    max_h = max(32, int(height * 0.18))

    if target_h > max_h:
        target_h = max_h
        target_w = max(1, int(logo.width * target_h / max(1, logo.height)))

    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    margin = max(8, int(min(width, height) * 0.012))
    base.alpha_composite(logo, (margin, margin))
    return base


def add_logo_to_image_file(
    source_path,
    output_path,
    width_ratio: float = 0.14,
    quality: int = 92,
) -> bool:
    """Create an upload copy with the logo; the original photo is never overwritten."""
    try:
        with Image.open(source_path) as origin:
            exif = origin.getexif()
            if exif:
                exif[274] = 1
            oriented = ImageOps.exif_transpose(origin).convert('RGBA')
            final = add_logo_to_rgba(oriented, width_ratio).convert('RGB')

            kwargs = {'quality': quality, 'optimize': True}
            if exif:
                kwargs['exif'] = exif
            final.save(output_path, **kwargs)
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# 颜色工具
# ---------------------------------------------------------------------------
def _hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    try:
        color = (color or '#ffffff').strip().lstrip('#')
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        return (
            int(color[0:2], 16),
            int(color[2:4], 16),
            int(color[4:6], 16),
            alpha,
        )
    except Exception:
        return (255, 255, 255, alpha)


# ---------------------------------------------------------------------------
# 字体路径解析
# ---------------------------------------------------------------------------
def resolve_font_path() -> str:
    local = 'simhei.ttf'
    if os.path.exists(local):
        return local

    system = platform.system()
    if system == 'Windows':
        return 'C:/Windows/Fonts/simhei.ttf'
    if system == 'Darwin':
        return '/System/Library/Fonts/PingFang.ttc'
    return '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


# ---------------------------------------------------------------------------
# 描边文本绘制
# ---------------------------------------------------------------------------
def _draw_text_with_stroke(draw, xy, text, font, fill, stroke_fill, stroke_width):
    if stroke_width > 0:
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx or dy:
                    draw.text((xy[0] + dx, xy[1] + dy), text, font=font, fill=stroke_fill)
    draw.text(xy, text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# 主水印函数
# ---------------------------------------------------------------------------
def add_watermark_to_image(img_path, output_path, options=None) -> bool:
    """为图片添加水印（中心文本 + 左侧信息面板 + Logo）。"""
    if isinstance(options, int):
        options = WatermarkOptions(left_font_size=options)
    if options is None:
        options = WatermarkOptions()

    try:
        img_origin = Image.open(img_path)
        origin_exif = img_origin.getexif()
        if origin_exif:
            origin_exif[274] = 1
        img = ImageOps.exif_transpose(img_origin).convert('RGBA')
        width, height = img.size

        watermark = Image.new('RGBA', img.size, (255, 255, 255, 0))

        if options.logo_enabled:
            watermark = add_logo_to_rgba(watermark, options.logo_width_ratio)

        draw = ImageDraw.Draw(watermark)

        font_path = resolve_font_path()
        try:
            center_font = ImageFont.truetype(
                font_path,
                max(10, int(min(width, height) * options.center_font_ratio)),
            )
            left_font = ImageFont.truetype(font_path, options.left_font_size)
        except Exception:
            center_font = ImageFont.load_default()
            left_font = ImageFont.load_default()

        # --- 中心水印文本 ---
        if options.center_enabled and options.center_text.strip():
            alpha = int(255 * max(0, min(1, options.center_opacity)))
            text = options.center_text.strip()
            bbox = draw.textbbox((0, 0), text, font=center_font)
            x = (width - (bbox[2] - bbox[0])) // 2
            y = (height - (bbox[3] - bbox[1])) // 2
            _draw_text_with_stroke(
                draw,
                (x, y),
                text,
                center_font,
                _hex_to_rgba(options.center_color, alpha),
                _hex_to_rgba(options.center_stroke_color, alpha),
                max(1, int(min(width, height) * options.center_font_ratio) // 20),
            )

        # --- 左侧信息面板 ---
        if options.left_enabled:
            info = read_img_gps(img_path)
            lines: list[str] = []

            if options.include_filename:
                lines.append(f'文件名：{os.path.basename(img_path)}')

            if options.include_lonlat:
                if info.has_gps:
                    lines.extend([
                        f'经度：{info.lon:.8f}',
                        f'纬度：{info.lat:.8f}',
                    ])
                else:
                    lines.extend(['经度：无GPS', '纬度：无GPS'])

            if options.include_address:
                if info.has_gps:
                    lines.append(f'地址：{get_address_from_latlng(info.lat, info.lon)}')
                else:
                    lines.append('地址：无GPS')

            if options.include_time:
                lines.append(f'时间：{info.capture_time or "未知"}')

            for line in options.custom_lines.splitlines():
                if line.strip():
                    lines.append(line.strip())

            if lines:
                line_h = options.left_font_size + 4
                x = 12
                y0 = max(8, height - line_h * len(lines) - 12)
                for i, line in enumerate(lines):
                    _draw_text_with_stroke(
                        draw,
                        (x, y0 + i * line_h),
                        line,
                        left_font,
                        _hex_to_rgba(options.left_color, 255),
                        _hex_to_rgba(options.left_stroke_color, 255),
                        options.left_stroke_width,
                    )

        final_img = Image.alpha_composite(img, watermark).convert('RGB')
        kwargs = {'quality': 95}
        if origin_exif:
            kwargs['exif'] = origin_exif
        final_img.save(output_path, **kwargs)
        return True
    except Exception as e:
        print(f'添加水印失败：{e}')
        return False
