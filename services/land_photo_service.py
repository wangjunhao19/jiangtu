"""图斑-照片匹配与整理服务。

提供 KML 图斑手工解析、照片-图斑空间匹配、按图斑整理/重命名照片等功能。
"""

import os
import re
import shutil
import xml.etree.ElementTree as ET
from typing import Callable, Iterable, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
from pyproj import Transformer

from models.image_info import ImageInfo
from services.kml_service import export_points_kml
from services.output_trace_service import append_kml_trace

KML_NS = {'kml': 'http://www.opengis.net/kml/2.2'}


def _safe_name(value='未命名地块', fallback: str = None) -> str:
    """将任意值转成安全的文件名片段。"""
    text = str(value or fallback).strip()
    text = re.sub(r'[\\/:*?"<>|\r\n]+', '_', text)
    return text[:80] or fallback


def _strip_ns(tag: str) -> str:
    """去除 XML namespace 前缀。"""
    if '}' in tag:
        return tag.split('}', 1)[-1]
    return tag


def _text(el) -> str:
    """安全获取元素文本。"""
    if el is not None and el.text is not None:
        return el.text.strip()
    return ''


def _parse_coords_text(text: str) -> list[tuple[float, float]]:
    """解析 KML coordinates：lon,lat[,alt] lon,lat[,alt]。"""
    pts: list[tuple[float, float]] = []
    for item in (text or '').replace('\n', ' ').replace('\t', ' ').split():
        parts = item.split(',')
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                pts.append((lon, lat))
            except Exception:
                continue
    return pts


def _polygon_from_node(poly_node) -> Polygon | None:
    """从 KML Polygon 节点构造 Shapely Polygon。"""
    rings: list[list[tuple[float, float]]] = []
    for coord_node in poly_node.findall('.//kml:LinearRing/kml:coordinates', KML_NS):
        coords = _parse_coords_text(_text(coord_node))
        if len(coords) >= 4:
            rings.append(coords)
    if not rings:
        return None
    exterior = rings[0]
    holes = rings[1:] if len(rings) > 1 else None
    try:
        poly = Polygon(exterior, holes)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        return poly
    except Exception:
        return None


def _extract_placemark_attrs(pm) -> dict:
    """从 Placemark 节点提取名称、描述和扩展属性。"""
    name = _text(pm.find('kml:name', KML_NS)) or _text(pm.find('name'))
    desc = _text(pm.find('kml:description', KML_NS)) or _text(pm.find('description'))
    attrs: dict = {'name': name, 'description': desc}
    for data in pm.findall('.//kml:ExtendedData/kml:Data', KML_NS) + pm.findall('.//ExtendedData/Data'):
        key = data.attrib.get('name', '').strip()
        val = _text(data.find('kml:value', KML_NS)) or _text(data.find('value'))
        if key and val:
            attrs[key] = val
    if 'landcode' not in attrs:
        attrs['landcode'] = name
    return attrs


def _read_kml_by_hand(path: str) -> gpd.GeoDataFrame:
    """手动读取 KML 图斑，避免 EXE 环境 Fiona/GDAL 不支持 KML 驱动。"""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f'KML解析失败：{os.path.basename(path)} - {e}') from e

    placemarks = root.findall('.//kml:Placemark', KML_NS)
    if not placemarks:
        placemarks = [el for el in root.iter() if _strip_ns(el.tag) == 'Placemark']

    rows: list[dict] = []
    geoms: list = []
    for idx, pm in enumerate(placemarks):
        attrs = _extract_placemark_attrs(pm)
        polys: list = []
        poly_nodes = pm.findall('.//kml:Polygon', KML_NS)
        if not poly_nodes:
            poly_nodes = [el for el in pm.iter() if _strip_ns(el.tag) == 'Polygon']
        for poly_node in poly_nodes:
            poly = _polygon_from_node(poly_node)
            if poly is not None:
                polys.append(poly)
        if not polys:
            continue
        geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            continue

        attrs['source_file'] = os.path.basename(path)
        if not attrs.get('name'):
            attrs['name'] = f'图斑_{idx + 1}'
        rows.append(attrs)
        geoms.append(geom)

    if not geoms:
        raise ValueError(f'KML中未读取到有效图斑：{os.path.basename(path)}')
    return gpd.GeoDataFrame(rows, geometry=geoms, crs='EPSG:4326')


def read_land_kml_files(paths: Iterable[str]) -> gpd.GeoDataFrame:
    """读取多个图斑 KML。

    关键：这里不使用 gpd.read_file(..., driver='KML')，避免 PyInstaller 打包后
    Fiona/GDAL 报 unsupported driver: 'KML'。
    """
    frames: list[gpd.GeoDataFrame] = []
    for path in paths:
        if path and os.path.exists(path):
            frames.append(_read_kml_by_hand(path))
    if not frames:
        raise ValueError('没有可读取的KML图斑文件')
    lands = pd.concat(frames, ignore_index=True)
    lands = gpd.GeoDataFrame(lands, geometry='geometry', crs='EPSG:4326')
    return lands


def export_land_centers(kml_paths: list[str], output_path: str) -> int:
    """导出图斑中心点到 KML 或 TSV 文件。"""
    lands = read_land_kml_files(kml_paths)
    metric_crs = _estimate_metric_crs(lands)
    metric = lands.to_crs(metric_crs)
    centers_metric = metric.geometry.centroid
    centers = gpd.GeoSeries(centers_metric, crs=metric_crs).to_crs(4326)

    points: list[dict] = []
    for idx, row in lands.iterrows():
        pt = centers.iloc[idx]
        name = row.get('landcode') or row.get('name') or row.get('Name') or f'地块中心_{idx + 1}'
        points.append({'name': str(name), 'lon': pt.x, 'lat': pt.y})

    if output_path.lower().endswith('.kml'):
        export_points_kml(points, output_path)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('地块名称\t经度\t纬度\n')
            for p in points:
                f.write(f"{p['name']}\t{p['lon']:.8f}\t{p['lat']:.8f}\n")
    return len(points)


def _coords_for_kml(geom) -> str:
    """将多边形外环坐标序列化为 KML coordinates 文本。"""
    return ' '.join(f'{x:.10f},{y:.10f},0' for x, y in list(geom.exterior.coords))


def export_no_photo_lands_kml(no_photo_rows: list[tuple[str, object]], output_path: str) -> None:
    """输出没有照片匹配的图斑KML，红色半透明面，便于导入地图核查。"""
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        '<name>无照片图斑</name>',
        '<Style id="noPhotoLand"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle><PolyStyle><color>660000ff</color></PolyStyle></Style>',
    ]
    for name, geom in no_photo_rows:
        if getattr(geom, 'geom_type', '') == 'MultiPolygon':
            geoms = list(geom.geoms)
        else:
            geoms = [geom]
        for i, poly in enumerate(geoms, start=1):
            if poly.is_empty:
                continue
            nm = _safe_name(name) if len(geoms) == 1 else _safe_name(f'{name}_{i}')
            parts.append(
                f'<Placemark><name>{nm}</name>'
                f'<styleUrl>#noPhotoLand</styleUrl>'
                f'<description>该图斑未匹配到照片</description>'
                f'<Polygon><outerBoundaryIs><LinearRing><coordinates>'
                f'{_coords_for_kml(poly)}'
                f'</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'
            )
    parts.append('</Document></kml>')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(append_kml_trace(''.join(parts), 'no_photo_land_kml'))


def _ensure_writable_dir(path: str) -> None:
    """提前检测输出目录可写，避免整理到一半才 Permission denied。"""
    os.makedirs(path, exist_ok=True)
    test_path = os.path.join(path, '.jt_write_test.tmp')
    try:
        with open(test_path, 'w', encoding='utf-8') as f:
            f.write('ok')
    except PermissionError as e:
        raise PermissionError(
            f'当前输出目录没有写入权限，或被系统/网盘/杀毒软件锁定。请在桌面新建一个空文件夹作为输出目录后重试。\n输出目录：{path}'
        ) from e
    finally:
        if os.path.exists(test_path):
            try:
                os.remove(test_path)
            except Exception:
                pass


def _polygonal_only(geom):
    """Repair geometry and retain only polygonal parts.

    Narrow/small parcels are kept as polygons whenever possible. GeometryCollection results from
    make-valid are reduced to their Polygon/MultiPolygon components instead of being silently lost.
    """
    if geom is None or getattr(geom, 'is_empty', True):
        return None
    fixed = geom
    if not getattr(fixed, 'is_valid', True):
        try:
            from shapely.validation import make_valid
            fixed = make_valid(fixed)
        except Exception:
            try:
                fixed = fixed.buffer(0)
            except Exception:
                return None
    if getattr(fixed, 'is_empty', True):
        return None
    gt = getattr(fixed, 'geom_type', '')
    if gt in ('Polygon', 'MultiPolygon'):
        return fixed
    if gt == 'GeometryCollection':
        parts = [g for g in fixed.geoms if getattr(g, 'geom_type', '') in ('Polygon', 'MultiPolygon') and not g.is_empty]
        if parts:
            merged = unary_union(parts)
            return merged if not merged.is_empty else None
    return None


def _estimate_metric_crs(lands: gpd.GeoDataFrame):
    """Choose a local metre-based CRS, normally the UTM zone covering the task."""
    try:
        crs = lands.estimate_utm_crs()
        if crs:
            return crs
    except Exception:
        pass
    try:
        centre = lands.to_crs(4326).geometry.unary_union.centroid
        zone = max(1, min(60, int(float(centre.x) + 180) // 6 + 1))
        return f'EPSG:{32600 + zone if float(centre.y) >= 0 else 32700 + zone}'
    except Exception:
        return 'EPSG:3857'


def _prepare_land_records(lands: gpd.GeoDataFrame) -> tuple[list[dict], object]:
    """修复几何、转度量坐标系，返回 (records, metric_crs)。"""
    lands_wgs = lands.to_crs(4326).copy()
    repaired: list = []
    keep_rows: list = []
    for idx, row in lands_wgs.iterrows():
        geom = _polygonal_only(row.geometry)
        if geom is None:
            continue
        keep_rows.append(row)
        repaired.append(geom)
    if not repaired:
        raise ValueError('图斑文件中没有可用于匹配的有效面图斑')

    clean = gpd.GeoDataFrame(keep_rows, geometry=repaired, crs='EPSG:4326').reset_index(drop=True)
    metric_crs = _estimate_metric_crs(clean)
    metric = clean.to_crs(metric_crs)

    records: list[dict] = []
    for idx, row in metric.iterrows():
        source = clean.iloc[idx]
        name = source.get('landcode') or source.get('name') or source.get('Name') or f'图斑_{idx + 1}'
        records.append({
            'name': str(name),
            'folder': _safe_name(name, fallback=f'图斑_{idx + 1}'),
            'geom': row.geometry,
            'wgs_geom': source.geometry,
            'count': 0,
        })
    return records, metric_crs


def _point_match_for_land(geom, pt, match_distance_m: float) -> tuple[bool, float, str]:
    """Match a photo point using containment first, then exact distance to parcel boundary."""
    try:
        inside = bool(geom.covers(pt))
    except Exception:
        inside = bool(geom.contains(pt) or geom.touches(pt))
    if inside:
        return (True, 0, '图斑内')

    try:
        distance = float(geom.boundary.distance(pt))
    except Exception:
        distance = float(geom.distance(pt))

    if match_distance_m > 0 and distance <= match_distance_m + 1e-6:
        return (True, distance, '图斑边缘距离范围内')
    return (False, distance, '未匹配')


def _find_best_land(pt, records: list[dict], match_distance_m: float) -> tuple[dict | None, float, str, dict | None, float]:
    """在所有图斑中为照片点找最佳匹配：优先图斑内最小面积，其次距离最近。"""
    best_inside = None
    best_inside_area = float('inf')
    nearest = None
    nearest_distance = float('inf')

    for rec in records:
        geom = rec['geom']
        try:
            matched, distance, match_type = _point_match_for_land(geom, pt, match_distance_m)
        except Exception:
            continue

        if distance < nearest_distance:
            nearest = rec
            nearest_distance = distance

        if match_type == '图斑内':
            area = float(getattr(geom, 'area', 0) or 0)
            if area < best_inside_area:
                best_inside_area = area
                best_inside = rec

    if best_inside is not None:
        return (best_inside, 0, '图斑内', nearest, nearest_distance)
    if nearest is not None and match_distance_m > 0 and nearest_distance <= match_distance_m + 1e-6:
        return (nearest, nearest_distance, '图斑边缘距离范围内', nearest, nearest_distance)
    return (None, nearest_distance, '未匹配', nearest, nearest_distance)


def _write_distance_match_report(output_dir: str, rows: list[dict]) -> None:
    """写出图斑边缘距离匹配照片清单。"""
    if not rows:
        return
    path = os.path.join(output_dir, '图斑边缘距离匹配照片清单.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('照片文件\t匹配图斑\t到图斑边缘距离米\t目标文件\n')
        for row in rows:
            f.write(f"{row.get('filename', '')}\t{row.get('land', '')}\t{float(row.get('distance_m', 0)):.2f}\t{row.get('target', '')}\n")


def _write_unmatched_report(output_dir: str, rows: list[dict]) -> None:
    """写出未匹配照片最近图斑距离清单。"""
    if not rows:
        return
    path = os.path.join(output_dir, '未匹配照片最近图斑距离.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('照片文件\t经度\t纬度\t最近图斑\t到最近图斑边缘距离米\n')
        for row in rows:
            distance = row.get('distance_m')
            if distance is None or distance == float('inf'):
                distance_text = ''
            else:
                distance_text = f'{float(distance):.2f}'
            f.write(f"{row.get('filename', '')}\t{row.get('lon', '')}\t{row.get('lat', '')}\t{row.get('nearest_land', '')}\t{distance_text}\n")


def _unique_target(directory: str, filename: str) -> str:
    """在目录中生成不重复的目标文件路径。"""
    target = os.path.join(directory, filename)
    if not os.path.exists(target):
        return target
    base, ext = os.path.splitext(filename)
    number = 1
    while os.path.exists(os.path.join(directory, f'{base}_{number}{ext}')):
        number += 1
    return os.path.join(directory, f'{base}_{number}{ext}')


def _write_empty_land_supplement_report(output_dir: str, rows: list[dict]) -> None:
    """记录原本无内部照片、后续按边界距离补充进去的照片。"""
    if not rows:
        return
    path = os.path.join(output_dir, '无照片图斑边缘补充匹配清单.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('图斑\t照片文件\t到图斑边缘距离米\t说明\n')
        for row in rows:
            f.write(f"{row.get('land', '')}\t{row.get('filename', '')}\t{float(row.get('distance_m', 0)):.2f}\t{row.get('match_type', '')}\n")


def organize_photos_by_land(
    img_list: list[ImageInfo],
    kml_paths: list[str],
    output_dir: str,
    copy_mode: bool = True,
    match_distance_m: float = 0,
) -> dict[str, int]:
    """按照图斑整理照片。

    匹配严格分两步：
    1. 第一遍只分类"照片点位位于图斑内部"的照片，不使用距离吸附；
    2. 第二遍只处理第一遍内部照片数为 0 的图斑，再按用户设置的边界距离吸附。
       第一遍已有内部照片的图斑不参与第二遍。补充阶段允许同一张照片同时进入
       相邻的空图斑文件夹，用于解决狭长、细小图斑没有现场照片的问题。
    """
    _ensure_writable_dir(output_dir)
    match_distance_m = max(0, min(300, float(match_distance_m or 0)))

    records, metric_crs = _prepare_land_records(read_land_kml_files(kml_paths))
    transformer = Transformer.from_crs('EPSG:4326', metric_crs, always_xy=True)

    infos = [item for item in img_list if item.has_gps and item.lat is not None and item.lon is not None]
    if not infos:
        raise ValueError('当前图片没有可用GPS点')

    counts: dict[str, int] = {}
    used: set[str] = set()
    for rec in records:
        folder = rec['folder']
        base = folder
        serial = 1
        while folder in used:
            serial += 1
            folder = _safe_name(f'{base}_{serial}')
        used.add(folder)
        rec['folder'] = folder
        rec['dir'] = os.path.join(output_dir, folder)
        rec['primary_count'] = 0
        rec['count'] = 0
        os.makedirs(rec['dir'], exist_ok=True)
        counts[folder] = 0

    # -- 第一遍：仅内部包含 --
    entries: list[dict] = []
    for info in infos:
        x, y = transformer.transform(float(info.lon), float(info.lat))
        pt = Point(x, y)
        best, distance, match_type, nearest, nearest_distance = _find_best_land(pt, records, 0)
        if best is not None:
            best['primary_count'] += 1
        entries.append({
            'info': info,
            'pt': pt,
            'primary': best,
            'primary_distance': distance,
            'primary_type': match_type,
            'nearest': nearest,
            'nearest_distance': nearest_distance,
            'supplements': [],
        })

    # -- 第二遍：距离吸附补充（仅空图斑） --
    supplement_rows: list[dict] = []
    if match_distance_m > 0:
        empty_records = [rec for rec in records if int(rec.get('primary_count', 0)) <= 0]
        for rec in empty_records:
            candidates: list = []
            for entry in entries:
                try:
                    matched, distance, match_type = _point_match_for_land(rec['geom'], entry['pt'], match_distance_m)
                except Exception:
                    continue
                if matched:
                    candidates.append((float(distance), str(entry['info'].filename).lower(), entry, match_type))
            candidates.sort(key=lambda item: (item[0], item[1]))
            for distance, _filename_key, entry, match_type in candidates:
                entry['supplements'].append({'record': rec, 'distance': distance, 'match_type': match_type})
                supplement_rows.append({
                    'land': rec['name'],
                    'filename': entry['info'].filename,
                    'distance_m': distance,
                    'match_type': '图斑内补充' if match_type == '图斑内' else '无照片图斑边缘补充',
                })

    # -- 输出阶段 --
    unmatched_dir = os.path.join(output_dir, '未匹配图斑')
    os.makedirs(unmatched_dir, exist_ok=True)
    unmatched_points: list[dict] = []
    unmatched_rows: list[dict] = []
    distance_rows: list[dict] = []

    for entry in entries:
        info = entry['info']
        destinations: list = []
        primary = entry['primary']
        if primary is not None:
            destinations.append((primary, float(entry['primary_distance']), str(entry['primary_type']), False))
        seen_ids = {id(primary)} if primary is not None else set()
        for supplement in entry['supplements']:
            rec = supplement['record']
            if id(rec) in seen_ids:
                continue
            seen_ids.add(id(rec))
            destinations.append((rec, float(supplement['distance']), str(supplement['match_type']), True))

        if not destinations:
            # 未匹配照片 → 复制到 未匹配图斑 目录
            target = _unique_target(unmatched_dir, info.filename)
            try:
                if copy_mode:
                    shutil.copy2(info.full_path, target)
                else:
                    shutil.move(info.full_path, target)
            except PermissionError as exc:
                raise PermissionError(
                    f'照片复制失败：输出目录没有写入权限，或目标文件正在被占用。\n源文件：{info.full_path}\n目标文件：{target}'
                ) from exc
            counts['未匹配图斑'] = counts.get('未匹配图斑', 0) + 1
            unmatched_points.append({'name': info.filename, 'lon': info.lon, 'lat': info.lat})
            nearest = entry['nearest']
            unmatched_rows.append({
                'filename': info.filename,
                'lon': info.lon,
                'lat': info.lat,
                'nearest_land': nearest['name'] if nearest else '',
                'distance_m': entry['nearest_distance'],
            })
        else:
            for rec, distance, match_type, is_supplement in destinations:
                target = _unique_target(rec['dir'], info.filename)
                try:
                    if not copy_mode and not is_supplement and len(destinations) == 1:
                        shutil.move(info.full_path, target)
                    else:
                        shutil.copy2(info.full_path, target)
                except PermissionError as exc:
                    raise PermissionError(
                        f'照片复制失败：输出目录没有写入权限，或目标文件正在被占用。\n源文件：{info.full_path}\n目标文件：{target}'
                    ) from exc
                rec['count'] += 1
                counts[rec['folder']] = counts.get(rec['folder'], 0) + 1
                if match_type == '图斑边缘距离范围内' or is_supplement:
                    distance_rows.append({
                        'filename': info.filename,
                        'land': rec['name'],
                        'distance_m': distance,
                        'target': target,
                    })

    # -- 生成报告 --
    no_photo = [(rec['name'], rec['wgs_geom']) for rec in records if rec['count'] <= 0]
    if no_photo:
        export_no_photo_lands_kml(no_photo, os.path.join(output_dir, '无照片图斑.kml'))
    if unmatched_points:
        export_points_kml(unmatched_points, os.path.join(output_dir, '未匹配照片.kml'))
    _write_distance_match_report(output_dir, distance_rows)
    _write_empty_land_supplement_report(output_dir, supplement_rows)
    _write_unmatched_report(output_dir, unmatched_rows)
    return counts


def rename_photos_by_land(
    img_list: list[ImageInfo],
    kml_paths: list[str],
    output_dir: str,
    match_distance_m: float = 0,
    progress: Optional[Callable[[int, int], None]] = None,
) -> dict[str, int]:
    """按照"根据图斑整理照片"的同一套两遍算法匹配后重命名复制。

    第一遍仅匹配位于图斑内部的照片；第二遍只给第一遍仍无内部照片的图斑
    按边线距离补充。已有内部照片的图斑不参加第二遍。同一照片在补充阶段
    可为多个相邻空图斑各生成一个重命名副本，与整理照片行为保持一致。
    """
    _ensure_writable_dir(output_dir)
    match_distance_m = max(0, min(300, float(match_distance_m or 0)))

    records, metric_crs = _prepare_land_records(read_land_kml_files(kml_paths))
    transformer = Transformer.from_crs('EPSG:4326', metric_crs, always_xy=True)

    infos = [item for item in img_list if item.has_gps and item.lat is not None and item.lon is not None]
    if not infos:
        raise ValueError('当前图片没有可用GPS点')

    used_names: set[str] = set()
    counts: dict[str, int] = {}
    for idx, rec in enumerate(records):
        safe = rec['folder']
        base = safe
        serial = 1
        while safe in used_names:
            serial += 1
            safe = _safe_name(f'{base}_{serial}', fallback=f'图斑_{idx + 1}')
        used_names.add(safe)
        rec['safe'] = safe
        rec['primary_count'] = 0
        rec['count'] = 0
        counts[safe] = 0

    # -- 第一遍：仅内部包含 --
    entries: list[dict] = []
    for info in infos:
        x, y = transformer.transform(float(info.lon), float(info.lat))
        pt = Point(x, y)
        best, distance, match_type, nearest, nearest_distance = _find_best_land(pt, records, 0)
        if best is not None:
            best['primary_count'] += 1
        entries.append({
            'info': info,
            'pt': pt,
            'primary': best,
            'primary_distance': distance,
            'primary_type': match_type,
            'nearest': nearest,
            'nearest_distance': nearest_distance,
            'supplements': [],
        })

    # -- 第二遍：距离吸附补充（仅空图斑） --
    supplement_rows: list[dict] = []
    if match_distance_m > 0:
        empty_records = [rec for rec in records if int(rec.get('primary_count', 0)) <= 0]
        for rec in empty_records:
            candidates: list = []
            for entry in entries:
                try:
                    matched, distance, match_type = _point_match_for_land(rec['geom'], entry['pt'], match_distance_m)
                except Exception:
                    continue
                if matched:
                    candidates.append((float(distance), str(entry['info'].filename).lower(), entry, match_type))
            candidates.sort(key=lambda item: (item[0], item[1]))
            for distance, _filename_key, entry, match_type in candidates:
                entry['supplements'].append({'record': rec, 'distance': distance, 'match_type': match_type})
                supplement_rows.append({
                    'land': rec['name'],
                    'filename': entry['info'].filename,
                    'distance_m': distance,
                    'match_type': '图斑内补充' if match_type == '图斑内' else '无照片图斑边缘补充',
                })

    # -- 输出阶段 --
    unmatched_count = 0
    unmatched_points: list[dict] = []
    unmatched_rows: list[dict] = []
    distance_rows: list[dict] = []
    total_entries = len(entries) or 1

    for entry_index, entry in enumerate(entries, 1):
        info = entry['info']
        destinations: list = []
        primary = entry['primary']
        if primary is not None:
            destinations.append((primary, float(entry['primary_distance']), str(entry['primary_type']), False))
        seen_ids = {id(primary)} if primary is not None else set()
        for supplement in entry['supplements']:
            rec = supplement['record']
            if id(rec) in seen_ids:
                continue
            seen_ids.add(id(rec))
            destinations.append((rec, float(supplement['distance']), str(supplement['match_type']), True))

        ext = os.path.splitext(info.filename)[1].lower() or '.jpg'

        if not destinations:
            # 未匹配 → 重命名为 未匹配_NNNN.ext
            unmatched_count += 1
            counts['未匹配'] = counts.get('未匹配', 0) + 1
            filename = f'未匹配_{unmatched_count:04d}{ext}'
            target = _unique_target(output_dir, filename)
            try:
                shutil.copy2(info.full_path, target)
            except PermissionError as exc:
                raise PermissionError(
                    f'照片重命名复制失败：输出目录没有写入权限，或目标文件正在被占用。\n源文件：{info.full_path}\n目标文件：{target}'
                ) from exc
            unmatched_points.append({'name': info.filename, 'lon': info.lon, 'lat': info.lat})
            nearest = entry['nearest']
            unmatched_rows.append({
                'filename': info.filename,
                'lon': info.lon,
                'lat': info.lat,
                'nearest_land': nearest['name'] if nearest else '',
                'distance_m': entry['nearest_distance'],
            })
            if progress:
                progress(entry_index, total_entries)
        else:
            for rec, distance, match_type, is_supplement in destinations:
                rec['count'] += 1
                counts[rec['safe']] = counts.get(rec['safe'], 0) + 1
                filename = f"{rec['safe']}_{rec['count']:04d}{ext}"
                target = _unique_target(output_dir, filename)
                try:
                    shutil.copy2(info.full_path, target)
                except PermissionError as exc:
                    raise PermissionError(
                        f'照片重命名复制失败：输出目录没有写入权限，或目标文件正在被占用。\n源文件：{info.full_path}\n目标文件：{target}'
                    ) from exc
                if match_type == '图斑边缘距离范围内' or is_supplement:
                    distance_rows.append({
                        'filename': info.filename,
                        'land': rec['name'],
                        'distance_m': distance,
                        'target': target,
                    })
            if progress:
                progress(entry_index, total_entries)

    # -- 生成报告 --
    no_photo = [(rec['name'], rec['wgs_geom']) for rec in records if rec['count'] <= 0]
    if no_photo:
        export_no_photo_lands_kml(no_photo, os.path.join(output_dir, '无照片图斑.kml'))
    if unmatched_points:
        export_points_kml(unmatched_points, os.path.join(output_dir, '未匹配照片.kml'))
    _write_distance_match_report(output_dir, distance_rows)
    _write_empty_land_supplement_report(output_dir, supplement_rows)
    _write_unmatched_report(output_dir, unmatched_rows)
    return counts
