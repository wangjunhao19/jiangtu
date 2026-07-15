# Source Generated with Decompyle++
# File: kml_service.pyc (Python 3.11)

import os
import xml.sax.saxutils as sax
from xml.sax.saxutils import escape as xml_escape
from services.output_trace_service import append_kml_trace


def _iter_polygons(geom):
    """把 Polygon / MultiPolygon / GeometryCollection 统一拆成可写入 KML 的面。

    HAR 接口里有些图斑经过 make_valid 后会变成 GeometryCollection，
    旧版直接取 exterior 会报：'GeometryCollection' object has no attribute 'exterior'。
    这里递归提取其中的 Polygon，自动忽略 Point/LineString 等非面要素。
    """
    if geom is None or getattr(geom, 'is_empty', True):
        return None
    gtype = getattr(geom, 'geom_type', '')
    if gtype == 'Polygon':
        yield geom
        return None
    if gtype == 'MultiPolygon':
        for g in geom.geoms:
            if not getattr(g, 'is_empty', True):
                yield g
        return None
    if gtype == 'GeometryCollection':
        for g in geom.geoms:
            yield from _iter_polygons(g)
    return None


def export_points_kml(points: list, output_path: str):
    lines = []
    for pt in points:
        # 同时支持 dict 和 ImageInfo dataclass 对象
        if isinstance(pt, dict):
            name = pt.get('name', pt.get('filename', ''))
            lon = pt.get('lon')
            lat = pt.get('lat')
        else:
            name = getattr(pt, 'filename', getattr(pt, 'name', ''))
            lon = getattr(pt, 'lon', None)
            lat = getattr(pt, 'lat', None)
        if lon is None or lat is None:
            continue
        lines.append(f'<Placemark><name>{xml_escape(str(name))}</name><Point><coordinates>{lon},{lat}</coordinates></Point></Placemark>')
    kml = f'<?xml version="1.0" encoding="utf-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{"".join(lines)}</Document></kml>'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(append_kml_trace(kml, 'points_kml'))
    return None


def write_land_kml(gdf, out_path: str):
    fname = os.path.basename(out_path)
    if '未完成' in fname:
        line_color, fill_color = ('ff00ffff', '3800ffff')
    elif '进行中' in fname:
        line_color, fill_color = ('ff0099ff', '800099ff')
    elif '已完成' in fname:
        line_color, fill_color = ('ff22bb00', '8022bb00')
    else:
        line_color, fill_color = ('ffff9900', '80ff9900')
    style_xml = (
        f'\n<Style id="land_style">\n'
        f'  <LineStyle><color>{line_color}</color><width>2</width></LineStyle>\n'
        f'  <PolyStyle><color>{fill_color}</color></PolyStyle>\n'
        f'</Style>'
    )
    parts = ['<?xml version="1.0" encoding="utf-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>', style_xml]
    for _, row in gdf.iterrows():
        geom = row.geometry
        name = xml_escape(str(row.get('name', '')))
        desc = xml_escape(str(row.get('description', '')))
        extended = []
        reserved = set()
        reserved.update(frozenset({'desc', 'name', 'geometry', 'description'}))
        preferred = ['landcode', 'land_area', 'landactuality', 'usestatus', 'land_user', 'idcard', 'landstatus']
        fields = preferred + [str(field) for field in row.index if str(field) not in preferred]
        seen = set()
        for field in fields:
            if field in seen or field in reserved or field not in row:
                continue
            seen.add(field)
            value = row.get(field)
            if value is None or isinstance(value, (dict, list, tuple, set)):
                continue
            text = str(value).strip()
            if not text or text.lower() in frozenset({'nan', 'nat', 'none', 'null'}):
                continue
            safe_field = xml_escape(str(field), {'"': '&quot;'})
            extended.append(f'<Data name="{safe_field}"><value>{xml_escape(text)}</value></Data>')
        extended_xml = f'<ExtendedData>{"".join(extended)}</ExtendedData>' if extended else ''
        poly_xml = []
        for poly in _iter_polygons(geom):
            if poly.is_empty or poly.exterior is None:
                continue
            coords = ' '.join(f'{p[0]},{p[1]}' for p in poly.exterior.coords)
            inner_xml = []
            for ring in getattr(poly, 'interiors', []):
                inner_coords = ' '.join(f'{p[0]},{p[1]}' for p in ring.coords)
                inner_xml.append(f'<innerBoundaryIs><LinearRing><coordinates>{inner_coords}</coordinates></LinearRing></innerBoundaryIs>')
            poly_xml.append(
                f'\n    <Polygon>\n'
                f'      <outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs>'
                f'{"".join(inner_xml)}'
                f'\n    </Polygon>'
            )
        if not poly_xml:
            continue
        parts.append(
            f'\n<Placemark>\n<styleUrl>#land_style</styleUrl>\n<name>{name}</name>\n<description>{desc}</description>\n'
            f'{extended_xml}\n'
            f'{"".join(poly_xml)}\n</Placemark>'
        )
    parts.append('</Document></kml>')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(append_kml_trace(''.join(parts), 'land_kml'))
    return None
