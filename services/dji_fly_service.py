# Source Generated with Decompyle++
# File: dji_fly_service.pyc (Python 3.11)

from __future__ import annotations

__doc__ = 'DJI Fly / WPML 风格航点任务生成。\n\n当前界面口径：\n- 三资图斑只生成图斑内部正射拍摄点：小图斑1张，大图斑最多10张。\n- 正射影像按图斑多边形内部生成南到北 S 型航线，不按外接矩形全区域飞。\n- 自定义只保留沿边巡查。\n- 输出一个 DJI Fly KMZ。\n\n注意：消费级 DJI Fly 的 KMZ 兼容性会随 APP/固件变化，生成后必须先在 DJI Fly 内检查再飞。\n'
import math
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import xml.sax.saxutils as saxutils
from io import BytesIO
import urllib.request as urllib
import geopandas as gpd
from shapely.geometry import Point, LineString
from pyproj import Transformer
from services.land_photo_service import read_land_kml_files
from services.output_trace_service import append_kml_trace
MissionType = Literal[('center', 'asset_photo', 'asset_single_5shot', 'asset_5shot', 'cross', 'edge', 'square', 'grid', 'model3d')]
MIN_ASSET_OFFSET_M = 8
MissionTemplate = Literal[('custom', 'asset', 'orthophoto', 'model3d')]
ActionType = Literal[('photo', 'hover', 'video')]
OrderType = Literal[('name', 'west_east', 'south_north', 'nearest')]
WPML_NS = 'http://www.uav.com/wpmz/1.0.2'


@dataclass
class DjiMissionOptions:
    kml_paths: list = None
    output_target: str = ''
    altitude_m: float = 60.0
    speed_ms: float = 5.0
    gimbal_pitch: float = -90.0
    heading_mode: str = 'along_path'
    finish_action: str = 'hover'
    takeoff_altitude: float = 0.0
    photo_interval_s: float = 2.0
    ortho_overlap: float = 70.0
    side_overlap: float = 60.0
    mission_template: str = 'orthophoto'
    mission_order: str = 'south_north'
    drone_profile: str = 'default'
    max_photos_per_land: int = 10
    sensor_width_mm: float = 13.2
    sensor_height_mm: float = 8.8
    image_width_px: int = 4000
    image_height_px: int = 3000
    focal_length_mm: float = 8.8


DRONE_PROFILES = {
    'default': {'name': '默认', 'altitude': 60, 'speed': 5, 'sensor_width': 13.2, 'sensor_height': 8.8, 'image_width': 4000, 'image_height': 3000, 'focal_length': 8.8},
    'mini3': {'name': 'Mini 3', 'altitude': 50, 'speed': 5, 'sensor_width': 9.7, 'sensor_height': 7.3, 'image_width': 4000, 'image_height': 3000, 'focal_length': 6.72},
    'air2s': {'name': 'Air 2S', 'altitude': 60, 'speed': 6, 'sensor_width': 13.2, 'sensor_height': 8.8, 'image_width': 5472, 'image_height': 3648, 'focal_length': 8.8},
    'mavic3': {'name': 'Mavic 3', 'altitude': 80, 'speed': 7, 'sensor_width': 17.3, 'sensor_height': 13.0, 'image_width': 5280, 'image_height': 3956, 'focal_length': 12.29},
}


def get_drone_profile_name(name=None):
    key = str(name or 'default').lower().strip()
    profile = DRONE_PROFILES.get(key, DRONE_PROFILES['default'])
    return profile['name']


def get_drone_profile(name=None):
    key = str(name or 'default').lower().strip()
    return dict(DRONE_PROFILES.get(key, DRONE_PROFILES['default']))


def drone_profile_summary(name=None):
    profile = get_drone_profile(name)
    return f"{profile['name']} ({profile['image_width']}x{profile['image_height']}, f={profile['focal_length']}mm)"


def _safe_text(value=None):
    text = str(value or '').strip()
    return text if text.lower() not in ('none', 'null', 'nan', '') else ''


def _land_name(row=None, idx=0):
    if isinstance(row, dict):
        for key in ('landname', 'name', 'landcode', 'landName'):
            text = _safe_text(row.get(key))
            if text:
                return text
    return f'图斑{idx + 1}'


def _metric_lands(kml_paths=None):
    lands = []
    for path in (kml_paths or []):
        try:
            gdf = gpd.read_file(path)
            for _, row in gdf.iterrows():
                lands.append({'geometry': row.geometry, 'name': _land_name(row, len(lands))})
        except Exception:
            pass
    return lands


def build_mission_points(kml_paths=None, options=None):
    """构建航线任务点列表。"""
    opts = options or DjiMissionOptions()
    lands = _metric_lands(kml_paths)
    points = []
    for idx, land in enumerate(lands):
        geom = land['geometry']
        name = land.get('name', f'图斑{idx + 1}')
        if geom.is_empty:
            continue
        centroid = geom.centroid
        points.append({
            'x': centroid.x, 'y': centroid.y,
            'name': name, 'seq': len(points),
            'task_type': 'center', 'heading': 0,
            'gimbal_pitch': opts.gimbal_pitch,
        })
    return points


def _template_kml(points=None, options=None):
    """生成 DJI Fly 格式的 KML 模板。"""
    opts = options or DjiMissionOptions()
    placemarks = []
    for p in (points or []):
        x, y = p.get('x', 0), p.get('y', 0)
        name = saxutils.escape(str(p.get('name', '')))
        alt = opts.altitude_m
        placemarks.append(
            f'<Placemark><name>{name}</name>'
            f'<Point><coordinates>{x},{y},{alt}</coordinates></Point></Placemark>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        f'<Document>{"" .join(placemarks)}</Document></kml>'
    )


def _waylines_wpml(points=None, options=None):
    return b''


def _write_one_kmz(points=None, output_kmz=None, options=None):
    opts = options or DjiMissionOptions()
    kml_content = _template_kml(points, opts)
    with zipfile.ZipFile(str(output_kmz), 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('wpmz/template.kml', kml_content)


def _safe_filename(value=None):
    text = str(value or 'mission').strip()
    for ch in '<>:"/\\|?*':
        text = text.replace(ch, '_')
    return text or 'mission'


def _resolve_output_target(output_target=None, options=None):
    target = str(output_target or '')
    if target.lower().endswith('.kmz'):
        return target
    return os.path.join(target or '.', f'{_safe_filename("mission")}.kmz')


def export_dji_fly_kmz(kml_paths=None, output_target=None, options=None):
    """导出 DJI Fly KMZ 文件。"""
    opts = options or DjiMissionOptions()
    points = build_mission_points(kml_paths, opts)
    if not points:
        return ''
    target = _resolve_output_target(output_target, opts)
    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
    _write_one_kmz(points, target, opts)
    return target


def export_mission_preview_kml(kml_paths=None, output_kml=None, options=None):
    """导出航线预览 KML。"""
    opts = options or DjiMissionOptions()
    points = build_mission_points(kml_paths, opts)
    content = _template_kml(points, opts)
    if output_kml:
        os.makedirs(os.path.dirname(str(output_kml)) or '.', exist_ok=True)
        with open(str(output_kml), 'w', encoding='utf-8') as f:
            f.write(content)
    return str(output_kml or '')


def estimate_mission_stats(kml_paths=None, options=None):
    """估算航线任务统计信息。"""
    opts = options or DjiMissionOptions()
    points = build_mission_points(kml_paths, opts)
    return {
        'point_count': len(points),
        'land_count': len(set(p.get('name', '') for p in points)),
        'altitude': opts.altitude_m,
        'speed': opts.speed_ms,
    }
