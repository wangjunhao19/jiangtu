# Source Generated with Decompyle++
# File: local_dem_service.pyc (Python 3.11)

from __future__ import annotations
import json
import math
import os
import re
import shutil
import struct
import threading
import time
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    import numpy as np
except Exception:
    np = None

try:
    import rasterio
    from rasterio.warp import transform_bounds
except Exception:
    rasterio = None
    transform_bounds = None

from pyproj import CRS, Transformer

_HGT_RE = re.compile(r'^([NS])(\d{2})([EW])(\d{3})\.hgt$', re.I)
_SUPPORTED = {'.asc', '.tif', '.tiff', '.hgt'}
_ZIP_SIDECARS = {'.aux', '.ovr', '.tfw', '.xml', '.prj'}


def _data_root() -> Path:
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or str(Path.home())
    path = Path(base) / 'JiangTu' / 'elevation_data'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return _data_root() / 'dem_sources.json'


@dataclass
class DemSource:
    path: Path
    kind: str
    bounds: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] | None = None


class LocalDemCatalog:
    """Local DEM catalogue supporting HGT, ESRI ASCII Grid and GeoTIFF.

    Source folders are persisted in the user's AppData directory. Files are never modified.
    HGT and ASC work with the standard Python stack; GeoTIFF uses rasterio when installed.
    """

    def __init__(self) -> None:
        self.root = _data_root()
        self.lock = threading.RLock()
        self.source_paths: list[str] = []
        self.sources: list[DemSource] = []
        self.hgt_index: dict = {}
        self._asc_cache: OrderedDict = OrderedDict()
        self._raster_cache: OrderedDict = OrderedDict()
        self._load_config()
        self.rescan()

    def _load_config(self) -> None:
        try:
            data = json.loads(_config_path().read_text(encoding='utf-8'))
            self.source_paths = [str(Path(x).expanduser()) for x in data.get('sources', []) if str(x).strip()]
        except Exception:
            self.source_paths = []

    def _save_config(self) -> None:
        payload = {
            'version': 1,
            'sources': self.source_paths,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        _config_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def _iter_dem_files(path: Path) -> Iterable[Path]:
        if path.is_file() and path.suffix.lower() in _SUPPORTED:
            yield path
        elif path.is_dir():
            for item in path.rglob('*'):
                if item.is_file() and item.suffix.lower() in _SUPPORTED:
                    yield item

    @staticmethod
    def _hgt_tile(path: Path) -> tuple[int, int] | None:
        m = _HGT_RE.match(path.name)
        if not m:
            return None
        lat = int(m.group(2)) * (1 if m.group(1).upper() == 'N' else -1)
        lon = int(m.group(4)) * (1 if m.group(3).upper() == 'E' else -1)
        return (lat, lon)

    def rescan(self) -> dict[str, Any]:
        sources: list[DemSource] = []
        hgt: dict = {}
        seen: set = set()
        for raw in self.source_paths:
            path = Path(raw)
            if not path.exists():
                continue
            for file in self._iter_dem_files(path):
                key = str(file.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                suffix = file.suffix.lower()
                source = DemSource(file.resolve(), suffix.lstrip('.'))
                if suffix == '.hgt':
                    tile = self._hgt_tile(file)
                    if tile is None:
                        continue
                    source.bounds = (tile[1], tile[0], tile[1] + 1, tile[0] + 1)
                    hgt[tile] = source
                sources.append(source)
        with self.lock:
            self.sources = sources
            self.hgt_index = hgt
        return self.status()

    def add_sources(self, paths: Iterable[str]) -> dict[str, Any]:
        """添加DEM来源；最近添加的项目数据优先于较早加入的省级/全国数据。"""
        changed = False
        resolved_paths: list[str] = []
        for raw in paths:
            path = Path(str(raw or '')).expanduser()
            if not path.exists():
                continue
            resolved = str(path.resolve())
            if resolved not in resolved_paths:
                resolved_paths.append(resolved)
        for resolved in reversed(resolved_paths):
            if resolved in self.source_paths:
                self.source_paths.remove(resolved)
            self.source_paths.insert(0, resolved)
            changed = True
        if changed:
            self._save_config()
        return self.rescan()

    def import_zip(self, zip_path: str) -> dict[str, Any]:
        src = Path(zip_path)
        if not src.is_file():
            raise FileNotFoundError('离线高程包不存在')
        target = self.root / f'import_{time.strftime("%Y%m%d_%H%M%S")}'
        target.mkdir(parents=True, exist_ok=True)
        extracted = 0
        target_resolved = target.resolve()
        with zipfile.ZipFile(src, 'r') as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                member_path = PurePosixPath(member.filename.replace('\\', '/'))
                safe_parts = [p for p in member_path.parts if p not in ('..', '.', '')]
                suffix = member_path.suffix.lower()
                if suffix not in _SUPPORTED and suffix not in _ZIP_SIDECARS:
                    continue
                dest = target.joinpath(*safe_parts).resolve()
                if dest != target_resolved and target_resolved not in dest.parents:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, 'r') as inp:
                    with open(dest, 'wb') as out:
                        shutil.copyfileobj(inp, out)
                extracted += 1
        if extracted <= 0:
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError('离线高程包中未找到支持的DEM文件')
        return self.add_sources([str(target)])

    def clear_sources(self) -> dict[str, Any]:
        with self.lock:
            self.source_paths = []
            self.sources = []
            self.hgt_index = {}
            self._asc_cache.clear()
            for ds in self._raster_cache.values():
                try:
                    ds.close()
                except Exception:
                    pass
            self._raster_cache.clear()
        self._save_config()
        return self.status()

    def status(self) -> dict[str, Any]:
        counts = {'hgt': 0, 'asc': 0, 'tif': 0, 'tiff': 0}
        with self.lock:
            for source in self.sources:
                counts[source.kind] = counts.get(source.kind, 0) + 1
            files = len(self.sources)
            paths = list(self.source_paths)
        return {
            'ok': True,
            'source_paths': paths,
            'file_count': files,
            'counts': counts,
            'geotiff_available': rasterio is not None,
            'message': f'已索引 {files} 个本地DEM文件',
        }

    def _lookup_hgt_source(self, source: DemSource, lat: float, lon: float) -> dict[str, Any] | None:
        tile = self._hgt_tile(source.path)
        if tile is None:
            return None
        tile_lat, tile_lon = tile
        if not (tile_lon <= lon <= tile_lon + 1 and tile_lat <= lat <= tile_lat + 1):
            return None
        size_bytes = source.path.stat().st_size
        cells = size_bytes // 2
        side = int(round(math.sqrt(cells)))
        if side not in (1201, 3601) or side * side != cells:
            return None
        rowf = (tile_lat + 1 - lat) * (side - 1)
        colf = (lon - tile_lon) * (side - 1)
        row = max(0, min(side - 1, int(round(rowf))))
        col = max(0, min(side - 1, int(round(colf))))
        offset = (row * side + col) * 2
        with open(source.path, 'rb') as f:
            f.seek(offset)
            raw = f.read(2)
        if len(raw) != 2:
            return None
        value = struct.unpack('>h', raw)[0]
        if value <= -32768:
            return None
        return {'ok': True, 'elevation': float(value), 'source': f'本地HGT：{source.path.name}'}

    def _load_asc(self, source: DemSource) -> dict[str, Any] | None:
        key = str(source.path)
        cached = self._asc_cache.get(key)
        if cached is not None:
            self._asc_cache.move_to_end(key)
            return cached
        if np is None:
            return None
        header: dict = {}
        skip = 0
        with open(source.path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in range(12):
                pos = f.tell()
                line = f.readline()
                if not line:
                    break
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].lower() in frozenset({
                    'ncols', 'nrows', 'cellsize', 'xllcenter', 'xllcorner',
                    'yllcenter', 'yllcorner', 'nodata_value',
                }):
                    try:
                        header[parts[0].lower()] = float(parts[1])
                        skip += 1
                    except Exception:
                        pass
                else:
                    f.seek(pos)
                    break
        ncols = int(header.get('ncols', 0))
        nrows = int(header.get('nrows', 0))
        cell = float(header.get('cellsize', 0))
        if ncols <= 0 or nrows <= 0 or cell <= 0:
            return None
        data = np.loadtxt(source.path, dtype=float, skiprows=skip)
        if data.shape != (nrows, ncols):
            data = np.asarray(data).reshape(nrows, ncols)
        x0 = header.get('xllcorner', header.get('xllcenter', 0)) - cell / 2
        y0 = header.get('yllcorner', header.get('yllcenter', 0)) - cell / 2
        native_bounds = (x0, y0, x0 + ncols * cell, y0 + nrows * cell)
        crs = None
        prj_path = source.path.with_suffix('.prj')
        if not prj_path.exists():
            for sibling in source.path.parent.glob(source.path.stem + '.*'):
                if sibling.suffix.lower() == '.prj':
                    prj_path = sibling
                    break
        if prj_path.exists():
            try:
                crs = CRS.from_user_input(prj_path.read_text(encoding='utf-8', errors='ignore'))
            except Exception:
                crs = None
        if crs is None:
            if (-180.5 <= native_bounds[0] <= 180.5 and -180.5 <= native_bounds[2] <= 180.5
                    and -90.5 <= native_bounds[1] <= 90.5 and -90.5 <= native_bounds[3] <= 90.5):
                crs = CRS.from_epsg(4326)
        item = {
            'header': header,
            'data': data,
            'x0': x0,
            'y0': y0,
            'cell': cell,
            'ncols': ncols,
            'nrows': nrows,
            'native_bounds': native_bounds,
            'crs': crs,
        }
        self._asc_cache[key] = item
        self._asc_cache.move_to_end(key)
        while len(self._asc_cache) > 3:
            self._asc_cache.popitem(last=False)
        if crs is not None:
            try:
                if crs.to_epsg() == 4326 or crs.is_geographic:
                    source.bounds = native_bounds
                elif transform_bounds:
                    source.bounds = tuple(transform_bounds(crs, 'EPSG:4326', *native_bounds, densify_pts=21))
                else:
                    transformer = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
                    corners = [
                        transformer.transform(native_bounds[0], native_bounds[1]),
                        transformer.transform(native_bounds[2], native_bounds[3]),
                    ]
                    source.bounds = (
                        min(c[0] for c in corners),
                        min(c[1] for c in corners),
                        max(c[0] for c in corners),
                        max(c[1] for c in corners),
                    )
            except Exception:
                source.bounds = None
        return item

    def _lookup_asc(self, source: DemSource, lat: float, lon: float) -> dict[str, Any] | None:
        item = self._load_asc(source)
        if not item:
            return None
        x0 = item['x0']
        y0 = item['y0']
        cell = item['cell']
        ncols = item['ncols']
        nrows = item['nrows']
        crs = item.get('crs')
        if crs is None:
            return None
        x, y = lon, lat
        try:
            if crs.to_epsg() != 4326 and not crs.is_geographic:
                x, y = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(lon, lat)
        except Exception:
            return None
        if not (x0 <= x <= x0 + ncols * cell and y0 <= y <= y0 + nrows * cell):
            return None
        col = max(0, min(ncols - 1, int((x - x0) / cell)))
        row_from_bottom = int((y - y0) / cell)
        row = max(0, min(nrows - 1, nrows - 1 - row_from_bottom))
        value = float(item['data'][row, col])
        nodata = item['header'].get('nodata_value')
        if not math.isfinite(value) or (nodata is not None and abs(value - nodata) < 1e-09):
            return None
        return {'ok': True, 'elevation': value, 'source': f'本地ASC：{source.path.name}'}

    def _open_raster(self, source: DemSource):
        if rasterio is None:
            return None
        key = str(source.path)
        ds = self._raster_cache.get(key)
        if ds is not None:
            self._raster_cache.move_to_end(key)
            return ds
        ds = rasterio.open(source.path)
        self._raster_cache[key] = ds
        self._raster_cache.move_to_end(key)
        while len(self._raster_cache) > 4:
            _, old = self._raster_cache.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
        try:
            if ds.crs and transform_bounds:
                source.bounds = tuple(transform_bounds(ds.crs, 'EPSG:4326', *ds.bounds, densify_pts=21))
        except Exception:
            pass
        return ds

    def _lookup_tiff(self, source: DemSource, lat: float, lon: float) -> dict[str, Any] | None:
        ds = self._open_raster(source)
        if ds is None:
            return None
        if source.bounds:
            left, bottom, right, top = source.bounds
            if not (left <= lon <= right and bottom <= lat <= top):
                return None
        x, y = lon, lat
        if ds.crs and str(ds.crs).upper() not in frozenset({'OGC:CRS84', 'EPSG:4326'}):
            transformer = Transformer.from_crs('EPSG:4326', ds.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
        try:
            value = float(next(ds.sample([(x, y)]))[0])
        except Exception:
            return None
        nodata = ds.nodata
        if not math.isfinite(value) or (nodata is not None and abs(value - float(nodata)) < 1e-09):
            return None
        return {'ok': True, 'elevation': value, 'source': f'本地GeoTIFF：{source.path.name}'}

    def lookup(self, lat: float, lon: float) -> dict[str, Any] | None:
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            return None
        with self.lock:
            sources = list(self.sources)
        for source in sources:
            try:
                if source.bounds:
                    left, bottom, right, top = source.bounds
                    if not (left <= lon <= right and bottom <= lat <= top):
                        continue
                if source.kind == 'hgt':
                    result = self._lookup_hgt_source(source, lat, lon)
                elif source.kind == 'asc':
                    result = self._lookup_asc(source, lat, lon)
                elif source.kind in {'tif', 'tiff'}:
                    result = self._lookup_tiff(source, lat, lon)
                else:
                    result = None
                if result:
                    return result
            except Exception:
                continue
        return None


_CATALOG: LocalDemCatalog | None = None
_CATALOG_LOCK = threading.Lock()


def get_local_dem_catalog() -> LocalDemCatalog:
    global _CATALOG
    with _CATALOG_LOCK:
        if _CATALOG is None:
            _CATALOG = LocalDemCatalog()
    return _CATALOG
