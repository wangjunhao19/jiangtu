# Source Generated with Decompyle++
# File: sanzi_photo_service.pyc (Python 3.11)

from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from models.image_info import ImageInfo
from services.image_service import ImageCache, read_img_gps
from services.kml_service import export_points_kml
from services.output_trace_service import add_trace_to_report, append_kml_trace
from services.platform_geometry_service import correct_platform_geometry
from services.sanzi_document_service import land_material_dir, normalize_land_record
from services.sanzi_rules import USE_STATUS_REQUIREMENT_TYPES, scene_photo_accessory_type

PHOTO_EXTS = {'.png', '.jpeg', '.jpg'}
_INVALID_FILENAME = re.compile('[<>:"/\\\\|?*\\x00-\\x1f]')
BASE_EDGE_TOLERANCE_M = 1.0
MAX_SNAP_DISTANCE_M = 100.0


def _geometry_from_record(record: Dict = None):
    candidates = []
    for source_name in ('summary', 'detail'):
        source = record.get(source_name)
        if isinstance(source, dict):
            candidates.extend([source.get("geom"), source.get("geometry"), source.get("geojson")])
    candidates.extend([record.get("geom"), record.get("geometry")])
    for value in candidates:
        if not value:
            continue
        try:
            data = json.loads(value) if isinstance(value, str) else value
            corrected = correct_platform_geometry(data)
            geom = shape(corrected)
            if not geom.is_valid:
                try:
                    from shapely.validation import make_valid
                    geom = make_valid(geom)
                except Exception:
                    geom = geom.buffer(0)
            if geom.geom_type == "GeometryCollection":
                polygons = [g for g in geom.geoms if g.geom_type in ('Polygon', 'MultiPolygon') and not g.is_empty]
                geom = unary_union(polygons) if polygons else None
            if geom is not None and geom.geom_type in ('Polygon', 'MultiPolygon') and not geom.is_empty:
                return geom
        except Exception:
            continue
    return None


def geometry_from_record(record: Dict = None):
    '''公开的图斑几何读取方法，供材料完整性检测输出 KML 使用。'''
    return _geometry_from_record(record)


def _prepare_records(records: Iterable[Dict] = None) -> Tuple[List[Dict], object]:
    rows = []
    geometries = []
    for record in records:
        data = normalize_land_record(record)
        if not data["landcode"]:
            continue
        geom = _geometry_from_record(record)
        if geom is None:
            continue
        rows.append({"record": record, "data": data})
        geometries.append(geom)
    if not rows:
         raise RuntimeError('同步数据中没有可用于照片匹配的图斑几何，请重新执行“同步平台数据”。')
    gdf = gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4490")
    try:
        metric_crs = gdf.estimate_utm_crs()
    except Exception:
        metric_crs = None
    if not metric_crs:
        centre = gdf.to_crs(4326).geometry.unary_union.centroid
        zone = max(1, min(60, int(float(centre.x) + 180) // 6 + 1))
        metric_crs = f"EPSG:{32600 + zone if float(centre.y) >= 0 else 32700 + zone}"
    metric = gdf.to_crs(metric_crs)
    prepared = []
    for idx, row in metric.iterrows():
        source = rows[idx]
        prepared.append({
            "record": source["record"],
            "data": source["data"],
            "geom": row.geometry,
            "wgs_geom": geometries[idx],
            "base_count": 0,
            "count": 0,
            "sequence": 0,
        })
    return prepared, metric_crs


def _scan_photo_paths(photo_root: str | Path = None, *, exclude_dir: str | Path | None = None) -> List[Path]:
    root = Path(photo_root)
    if not root.is_dir():
        raise RuntimeError("请选择有效的航拍总照片目录。")
    excluded = Path(exclude_dir).resolve() if exclude_dir else None
    result = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in PHOTO_EXTS:
            continue
        if excluded is not None:
            try:
                path.resolve().relative_to(excluded)
                continue
            except ValueError:
                pass
            except Exception:
                pass
        result.append(path)
    return sorted(result, key=lambda p: str(p).lower())


def _read_photo_infos(paths: List[Path] = None, *, log=None, progress=None) -> Tuple[List[ImageInfo], List[Path]]:
    cache = ImageCache()
    valid = []
    no_gps = []
    total = len(paths) or 1
    completed = 0
    pending = []
    for path in paths:
        cached = cache.get(str(path))
        if cached is None:
            pending.append(path)
            continue
        if cached.has_gps and cached.lat is not None and cached.lon is not None:
            valid.append(cached)
        else:
            no_gps.append(path)
        completed += 1
        if progress:
            progress(completed, total, "读取照片GPS")
    workers = min(8, max(1, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(read_img_gps, str(path)): path for path in pending}
        for future in as_completed(futures):
            path = futures[future]
            try:
                info = future.result()
            except Exception:
                info = ImageInfo(path.name, path.name, str(path))
            cache.set(str(path), info)
            if info.has_gps and info.lat is not None and info.lon is not None:
                valid.append(info)
            else:
                no_gps.append(path)
            completed += 1
            if progress:
                progress(completed, total, "读取照片GPS")
    cache.save_cache()
    valid.sort(key=lambda x: (x.capture_time or "", x.filename.lower()))
    if log:
        log(f"读取照片 {len(paths)} 张：带GPS {len(valid)} 张，无GPS {len(no_gps)} 张。")
    return valid, no_gps


def _inside(geom: Point = None, point: Point = None) -> bool:
    try:
        return bool(geom.covers(point))
    except Exception:
        return bool(geom.contains(point) or geom.touches(point))


def _boundary_distance(geom: Point = None, point: Point = None) -> float:
    try:
        return float(geom.boundary.distance(point))
    except Exception:
        return float(geom.distance(point))


def _reset_generated_photo_dirs(lands: List[Dict] = None, project_dir: Path = None) -> Path:
    for land in lands:
        folder = land_material_dir(project_dir, land["record"])
        folder.mkdir(parents=True, exist_ok=True)
        photo_dir = folder / "现场照片_软件整理"
        if photo_dir.exists():
            shutil.rmtree(photo_dir)
        photo_dir.mkdir(parents=True, exist_ok=True)
        land["photo_dir"] = photo_dir
    unmatched = project_dir / "02_材料输出" / "未匹配照片_软件整理"
    if unmatched.exists():
        shutil.rmtree(unmatched)
    unmatched.mkdir(parents=True, exist_ok=True)
    return unmatched


def _copy_photo(info: ImageInfo = None, land: Dict = None) -> Path:
    land["sequence"] += 1
    land["count"] += 1
    code = land["data"]["landcode"]
    status = land["data"]["use_status"]
    label = "对外发包现场照片" if scene_photo_accessory_type(status) == 2 else "现场照片"
    ext = Path(info.filename).suffix.lower() or ".jpg"
    target = Path(land["photo_dir"]) / f"{code}_{label}_{land['sequence']:03d}{ext}"
    shutil.copy2(info.full_path, target)
    return target


def _coord_text(coords) -> str:
    return " ".join(f"{float(x):.10f},{float(y):.10f},0" for x, y, *_ in coords)


def _polygon_kml(geom) -> str:
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        return ""
    blocks = []
    for poly in polys:
        outer = _coord_text(poly.exterior.coords)
        inners = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_coord_text(ring.coords)}</coordinates></LinearRing></innerBoundaryIs>"
            for ring in poly.interiors
        )
        blocks.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>{inners}</Polygon>")
    if len(blocks) == 1:
        return blocks[0]
    return "<MultiGeometry>" + "".join(blocks) + "</MultiGeometry>"


def _export_no_photo_kml(lands: List[Dict] = None, output_path: Path = None) -> None:
    placemarks = []
    for land in lands:
        data = land["data"]
        placemarks.append(
            f"<Placemark><name>{html.escape(data['landcode'])}</name>"
            f"<styleUrl>#noPhoto</styleUrl>"
            f"<description><![CDATA[使用状态：{data['use_status_label']}"
            f"<br>地类现状：{data['land_actuality_label']}"
            f"<br>该图斑未自动匹配到现场照片，请手动归档。]]></description>"
            + _polygon_kml(land["wgs_geom"])
            + "</Placemark>"
        )
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<name>无照片图斑</name>'
        '<Style id="noPhoto"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle>'
        '<PolyStyle><color>660000ff</color></PolyStyle></Style>'
        + "".join(placemarks)
        + "</Document></kml>"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(append_kml_trace(text, "sanzi_missing_photo_kml"), encoding="utf-8")


def export_missing_photo_kml(lands: List[Dict] = None, output_path: str | Path = None) -> Path:
    """输出缺少现场照片图斑 KML；lands 元素需包含 data 与 wgs_geom。"""
    target = Path(output_path)
    _export_no_photo_kml(lands, target)
    return target


def export_missing_material_kml(lands: List[Dict] = None, output_path: str | Path = None) -> Path:
    """输出所有缺少/待确认材料图斑，而不只输出缺少现场照片图斑。"""
    target = Path(output_path)
    placemarks = []
    for land in lands:
        data = land["data"]
        missing = html.escape(str(land.get("missing_summary") or "缺少或待确认材料"))
        placemarks.append(
            f"<Placemark><name>{html.escape(data['landcode'])}</name>"
            f"<styleUrl>#missingMaterial</styleUrl>"
            f"<description><![CDATA[使用状态：{html.escape(data['use_status_label'])}"
            f"<br>地类现状：{html.escape(data['land_actuality_label'])}"
            f"<br>缺少或待确认：{missing}]]></description>"
            + _polygon_kml(land["wgs_geom"])
            + "</Placemark>"
        )
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<name>三资平台缺少材料图斑</name>'
        '<Style id="missingMaterial"><LineStyle><color>ff00a5ff</color><width>3</width></LineStyle>'
        '<PolyStyle><color>6600a5ff</color></PolyStyle></Style>'
        + "".join(placemarks)
        + "</Document></kml>"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(append_kml_trace(text, "sanzi_missing_material_kml"), encoding="utf-8")
    return target


def _query_spatial_index(index_obj, geom, fallback_count: int = None) -> List[int]:
    """兼容不同 GeoPandas/Shapely 版本的空间索引查询。"""
    if index_obj is None:
        return list(range(fallback_count))
    try:
        return [int(x) for x in index_obj.query(geom, predicate="intersects")]
    except TypeError:
        try:
            return [int(x) for x in index_obj.intersection(geom.bounds)]
        except Exception:
            return list(range(fallback_count))
    except Exception:
        try:
            return [int(x) for x in index_obj.intersection(geom.bounds)]
        except Exception:
            return list(range(fallback_count))


def _progress_tick(progress, done: int, total: int, phase: str, *, force: bool = False) -> None:
    if not progress:
        return
    step = max(1, int(total or 1) // 200)
    if force or done <= 1 or done >= total or done % step == 0:
        progress(done, max(1, total), phase)
        return


def organize_project_photos(
    records: Iterable[Dict],
    photo_root: str | Path,
    project_dir: str | Path,
    *,
    match_distance_m: float = 10.0,
    log: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict:
    """按两阶段吸附规则整理现场照片。

    性能优化：
    - 图斑和照片均建立空间索引，不再逐照片遍历全部图斑；
    - 各阶段持续报告进度，避免 GPS 读取到 100% 后长时间无提示；
    - 照片总目录递归读取全部子文件夹，并自动排除项目输出目录。
    """
    distance_limit = max(BASE_EDGE_TOLERANCE_M, min(MAX_SNAP_DISTANCE_M, float(match_distance_m or 10.0)))
    project = Path(project_dir)
    project.mkdir(parents=True, exist_ok=True)

    _progress_tick(progress, 0, 1, "扫描照片目录", force=True)
    paths = _scan_photo_paths(photo_root, exclude_dir=project / "02_材料输出")
    _progress_tick(progress, 1, 1, "扫描照片目录", force=True)

    if not paths:
        raise RuntimeError("所选照片总目录及其子文件夹中没有 JPG/JPEG/PNG 照片。")
    if log:
        log(f"已递归扫描照片总目录：发现 {len(paths)} 张 JPG/JPEG/PNG 照片。")

    photos, no_gps = _read_photo_infos(paths, log=log, progress=progress)
    if not photos:
        raise RuntimeError("所选照片均未读取到GPS坐标，无法按图斑整理。")

    _progress_tick(progress, 0, 1, "建立空间索引", force=True)
    lands, metric_crs = _prepare_records(records)
    unmatched_dir = _reset_generated_photo_dirs(lands, project)
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)

    land_geometries = gpd.GeoSeries([land["geom"] for land in lands], crs=metric_crs)
    try:
        land_sindex = land_geometries.sindex
    except Exception:
        land_sindex = None

    entries = []
    photo_points = []
    for info in photos:
        x, y = transformer.transform(float(info.lon), float(info.lat))
        point = Point(x, y)
        photo_points.append(point)
        entries.append({"info": info, "point": point, "base": [], "supplements": []})

    photo_geometries = gpd.GeoSeries(photo_points, crs=metric_crs)
    try:
        photo_sindex = photo_geometries.sindex
    except Exception:
        photo_sindex = None

    _progress_tick(progress, 1, 1, "建立空间索引", force=True)

    # ---- Stage 1: match photos inside / within 1m of polygons ----
    base_total = len(entries) or 1
    for entry_index, entry in enumerate(entries, 1):
        point = entry["point"]
        query_geom = point.buffer(BASE_EDGE_TOLERANCE_M + 1e-06)
        candidate_indexes = _query_spatial_index(land_sindex, query_geom, len(lands))
        base_matches = []
        for land_index in candidate_indexes:
            if land_index < 0 or land_index >= len(lands):
                continue
            land = lands[land_index]
            inside = _inside(land["geom"], point)
            d = 0.0 if inside else _boundary_distance(land["geom"], point)
            if inside:
                base_matches.append((land, "图斑内部", 0.0))
                continue
            if d <= BASE_EDGE_TOLERANCE_M + 1e-06:
                base_matches.append((land, "图斑外1米内", d))
        for land, _kind, _d in base_matches:
            land["base_count"] += 1
        entry["base"] = base_matches
        _progress_tick(progress, entry_index, base_total, "匹配图斑内部及1米内照片")

    # ---- Stage 2: snap photos to empty polygons (outside, within distance_limit) ----
    empty_lands = [land for land in lands if land["base_count"] == 0]
    supplement_total = len(empty_lands) or 1

    if distance_limit > BASE_EDGE_TOLERANCE_M and empty_lands:
        for land_index, land in enumerate(empty_lands, 1):
            query_geom = land["geom"].buffer(distance_limit + 1e-06)
            candidate_indexes = _query_spatial_index(photo_sindex, query_geom, len(entries))
            candidates = []
            for entry_index in candidate_indexes:
                if entry_index < 0 or entry_index >= len(entries):
                    continue
                entry = entries[entry_index]
                point = entry["point"]
                if _inside(land["geom"], point):
                    continue
                d = _boundary_distance(land["geom"], point)
                if BASE_EDGE_TOLERANCE_M < d <= distance_limit + 1e-06:
                    candidates.append((d, entry["info"].filename.lower(), entry))
            candidates.sort(key=lambda x: (x[0], x[1]))
            for d, _name, entry in candidates:
                entry["supplements"].append((land, d))
            _progress_tick(progress, land_index, supplement_total, "为空图斑计算外部吸附")
    else:
        _progress_tick(progress, 1, 1, "为空图斑计算外部吸附", force=True)

    # ---- Stage 3: copy / move photos ----
    unmatched_points = []
    match_rows = []
    copy_total = 0
    total = len(entries) or 1

    for index, entry in enumerate(entries, 1):
        info = entry["info"]
        destinations = []
        seen = set()
        for land, kind, d in entry["base"]:
            destinations.append((land, kind, d))
            seen.add(id(land))
        for land, d in entry["supplements"]:
            if id(land) not in seen:
                destinations.append((land, "空图斑外部吸附", d))
                seen.add(id(land))

        if not destinations:
            target = unmatched_dir / info.filename
            if target.exists():
                target = unmatched_dir / f"{target.stem}_{index:04d}{target.suffix}"
            shutil.copy2(info.full_path, target)
            unmatched_points.append({"name": info.filename, "lon": info.lon, "lat": info.lat})
            match_rows.append({
                "源照片": info.filename,
                "图斑编号": "",
                "匹配方式": "未匹配",
                "边缘距离（米）": "",
                "输出文件": str(target),
            })
        else:
            for land, kind, d in destinations:
                target = _copy_photo(info, land)
                copy_total += 1
                match_rows.append({
                    "源照片": info.filename,
                    "图斑编号": land["data"]["landcode"],
                    "匹配方式": kind,
                    "边缘距离（米）": f"{d:.2f}",
                    "输出文件": str(target),
                })
        _progress_tick(progress, index, total, "整理现场照片")

    # ---- Stage 4: generate reports ----
    _progress_tick(progress, 0, 4, "生成整理报告", force=True)
    report_dir = project / "05_操作日志"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_csv = report_dir / "现场照片整理结果.csv"

    with report_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["源照片", "图斑编号", "匹配方式", "边缘距离（米）", "输出文件"])
        writer.writeheader()
        writer.writerows(match_rows)

    _progress_tick(progress, 1, 4, "生成整理报告", force=True)

    (report_dir / "无GPS照片.txt").write_text(
        "\n".join(str(p) for p in no_gps), encoding="utf-8"
    )

    if unmatched_points:
        export_points_kml(unmatched_points, str(report_dir / "未匹配照片.kml"))

    _progress_tick(progress, 2, 4, "生成整理报告", force=True)

    counts = {land["data"]["landcode"]: land["count"] for land in lands}
    no_photo_lands = [land for land in lands if land["count"] <= 0]
    no_photo_kml = project / "02_材料输出" / "无照片图斑.kml"
    _export_no_photo_kml(no_photo_lands, no_photo_kml)

    _progress_tick(progress, 3, 4, "生成整理报告", force=True)

    summary = {
        "source_total": len(paths),
        "gps_total": len(photos),
        "no_gps_total": len(no_gps),
        "copied_total": copy_total,
        "unmatched_total": len(unmatched_points),
        "land_total": len(lands),
        "no_photo_land_total": len(no_photo_lands),
        "no_photo_landcodes": [x["data"]["landcode"] for x in no_photo_lands],
        "counts": counts,
        "report_csv": str(report_csv),
        "no_photo_kml": str(no_photo_kml),
        "output_root": str(project / "02_材料输出"),
        "base_edge_tolerance_m": BASE_EDGE_TOLERANCE_M,
        "snap_distance_m": distance_limit,
        "spatial_index_enabled": bool(land_sindex is not None and photo_sindex is not None),
    }
    summary = add_trace_to_report(summary, "sanzi_photo_summary")

    (report_dir / "现场照片整理汇总.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _progress_tick(progress, 4, 4, "生成整理报告", force=True)

    if log:
        index_text = "已启用空间索引" if summary["spatial_index_enabled"] else "当前环境未启用空间索引，已使用兼容模式"
        log(f"照片匹配算法：{index_text}。")
        log(
            f"照片整理完成：源照片{len(paths)}张，带GPS{len(photos)}"
            f"张，复制{copy_total}份，未匹配{len(unmatched_points)}"
            f"张，无照片图斑{len(no_photo_lands)}个。"
        )
        log(f"无照片图斑KML：{no_photo_kml}")

    return summary
