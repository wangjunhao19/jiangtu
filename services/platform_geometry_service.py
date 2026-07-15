# Source Generated with Decompyle++
# File: platform_geometry_service.pyc (Python 3.11)

from __future__ import annotations
from copy import deepcopy
import math
from typing import Any
LONGITUDE_OFFSET = -0.00015
LATITUDE_OFFSET = 5.4e-05

def _shift_lon_lat(lon = None, lat = None, east_m = None, north_m = (0, 0)):
    '''固定平台偏移后，再按米数向东/向北平移。'''
    lat2 = float(lat) + LATITUDE_OFFSET
    lon2 = float(lon) + LONGITUDE_OFFSET
    if north_m:
        lat2 += float(north_m) / 110540
    if east_m:
        lon2 += float(east_m) / (111320 * max(math.cos(math.radians(lat2)), 1e-06))
    return (lon2, lat2)


def _shift_position(position=None, east_m=None, north_m=None):
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        return deepcopy(position)
    (lon, lat) = _shift_lon_lat(position[0], position[1], east_m, north_m)
    return [lon, lat]


def correct_platform_geometry(geometry=None, east_offset_m=None, north_offset_m=None):
    '''返回修正后的 GeoJSON geometry，不修改原对象。

    支持 Point、MultiPoint、LineString、MultiLineString、Polygon、
    MultiPolygon 和 GeometryCollection。
    '''
    if not isinstance(geometry, dict):
        raise TypeError('geometry 必须是 GeoJSON 字典')
    result = deepcopy(geometry)
    gtype = str(result.get('type') or '')
    coords = result.get('coordinates')

    if gtype == 'Point':
        result['coordinates'] = _shift_position(coords, east_offset_m, north_offset_m)

    elif gtype in ('LineString', 'MultiPoint'):
        result['coordinates'] = [
            _shift_position(p, east_offset_m, north_offset_m)
            for p in (coords or [])
        ]

    elif gtype in ('Polygon', 'MultiLineString'):
        result['coordinates'] = [
            [_shift_position(p, east_offset_m, north_offset_m) for p in line]
            for line in (coords or [])
        ]

    elif gtype == 'MultiPolygon':
        result['coordinates'] = [
            [
                [_shift_position(p, east_offset_m, north_offset_m) for p in ring]
                for ring in polygon
            ]
            for polygon in (coords or [])
        ]

    elif gtype == 'GeometryCollection':
        result['geometries'] = [
            correct_platform_geometry(g, east_offset_m, north_offset_m)
            for g in (result.get('geometries') or [])
            if isinstance(g, dict)
        ]

    return result

