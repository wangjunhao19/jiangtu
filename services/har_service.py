# Source Generated with Decompyle++
# File: har_service.pyc (Python 3.11)

import base64
import gzip
import json
import os
import re
import urllib.parse as urllib
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from shapely.validation import make_valid
from config import STATUS_CFG
from services.kml_service import write_land_kml
from services.output_trace_service import add_trace_to_report
from services.platform_geometry_service import LATITUDE_OFFSET, LONGITUDE_OFFSET, correct_platform_geometry
USE_STATUS_LABELS = {
    '0': '对外发包',
    '1': '不规范使用',
    '2': '征收征占',
    '3': '闲置',
    '4': '外部（内部）飞地',
    '5': '村民自留地（菜地）',
    '6': '抵顶地',
    '7': '村集体自用-经营性',
    '8': '村集体自用-公共性',
    '9': '争议待确权地',
    '10': '田间硬化路面',
    '11': '村民自用',
    '12': '无争议未确权承包地',
    '13': '延包后村集体再分地',
    '14': '已确权承包地' }
LAND_ACTUALITY_LABELS = {
    '0': '耕地',
    '1': '林地',
    '2': '园地',
    '3': '工矿仓储用地',
    '4': '商业服务业设施用地',
    '5': '养殖水面（坑塘水面）',
    '6': '四荒地',
    '7': '滩涂',
    '8': '设施农用地',
    '9': '田埂地边地',
    '10': '宅基地',
    '11': '交通运输用地',
    '12': '公共管理与公共服务用地',
    '13': '水域及水利设施用地',
    '14': '城镇住宅用地' }

def _first_item_value(item=None, *keys):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() not in {'', 'None', 'null'}:
            return value
    return ""


def _label_value(value=None, mapping=None):
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        normalized = text[:-2]
    else:
        normalized = text
    return mapping.get(normalized, text)


def correct_coords(geom = None, east_offset_m = None, north_offset_m = None):
    '''兼容旧调用：HAR与三资照片整理统一使用同一坐标修正规则。'''
    return correct_platform_geometry(geom, east_offset_m, north_offset_m)


def _query_params(url = None):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def _status_filename(url=None, item=None):
    decoded = urllib.parse.unquote(url)
    candidates = [url, decoded]
    status_value = None
    if item:
        status_value = item.get("landstatus") or item.get("land_status") or item.get("status")
        if status_value is not None:
            candidates.append(str(status_value))
    params = _query_params(url)
    for key in ('landstatus', 'landStatus', 'status', 'state'):
        if key in params:
            candidates.extend(params[key])
    for code, (file_name, _) in STATUS_CFG.items():
        decoded_code = urllib.parse.unquote(code).strip("'")
        for c in candidates:
            if code in c or f"'{decoded_code}'" in c or str(decoded_code) == str(c).strip("'"):
                return file_name
    return None


def _decode_content(content=None):
    text = content.get("text") or ""
    if not text:
        return ""
    encoding = (content.get("encoding") or "").lower()
    if encoding == "base64":
        raw = base64.b64decode(text)
        for fn in (gzip.decompress, zlib.decompress):
            try:
                raw = fn(raw)
            except Exception:
                pass
        return raw.decode("utf-8", errors="ignore")
    return text


def _find_records(obj=None):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ('rows', 'data', 'records', 'items', 'list'):
            value = obj.get(key)
            if isinstance(value, list) and value:
                return value
    return []


def _load_json_records(text=None):
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return []
    return _find_records(data)


def _item_to_feature(item=None, east_offset_m=None, north_offset_m=None):
    if not isinstance(item, dict):
        return None
    geom_data = item.get('geometry') or item.get('geom')
    if not geom_data:
        return None
    try:
        geom = shape(geom_data)
        geom = make_valid(geom)
    except Exception:
        return None
    if east_offset_m or north_offset_m:
        geom = correct_coords(geom, east_offset_m, north_offset_m)
    props = {}
    for key in ('landcode', 'landname', 'landstatus', 'landCode', 'landName'):
        value = item.get(key)
        if value is not None:
            props[key] = str(value)
    return {'geometry': geom, 'properties': props}


def _dedupe_gdf(gdf=None):
    if gdf is None or gdf.empty:
        return gdf
    return gdf.drop_duplicates(subset=['landcode'], keep='first') if 'landcode' in gdf.columns else gdf


def _extract_census_counts(har=None):
    return Counter()


def _status_desc(status=None):
    return USE_STATUS_LABELS.get(str(status).strip(), str(status or ''))


def _status_to_filename(status=None):
    desc = _status_desc(status)
    return desc if desc else '其他'


def _status_from_url(url=None):
    for code, (filename, _) in STATUS_CFG.items():
        if code in str(url):
            return filename
    return None


def _safe_name(value=None):
    text = str(value or '').strip()
    for ch in '<>:"/\\|?*':
        text = text.replace(ch, '_')
    return text or '未命名'


def _layer_name(url=None):
    decoded = urllib.parse.unquote(str(url or ''))
    return decoded


def _where_text(url=None):
    params = urllib.parse.parse_qs(urllib.parse.urlparse(str(url or '')).query)
    for key in ('where', 'Where', 'WHERE'):
        values = params.get(key, [])
        if values:
            return values[0]
    return ''


def _where_value(url=None, field=None):
    text = _where_text(url)
    if not text or not field:
        return ''
    pattern = re.compile(rf"{re.escape(field)}\s*=\s*'([^']*)'")
    match = pattern.search(text)
    return match.group(1) if match else ''


def _record_code(item=None, entry_index=0, item_index=0):
    if isinstance(item, dict):
        return str(item.get('landcode', f'entry{entry_index}_item{item_index}'))
    return f'entry{entry_index}_item{item_index}'


def _subcategory_for_entry(layer=None, url=None, item=None):
    return 'default'


def _collect_har_classified(har=None, emit=None):
    return []


def _build_gdf_from_items(items=None, category='', leaf='', east_offset_m=None, north_offset_m=None, emit=None):
    features = []
    for item in (items or []):
        feature = _item_to_feature(item, east_offset_m, north_offset_m)
        if feature:
            features.append(feature)
    if not features:
        return None
    return gpd.GeoDataFrame(features)


def _write_empty_note(folder=None, category='', leaf=''):
    if not folder:
        return
    path = Path(folder) / f'{_safe_name(category or leaf or "empty")}.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'({category}/{leaf}) 无匹配数据\n', encoding='utf-8')


def parse_har_work_to_kml(har_path=None, output_dir=None, log=None, east_offset_m=None, north_offset_m=None):
    """\u89e3\u6790\u5de5\u4f5cHAR\u6587\u4ef6\u751f\u6210KML\u3002"""
    results = []
    if not har_path or not os.path.isfile(har_path):
        return results
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    entries = har.get('log', {}).get('entries', []) if isinstance(har, dict) else []
    os.makedirs(str(output_dir or '.'), exist_ok=True)
    return results


def parse_har_classified_to_kml(har_path=None, output_dir=None, log=None, east_offset_m=None, north_offset_m=None):
    """\u89e3\u6790\u5206\u7c7bHAR\u6587\u4ef6\u751f\u6210KML\u3002"""
    results = []
    if not har_path or not os.path.isfile(har_path):
        return results
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    os.makedirs(str(output_dir or '.'), exist_ok=True)
    return results
