# Source Generated with Decompyle++
# File: sanzi_upload_service.pyc (Python 3.11)

from __future__ import annotations
import base64
import csv
import json
import mimetypes
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import requests
from PIL import Image
from services.sanzi_rules import ACCESSORY_TYPE_LABELS, USE_STATUS_REQUIREMENT_TYPES, accessory_label, land_actuality_label, land_status_label, normalize_int, proof_accessory_type, scene_photo_accessory_type, use_status_label
IMAGE_EXTS = ('.jpg', '.jpeg', '.png')
UPLOAD_EXTS = ('.jpg', '.jpeg', '.png', '.pdf')
FIELD_PHOTO_ACCESSORY_TYPE = 5

def _user_data_file(filename = None):
    if not os.getenv('APPDATA'):
        pass
    base = os.path.join(str(Path.home()), '.jiangtu')
    folder = os.path.join(base, 'JiangTu')
    os.makedirs(folder, exist_ok = True)
    return os.path.join(folder, filename)

LOGIN_CACHE_FILE = _user_data_file('sanzi_login.json')

class SanziAuthenticationError(RuntimeError):
    '''三资平台登录状态失效。'''
    pass

@dataclass
class SanziLoginOptions:
    web_url: str = 'http://222.143.69.159:38590'
    base_url: str = 'http://222.143.69.159:38762'
    login_url: str = 'http://222.143.69.159:38590/dist/#/login'
    captcha_url: str = ''
    username: str = ''
    password: str = ''
    captcha_code: str = ''
    remember_account: bool = True


@dataclass
class SanziUploadOptions:
    base_url: str = 'http://222.143.69.159:38762'
    origin: str = 'http://222.143.69.159:38590'
    token: str = ''
    token_header: str = 'Token'
    cookie: str = ''
    districtcode: str = ''
    districtname: str = ''
    photo_root: str = ''
    max_photos: int = 3
    only_with_use_status: bool = True
    skip_uploaded: bool = True
    average_pick: bool = True
    delay_seconds: float = 0.15
    add_logo: bool = False
    retry_count: int = 3
    photo_quality: int = 75


@dataclass
class SanziUploadResult:
    landcode: str = ''
    filename: str = ''
    status: str = ''
    message: str = ''


@dataclass
class ArchiveMaterial:
    landcode: str = ''
    accessory_type: int = 0
    label: str = ''
    file_path: str = ''
    filename: str = ''
    landcode_source: str = '文件名'
    match_note: str = ''

def load_login_cache():
    try:
        with open(LOGIN_CACHE_FILE, 'r', encoding = 'utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}






def save_login_cache(data = None):
    if not data:
        return
    safe = dict(data)
    safe.pop('password', None)
    safe.pop('captcha_code', None)
    Path(LOGIN_CACHE_FILE).parent.mkdir(parents = True, exist_ok = True)
    with open(LOGIN_CACHE_FILE, 'w', encoding = 'utf-8') as f:
        json.dump(safe, f, ensure_ascii = False, indent = 2)


def clear_login_cache():
    
    try:
        Path(LOGIN_CACHE_FILE).unlink(missing_ok = True)
        return None
    except Exception:
        save_login_cache({ })
        return None



def options_from_cache(**overrides):
    cache = load_login_cache()
    opts = SanziLoginOptions()
    for key, value in cache.items():
        if hasattr(opts, key):
            setattr(opts, key, value)
    for key, value in overrides.items():
        if hasattr(opts, key):
            setattr(opts, key, value)
    return opts


def _try_json_loads(text = None):
    if not text:
        return None
    
    try:
        return json.loads(text)
    except Exception:
        return None



def _walk_json(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_json(item)


def _har_content_text(content = None):
    text = content.get('text') or ''
    if not text:
        return ''
    encoding = (content.get('encoding') or '').lower()
    if encoding == 'base64':
        import base64
        return base64.b64decode(text).decode('utf-8', errors = 'ignore')
    return text


# ── 以下为从反汇编重建的函数 ──

def _extract_tokens_from_text(text=None):
    if not text:
        return []
    found = []
    patterns = [r'"token"\s*:\s*"([^"]+)"', r'"access_token"\s*:\s*"([^"]+)"']
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = 'token'
            if 'access' in pattern:
                name = 'access_token'
            found.append((name, match.group(1)))
    return found


def _merge_login_identity(result=None, obj=None):
    if not isinstance(obj, dict):
        return result
    for item in obj.items() if isinstance(obj, dict) else []:
        key, value = item
        if isinstance(key, str) and isinstance(value, str) and value:
            token_name = key.lower()
            if 'token' in token_name or 'authorization' in token_name:
                result.setdefault('token', value)
            if 'cookie' in token_name:
                result.setdefault('cookie', value)
    return result


def import_login_har(har_path=None):
    result = {'token': '', 'cookie': '', 'districtcode': '', 'districtname': ''}
    if not har_path or not os.path.isfile(har_path):
        return result
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    cookies = []
    for entry in (har.get('log', {}).get('entries', []) if isinstance(har, dict) else []):
        request = entry.get('request', {})
        response = entry.get('response', {})
        url = request.get('url', '')
        for header in request.get('headers', []):
            name = header.get('name', '').lower()
            value = header.get('value', '')
            if name == 'cookie':
                cookies.append(value)
            if 'token' in name:
                result.setdefault('token', value)
        content_text = _har_content_text(response.get('content', {}))
        if content_text:
            for name, value in _extract_tokens_from_text(content_text):
                if 'token' in name and not result.get('token'):
                    result['token'] = value
    if cookies:
        result['cookie'] = '; '.join(cookies)
    return result


def extract_token(data=None):
    result = {'token': '', 'cookie': ''}
    return result


def _message_from_json(data=None):
    if isinstance(data, dict):
        return data.get('message') or data.get('msg') or ''
    return ''


def _looks_auth_error(status_code=0, data=None, text=''):
    code = 0
    try:
        code = int(status_code)
    except Exception:
        pass
    if code in (401, 403):
        return True
    words = ('token', 'expired', 'login', 'auth', 'unauthorized')
    return any(w in str(text).lower() for w in words)


class SanziClient:
    """三资平台 HTTP 客户端（简化重建）。"""

    def __init__(self, options=None):
        self.options = options or SanziUploadOptions()
        self.session = requests.Session()
        if self.options.token:
            self.session.headers[self.options.token_header] = self.options.token
        if self.options.cookie:
            self.session.headers['Cookie'] = self.options.cookie

    def _url(self, path):
        return f'{self.options.base_url.rstrip("/")}/{path.lstrip("/")}'

    def get(self, path, params=None):
        return self.session.get(self._url(path), params=params, timeout=30)

    def post(self, path, data=None, json_data=None, files=None):
        return self.session.post(self._url(path), data=data, json=json_data, files=files, timeout=60)


def is_landcode(name=None):
    if not name:
        return False
    return bool(re.match(r'^\d{4,}$', str(name).strip()))


def extract_landcode(name=None):
    if not name:
        return ''
    groups = re.findall(r'(\d{4,})', str(name))
    return groups[0] if groups else ''


def collect_land_photo_groups(photo_root=None):
    groups = {}
    if not photo_root or not os.path.isdir(photo_root):
        return groups
    for entry in os.scandir(photo_root):
        if entry.is_dir():
            folder = entry.name
            landcode = extract_landcode(folder)
            if landcode:
                photos = [os.path.join(entry.path, f) for f in os.listdir(entry.path)
                          if os.path.splitext(f)[1].lower() in IMAGE_EXTS]
                if photos:
                    groups[landcode] = sorted(photos)
    return groups


def collect_landcodes_from_root(photo_root=None):
    return set(collect_land_photo_groups(photo_root).keys())


def pick_photos_evenly(photos, max_photos=3, average=True):
    if not photos:
        return []
    if len(photos) <= max_photos:
        return list(photos)
    if average:
        step = len(photos) / max_photos
        return [photos[int(i * step)] for i in range(max_photos)]
    return photos[:max_photos]


def _find_first_value(data, keys):
    wanted = keys if isinstance(keys, (list, tuple)) else [keys]
    if not isinstance(data, dict):
        return None
    for key in wanted:
        value = data.get(key)
        if value is not None:
            text = str(value).strip()
            if text and text.lower() not in ('null', 'none', 'nan', ''):
                return text
    return None


def get_use_status(detail=None):
    return _find_first_value(detail, ('usestatus', 'use_status', 'USESTATUS'))


def get_land_current_status(detail=None):
    return _find_first_value(detail, ('landcurrentstatus', 'land_current_status'))


def has_required_land_fields(detail=None):
    use_status = get_use_status(detail)
    land_status = get_land_current_status(detail)
    return use_status is not None and land_status is not None


def resolve_photo_accessory_type(detail=None):
    status = get_use_status(detail)
    scene_type = scene_photo_accessory_type(status)
    return scene_type


def accessory_type_label(accessory_type=0):
    return accessory_label(accessory_type)


def _doc_accessory_type(doc=None):
    value = 0
    if isinstance(doc, dict):
        try:
            value = int(float(str(doc.get('accessorytype', doc.get('accessoryType', 0)))))
        except Exception:
            value = 0
    return value


def _doc_id(doc=None):
    if isinstance(doc, dict):
        return str(doc.get('id', doc.get('fileid', '')))
    return ''


def _doc_name(doc=None):
    value = ''
    if isinstance(doc, dict):
        value = str(doc.get('name', doc.get('filename', ''))).strip()
    return value


def uploaded_names(docs=None, accessorytype=None):
    docs = docs or []
    result = set()
    for doc in docs:
        if _doc_accessory_type(doc) == normalize_int(accessorytype, -1):
            name = _doc_name(doc)
            if name:
                result.add(name)
    return result


def is_target_photo_doc(doc=None, accessory_type=0):
    return _doc_accessory_type(doc) == normalize_int(accessory_type, -1)


def is_field_photo_doc(doc=None):
    return _doc_accessory_type(doc) == FIELD_PHOTO_ACCESSORY_TYPE


def _extract_upload_file_id(result=None):
    value = None
    if isinstance(result, dict):
        for key in ('id', 'fileId', 'fileid', 'data'):
            value = result.get(key)
            if value:
                return str(value)
    return ''


def _verify_upload(docs_after=None, filename='', before_ids=None, expected_type=0, returned_file_id=''):
    docs = docs_after or []
    matches = []
    for doc in docs:
        if _doc_name(doc) == filename and _doc_accessory_type(doc) == normalize_int(expected_type, -1):
            doc_id = _doc_id(doc)
            if doc_id not in (before_ids or set()):
                matches.append(doc_id)
    return (True, matches[0]) if matches else (False, '')


def _verify_uploaded_photo(docs_after=None, filename='', before_ids=None, expected_type=0, returned_file_id=''):
    return _verify_upload(docs_after, filename, before_ids, expected_type, returned_file_id)


def _verify_uploaded_field_photo(docs_after=None, filename='', before_ids=None, returned_file_id=''):
    return _verify_upload(docs_after, filename, before_ids, FIELD_PHOTO_ACCESSORY_TYPE, returned_file_id)


def check_photo_groups(options=None, log=None, progress=None):
    return []


def upload_photo_groups(options=None, log=None, progress=None):
    return []


def delete_field_photos(options=None, log=None, progress=None):
    return []


def _write_json(path=None, data=None):
    if not path:
        return
    temp = str(path) + '.tmp'
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(data or {}, f, ensure_ascii=False, indent=2)
    shutil.move(temp, str(path))


def _upload_registry_path(project_dir=None):
    return os.path.join(str(project_dir), 'upload_registry.json')


def _load_upload_registry(project_dir=None):
    path = _upload_registry_path(project_dir)
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _save_upload_registry(project_dir=None, rows=None):
    _write_json(_upload_registry_path(project_dir), rows or [])


def _record_uploaded_file(project_dir=None, landcode='', filename='', accessory_type=0, file_id=''):
    rows = _load_upload_registry(project_dir)
    row = {
        'landcode': landcode, 'filename': filename,
        'accessory_type': accessory_type, 'file_id': file_id,
        'status': 'uploaded', 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    rows.append(row)
    _save_upload_registry(project_dir, rows)


def _mark_registry_deleted(project_dir=None, file_id=''):
    rows = _load_upload_registry(project_dir)
    changed = False
    for row in rows:
        if row.get('file_id') == file_id:
            row['status'] = 'deleted'
            changed = True
    if changed:
        _save_upload_registry(project_dir, rows)


def _reconcile_upload_registry(project_dir=None, records=None):
    pass


def sync_all_sanzi_data(options=None, project_dir=None, **kwargs):
    """全量同步三资数据（本地模拟：返回空记录）。"""
    return ([], [])


def load_synced_records(project_dir=None):
    path = os.path.join(str(project_dir), 'synced_records.json')
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def refresh_uploaded_land_records(options=None, project_dir=None, records=None, landcodes=None, log=None):
    return []


_ARCHIVE_RE = re.compile(r'(\d{4,})')
_MATERIAL_KEYWORDS = {}


def _normalized_material_name(name=None):
    text = str(name or '').strip()
    return text


def _candidate_landcode(text=None, known_codes=None):
    if not text:
        return ''
    groups = _ARCHIVE_RE.findall(str(text))
    known_codes = known_codes or set()
    for group in groups:
        if group in known_codes:
            return group
    return groups[0] if groups else ''


def _landcode_from_path(path=None, root=None, known_codes=None):
    filename_code = _candidate_landcode(os.path.basename(str(path or '')), known_codes)
    if filename_code:
        return filename_code, '文件名'
    known_codes = known_codes or set()
    parents = Path(path or '.').parents
    for parent in parents:
        code = _candidate_landcode(parent.name, known_codes)
        if code:
            return code, '目录名'
        if root and str(parent) == str(root):
            break
    return '', ''


def _material_type_from_name(filename=None, use_status=None):
    stem = Path(filename or '').stem
    return 0


def scan_archive_materials(archive_root=None, records=None, include_scene_photos=True, include_other_materials=True, progress=None):
    """扫描归档目录，识别图斑材料文件。"""
    materials = []
    problems = []
    root = Path(archive_root or '.')
    if not root.is_dir():
        return materials, problems
    status_lookup = {}
    if records:
        for record in records:
            source = record.get('detail', record) if isinstance(record, dict) else {}
            landcode = str(source.get('landcode', '')).strip()
            if landcode:
                status_lookup[landcode] = source
    known_codes = set(status_lookup.keys())
    paths = sorted(root.rglob('*'))
    paths = [p for p in paths if p.is_file() and p.suffix.lower() in UPLOAD_EXTS]
    total = len(paths)
    for index, path in enumerate(paths):
        if progress:
            try:
                progress(index, total, str(path.relative_to(root)))
            except Exception:
                pass
        landcode, source = _landcode_from_path(path, root, known_codes)
        if not landcode:
            continue
        filename_code = _candidate_landcode(path.stem, known_codes)
        path_code = landcode
        status = status_lookup.get(landcode, {})
        accessory_type = _material_type_from_name(path.name, get_use_status(status))
        matched_by = source or '路径'
        is_scene = accessory_type == scene_photo_accessory_type(get_use_status(status))
        note_parts = []
        if is_scene and not include_scene_photos:
            continue
        if not is_scene and not include_other_materials:
            continue
        materials.append(ArchiveMaterial(
            landcode=landcode,
            accessory_type=accessory_type,
            label=accessory_label(accessory_type),
            file_path=str(path),
            filename=path.name,
            landcode_source=matched_by,
            match_note='; '.join(note_parts),
        ))
    return materials, problems


def _contract_id(contract=None):
    if isinstance(contract, dict):
        return str(contract.get('id', contract.get('contractid', '')))
    return ''


def _pay_id(payment=None):
    if isinstance(payment, dict):
        return str(payment.get('id', payment.get('paymentid', '')))
    return ''


def _archive_photo_sort_key(item=None):
    stem = Path(item.file_path if isinstance(item, ArchiveMaterial) else str(item or '')).stem
    numbers = re.findall(r'\d+', stem)
    return [int(n) for n in numbers]


def _pick_evenly(items=None, limit=3):
    items = list(items or [])
    if len(items) <= limit:
        return items, []
    selected = []
    omitted = []
    step = len(items) / limit
    for index, item in enumerate(items):
        if len(selected) < limit and index >= int(len(selected) * step):
            selected.append(item)
        else:
            omitted.append(item)
    return selected, omitted


def _limit_scene_materials(materials=None, max_per_land=3):
    scene_groups = {}
    others = []
    for item in (materials or []):
        if item.accessory_type == 5:
            scene_groups.setdefault(item.landcode, []).append(item)
        else:
            others.append(item)
    selected_scene = []
    omitted_scene = []
    for group in scene_groups.values():
        sel, omit = _pick_evenly(group, max_per_land)
        selected_scene.extend(sel)
        omitted_scene.extend(omit)
    return others + selected_scene, omitted_scene


def _critical_exif_state(path=None):
    return {}


def _prepare_jpeg_upload_copy(file_path=None, quality=75):
    return str(file_path or ''), ''


def upload_archive_materials(options=None, archive_root=None, **kwargs):
    return []


def delete_platform_attachments(options=None, records=None, **kwargs):
    return []


def export_upload_log(results=None, out_csv=None):
    if not out_csv:
        return
    with open(str(out_csv), 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['landcode', 'filename', 'status', 'message'])
        for result in (results or []):
            if isinstance(result, SanziUploadResult):
                writer.writerow([result.landcode, result.filename, result.status, result.message])
            elif isinstance(result, dict):
                writer.writerow([result.get('landcode', ''), result.get('filename', ''),
                                 result.get('status', ''), result.get('message', '')])
