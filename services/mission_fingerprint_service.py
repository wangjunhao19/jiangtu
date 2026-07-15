# Source Generated with Decompyle++
# File: mission_fingerprint_service.pyc (Python 3.11)

from __future__ import annotations
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

_XML_SUFFIXES = {'.kml', '.xml', '.wpml'}
_COORD_TAGS = {
    'coord', 'index', 'speed', 'height', 'coordinates',
    'headingangle', 'executeheight', 'waypointspeed',
    'actionactuatorfunc', 'gimbalyawrotateangle',
    'waypointheadingangle', 'gimbalpitchrotateangle',
    'actionactuatorfuncparam',
}
_NUMBER_RE = re.compile('-?\\d+(?:\\.\\d+)?')


def _local_name(tag: str) -> str:
    return str(tag or '').rsplit('}', 1)[-1].rsplit(':', 1)[-1].lower()


def _normal_number(value: str) -> str:
    try:
        number = float(value)
    except Exception:
        return value.strip()
    if not math.isfinite(number):
        return value.strip()
    return f'{number:.8f}'.rstrip('0').rstrip('.')


def _normalize_coordinates(text: str) -> tuple[str, int]:
    values: list = []
    waypoint_count = 0
    chunks = re.split(r'\s+', str(text or '').strip())
    for chunk in chunks:
        if not chunk:
            continue
        parts = [p for p in chunk.split(',') if p != '']
        if len(parts) >= 2 and all(
            _NUMBER_RE.fullmatch(p.strip()) for p in parts[:2]
        ):
            values.append(','.join(
                _normal_number(p.strip()) for p in parts[:3]
            ))
            waypoint_count += 1
        else:
            nums = _NUMBER_RE.findall(chunk)
            if nums:
                values.extend(_normal_number(x) for x in nums)
    return ' '.join(values), waypoint_count


def _canonical_xml(name: str, raw: bytes) -> tuple[dict[str, Any], int]:
    try:
        root = ET.fromstring(raw)
    except Exception:
        text = raw.decode('utf-8', errors='ignore')
        normalized = ' '.join(text.split())
        return {'name': name, 'fallback': normalized[:200000]}, 0

    items: list = []
    waypoint_count = 0
    coordinate_blocks = 0

    for elem in root.iter():
        local = _local_name(elem.tag)
        text = (elem.text or '').strip()
        if not text:
            continue

        if local == 'coordinates':
            normalized, count = _normalize_coordinates(text)
            if normalized:
                items.append([local, normalized])
                coordinate_blocks += 1
                waypoint_count = max(waypoint_count, count)
        elif local in _COORD_TAGS:
            if _NUMBER_RE.search(text):
                nums = _NUMBER_RE.findall(text)
                norm = ','.join(_normal_number(x) for x in nums)
            else:
                norm = ' '.join(text.split())[:500]
            items.append([local, norm])

    execute_height_count = sum(
        1 for tag, _ in items if tag == 'executeheight'
    )
    index_count = sum(
        1 for tag, _ in items if tag == 'index'
    )
    waypoint_count = max(waypoint_count, execute_height_count, index_count)

    return {
        'name': name,
        'items': items,
        'coordinate_blocks': coordinate_blocks,
    }, waypoint_count


def inspect_mission_content(
    content: bytes,
    filename: str,
    export_type: str = '',
) -> dict[str, Any]:
    """Return a stable semantic fingerprint without modifying the task file.

    ZIP/KMZ archive timestamps and compression ratios are ignored. The fingerprint is based on
    normalized XML waypoint coordinates, heights, speeds and actions, so simply renaming or
    re-zipping a task normally does not change the semantic fingerprint.
    """
    suffix = Path(filename).suffix or f'.{str(export_type).lstrip(".")}'.lower()
    documents: list = []
    archive_entries = 0

    if suffix in {'.kmz', '.zip'} or content[:4] == b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
                names = sorted(n for n in zf.namelist() if not n.endswith('/'))
                archive_entries = len(names)
                for name in names:
                    if Path(name).suffix.lower() in _XML_SUFFIXES:
                        try:
                            documents.append((name, zf.read(name)))
                        except Exception:
                            continue
        except Exception:
            documents = []
    elif suffix in _XML_SUFFIXES or content.lstrip().startswith(b'<'):
        documents.append((Path(filename).name or 'mission.xml', content))

    canonical_docs: list = []
    waypoint_count = 0

    for name, raw in documents:
        canonical, count = _canonical_xml(name, raw)
        canonical_docs.append(canonical)
        waypoint_count = max(waypoint_count, count)

    if canonical_docs:
        fmt = suffix.lstrip('.') or 'xml'
        payload = {'format': fmt, 'documents': canonical_docs}
        canonical_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        semantic = hashlib.sha256(canonical_bytes).hexdigest()
        status = 'xml-normalized'
    else:
        semantic = hashlib.sha256(content).hexdigest()
        status = 'binary-fallback'

    return {
        'semantic_sha256': semantic,
        'waypoint_count': int(waypoint_count),
        'fingerprint_engine': 'jt-mission-semantic-1.0',
        'fingerprint_status': status,
        'document_count': len(canonical_docs),
        'archive_entries': archive_entries,
    }
