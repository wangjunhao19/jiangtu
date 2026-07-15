from __future__ import annotations

import html
import re
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from xml.etree import ElementTree as ET
from pyproj import Transformer

KML_NS = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', KML_NS)


@dataclass
class EmgFeature:
    emid: int
    attributes: Dict[str, object]
    rings: List[List[Tuple[float, float]]]


def _read_page_map(blob: bytes) -> tuple[list[int], list[int]]:
    if len(blob) < 12288:
        raise ValueError('EMG文件长度不足，无法读取页目录。')
    root = blob[8192:12288]

    try:
        index_pos = root.index(b'Index')
        data_pos = root.index(b'Data')
    except ValueError as exc:
        raise ValueError('不是受支持的EMG图形文件：缺少Index/Data目录。') from exc

    index_count = struct.unpack_from('<I', root, index_pos + 9)[0]
    data_count = struct.unpack_from('<I', root, data_pos + 8)[0]
    if not (0 <= index_count < 100000 and 0 <= data_count < 1000000):
        raise ValueError('EMG页目录数量异常。')
    index_ids = list(struct.unpack_from('<' + 'I' * index_count, root, index_pos + 13))
    data_ids = list(struct.unpack_from('<' + 'I' * data_count, root, data_pos + 12))
    return (index_ids, data_ids)


def _join_pages(blob: bytes, page_ids: Sequence[int]) -> bytes:
    chunks = []
    for page_id in page_ids:
        start = (int(page_id) + 2) * 4096
        end = start + 4096
        if start < 0 or end > len(blob):
            raise ValueError(f'EMG页号越界：{page_id}')
        chunks.append(blob[start:end])
    return b''.join(chunks)


def _source_epsg(connection: sqlite3.Connection, sample_x: float | None = None) -> int:
    row = connection.execute('SELECT EmData FROM EmCoordSys LIMIT 1').fetchone()
    raw = bytes(row[0] or b'') if row else b''
    text = raw.decode('latin1', errors='ignore')
    match = re.search(r'CGCS2000_3_Degree_GK_Zone_(\d+)', text, flags=re.I)
    if match:
        zone = int(match.group(1))
        epsg = 4488 + zone
        try:
            Transformer.from_crs(epsg, 4326, always_xy=True)
            return epsg
        except Exception:
            pass
    if sample_x and abs(sample_x) >= 1000000:
        zone = int(abs(sample_x) // 1000000)
        if 1 <= zone <= 45:
            return 4488 + zone
    raise ValueError('无法识别EMD坐标系；当前转换器支持CGCS2000三度带带号坐标。')


def _read_attributes(connection: sqlite3.Connection) -> tuple[list[str], dict[int, Dict[str, object]]]:
    columns = [row[1] for row in connection.execute('PRAGMA table_info(EmDataset)')]
    if not columns or 'EmID' not in columns:
        raise ValueError('EMD属性库缺少EmDataset/EmID。')
    rows = {}
    for record in connection.execute('SELECT * FROM EmDataset'):
        item = dict(zip(columns, record))
        emid = int(item.get('EmID') or 0)
        rows[emid] = item
    return (columns, rows)


def read_emd_emg(emd_path: str | Path, emg_path: str | Path) -> tuple[list[EmgFeature], int]:
    emd = Path(emd_path)
    emg = Path(emg_path)
    if not emd.is_file():
        raise FileNotFoundError(f'缺少同名EMD属性文件：{emd}')
    if not emg.is_file():
        raise FileNotFoundError(f'EMG图形文件不存在：{emg}')
    if emd.stem.lower() != emg.stem.lower():
        raise ValueError('EMD与EMG主文件名必须相同。')

    blob = emg.read_bytes()
    index_ids, data_ids = _read_page_map(blob)
    index_stream = _join_pages(blob, index_ids)
    data_stream = _join_pages(blob, data_ids)

    with sqlite3.connect(str(emd)) as connection:
        meta = connection.execute('SELECT EmGeometryType, EmFeatureCount FROM EmMeta LIMIT 1').fetchone()
        if not meta:
            raise ValueError('EMD中缺少EmMeta。')
        geometry_type = int(meta[0])
        feature_count = int(meta[1])
        index_count = struct.unpack_from('<I', index_stream, 0)[0]
        if index_count != feature_count:
            raise ValueError(f'EMD/EMG数量不一致：属性{feature_count}，图形索引{index_count}。')
        starts = list(struct.unpack_from('<' + 'I' * index_count, index_stream, 4))
        _, attributes = _read_attributes(connection)

        dimension = 3 if geometry_type >= 30 else 2
        raw_features = []
        first_x = None
        for emid, start in enumerate(starts):
            if start + 8 > len(data_stream):
                raise ValueError(f'EMG第{emid + 1}个图形偏移越界。')
            payload_len = struct.unpack_from('<I', data_stream, start)[0]
            end = start + 4 + payload_len
            if end > len(data_stream):
                raise ValueError(f'EMG第{emid + 1}个图形数据不完整。')
            if emid + 1 < len(starts) and end != starts[emid + 1]:
                raise ValueError(f'EMG第{emid + 1}个图形索引不连续。')
            record = data_stream[start:end]
            part_count = struct.unpack_from('<I', record, 4)[0]
            if not (0 <= part_count < 100000):
                raise ValueError(f'EMG第{emid + 1}个图形分部数量异常。')
            point_counts = list(struct.unpack_from('<' + 'I' * part_count, record, 8))
            pos = 8 + 4 * part_count
            rings = []
            for point_count in point_counts:
                ring = []
                for _ in range(point_count):
                    values = struct.unpack_from('<' + 'd' * dimension, record, pos)
                    pos += 8 * dimension
                    x = float(values[0])
                    y = float(values[1])
                    if first_x is None:
                        first_x = x
                    ring.append((x, y))
                if len(ring) >= 3:
                    if ring[0] != ring[-1]:
                        ring.append(ring[0])
                    rings.append(ring)
            if pos != len(record):
                raise ValueError(f'EMG第{emid + 1}个图形结构无法完整解析。')
            raw_features.append((emid, rings))

        epsg = _source_epsg(connection, first_x)
        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)

        features = []
        for emid, rings in raw_features:
            transformed = []
            for ring in rings:
                coords = [transformer.transform(x, y) for x, y in ring]
                transformed.append([(float(lon), float(lat)) for lon, lat in coords])
            features.append(EmgFeature(
                emid,
                attributes.get(emid, {'EmID': emid}),
                transformed
            ))

        return (features, epsg)


def _ring_area(ring: Sequence[Tuple[float, float]]) -> float:
    return 0.5 * sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        for i in range(len(ring) - 1)
    )


def _point_in_ring(point: Tuple[float, float], ring: Sequence[Tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def _group_rings(rings: Sequence[Sequence[Tuple[float, float]]]) -> list[tuple[list[Tuple[float, float]], list[list[Tuple[float, float]]]]]:
    '''按包含层级把外环与内环分组；支持多部件和洞。'''
    valid = [list(r) for r in rings if len(r) >= 4 and abs(_ring_area(r)) > 1e-16]
    order = sorted(range(len(valid)), key=lambda i: abs(_ring_area(valid[i])), reverse=True)
    parent = {}
    depth = {}
    for pos, idx in enumerate(order):
        p = None
        p_area = float('inf')
        test_point = valid[idx][0]
        for larger in order[:pos]:
            area = abs(_ring_area(valid[larger]))
            if area < p_area and _point_in_ring(test_point, valid[larger]):
                p = larger
                p_area = area
        parent[idx] = p
        depth[idx] = 0 if p is None else depth[p] + 1
    groups = {}
    for idx in order:
        if depth[idx] % 2 == 0:
            groups[idx] = (valid[idx], [])
    for idx in order:
        if depth[idx] % 2 == 1:
            ancestor = parent[idx]
            while ancestor is not None and depth[ancestor] % 2 == 1:
                ancestor = parent[ancestor]
            if ancestor is not None and ancestor in groups:
                groups[ancestor][1].append(valid[idx])
    return list(groups.values())


def _coords_text(ring: Sequence[Tuple[float, float]]) -> str:
    return ' '.join(
        f'{lon:.10f},{lat:.10f},0'
        for lon, lat in ring
    )


PLOT_NUMBER_ALIASES = ('图斑号', '新图斑号', '号', '图斑号_1', '号_1', '地块编号', '地块编码', 'landcode', 'land_code', '编号', '自治区K编')


def _normalize_plot_number(value: object) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if not text or text.lower() in {'none', 'nan', 'null'}:
        return ''
    if re.fullmatch(r'[+-]?\d+\.0+', text):
        return text.split('.', 1)[0]
    return text


def _plot_number(attrs: Dict[str, object], emid: int) -> str:
    for key in PLOT_NUMBER_ALIASES:
        value = _normalize_plot_number(attrs.get(key))
        if value:
            return value
    return str(emid + 1)


def _ordered_export_attributes(attrs: Dict[str, object], emid: int) -> Dict[str, object]:
    '''固定把图斑号放在第一字段，landcode放在第二字段。'''
    plot_number = _plot_number(attrs, emid)
    ordered = {'图斑号': plot_number, 'landcode': plot_number}
    emid_value = attrs.get('EmID', emid)
    for key, value in attrs.items():
        key_text = str(key)
        if key_text in {'EmID', 'landcode', '图斑号'}:
            continue
        ordered[key_text] = value
    ordered['EmID'] = emid_value
    return ordered


def _feature_name(attrs: Dict[str, object], emid: int) -> str:
    return _plot_number(attrs, emid)


def export_emg_pair_to_kml(emd_path: str | Path, emg_path: str | Path, output_path: str | Path) -> dict:
    features, epsg = read_emd_emg(emd_path, emg_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    kml = ET.Element(f'{{{KML_NS}}}kml')
    document = ET.SubElement(kml, f'{{{KML_NS}}}Document')
    Path(emg_path).stem  # used below
    name_elem = ET.SubElement(document, f'{{{KML_NS}}}name')
    name_elem.text = Path(emg_path).stem

    style = ET.SubElement(document, f'{{{KML_NS}}}Style', id='emgPlot')
    line = ET.SubElement(style, f'{{{KML_NS}}}LineStyle')
    ET.SubElement(line, f'{{{KML_NS}}}color').text = 'ff00a5ff'
    ET.SubElement(line, f'{{{KML_NS}}}width').text = '2'
    poly = ET.SubElement(style, f'{{{KML_NS}}}PolyStyle')
    ET.SubElement(poly, f'{{{KML_NS}}}color').text = '5500a5ff'

    exported = 0
    for feature in features:
        grouped = _group_rings(feature.rings)
        if not grouped:
            continue
        placemark = ET.SubElement(document, f'{{{KML_NS}}}Placemark')
        name_el = ET.SubElement(placemark, f'{{{KML_NS}}}name')
        name_el.text = _feature_name(feature.attributes, feature.emid)
        ET.SubElement(placemark, f'{{{KML_NS}}}styleUrl').text = '#emgPlot'

        table_rows = []
        extended = ET.SubElement(placemark, f'{{{KML_NS}}}ExtendedData')
        export_attributes = _ordered_export_attributes(feature.attributes, feature.emid)
        for key, value in export_attributes.items():
            text = '' if value is None else str(value)
            data = ET.SubElement(extended, f'{{{KML_NS}}}Data', name=str(key))
            ET.SubElement(data, f'{{{KML_NS}}}value').text = text
            table_rows.append(f'<tr><th>{html.escape(str(key))}</th><td>{html.escape(text)}</td></tr>')
        desc = ET.SubElement(placemark, f'{{{KML_NS}}}description')
        desc.text = '<table>' + ''.join(table_rows) + '</table>'

        geometry_parent = placemark
        if len(grouped) > 1:
            geometry_parent = ET.SubElement(placemark, f'{{{KML_NS}}}MultiGeometry')
        for outer, holes in grouped:
            polygon = ET.SubElement(geometry_parent, f'{{{KML_NS}}}Polygon')
            ET.SubElement(polygon, f'{{{KML_NS}}}tessellate').text = '1'
            outer_boundary = ET.SubElement(polygon, f'{{{KML_NS}}}outerBoundaryIs')
            outer_ring = ET.SubElement(outer_boundary, f'{{{KML_NS}}}LinearRing')
            ET.SubElement(outer_ring, f'{{{KML_NS}}}coordinates').text = _coords_text(outer)
            for hole in holes:
                inner_boundary = ET.SubElement(polygon, f'{{{KML_NS}}}innerBoundaryIs')
                inner_ring = ET.SubElement(inner_boundary, f'{{{KML_NS}}}LinearRing')
                ET.SubElement(inner_ring, f'{{{KML_NS}}}coordinates').text = _coords_text(hole)
        exported += 1

    tree = ET.ElementTree(kml)
    ET.indent(tree, space='  ')
    tree.write(output, encoding='utf-8', xml_declaration=True)

    return {
        'emd': str(Path(emd_path)),
        'emg': str(Path(emg_path)),
        'output': str(output),
        'source_epsg': epsg,
        'feature_total': len(features),
        'exported_total': exported
    }


def batch_convert_emg_to_kml(
    emg_paths: Iterable[str | Path],
    output_dir: str | Path,
    *,
    progress=None,
    log=None
) -> dict:
    paths = [Path(p) for p in emg_paths]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    total = len(paths)
    for index, emg in enumerate(paths, 1):
        emd = emg.with_suffix('.emd')
        target = out / f'{emg.stem}.kml'
        try:
            item = export_emg_pair_to_kml(emd, emg, target)
            results.append(item)
            if log:
                log(f'转换成功：{emg.name} → {target.name}，图斑{item["exported_total"]}个，源坐标EPSG:{item["source_epsg"]}')
        except Exception as exc:
            failures.append({'emg': str(emg), 'emd': str(emd), 'error': str(exc)})
            if log:
                log(f'转换失败：{emg.name} - {exc}')
        if progress:
            progress(index, total)
    return {'success': results, 'failed': failures, 'output_dir': str(out)}
