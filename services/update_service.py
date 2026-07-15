# Source Generated with Decompyle++
# File: update_service.pyc (Python 3.11)

"""在线更新检查与下载安装服务（V1.0）。"""
from __future__ import annotations
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urljoin, urlparse
import requests
from config import APP_NAME, ONLINE_LICENSE_SERVER


@dataclass
class UpdateResult:
    success: bool = False
    has_update: bool = False
    latest_version: str = ''
    current_version: str = ''
    force_update: bool = False
    download_url: str = ''
    download_sha256: str = ''
    download_size: int = 0
    update_log: str = ''
    message: str = ''


def normalize_version(v: str) -> str:
    """把 V1.0 / v1.4 / 1.3.8 等写法统一成纯数字版本号。"""
    v = (v or '').strip()
    v = v.replace('版本', '').replace('版', '')
    v = v.lstrip('Vv')
    return v.strip()


def version_tuple(v: str) -> tuple[int, int, int, int]:
    v = normalize_version(v)
    nums = re.findall(r'\d+', v)
    parts = [int(x) for x in nums[:4]]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def get_current_version() -> str:
    m = re.search(r'[Vv]?(\d+(?:\.\d+){0,3})', APP_NAME or '')
    if m:
        return m.group(1)
    return '1.0'


def _absolute_download_url(server: str, value: str) -> str:
    value = str(value or '').strip()
    if not value:
        return ''
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return value
    return urljoin(server.rstrip('/') + '/', value.lstrip('/'))


def check_for_update(timeout: int = 8) -> UpdateResult:
    """检查服务器版本。失败只返回错误信息，不影响软件其他业务。"""
    current = get_current_version()
    server = (ONLINE_LICENSE_SERVER or '').rstrip('/')

    if not server:
        return UpdateResult(
            False,
            current_version=current,
            message='未配置更新服务器地址',
        )

    headers = {
        'User-Agent': f'JT-Updater/{current}',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache',
    }
    errors: list = []
    data = None

    connect_timeout = max(3, min(8, int(timeout or 8)))
    read_timeout = max(5, min(15, int(timeout or 8)))

    for endpoint in ('/api/version', '/version'):
        try:
            resp = requests.get(
                f'{server}{endpoint}',
                headers=headers,
                params={'_': int(__import__('time').time())},
                timeout=(connect_timeout, read_timeout),
                allow_redirects=True,
            )
            if resp.status_code != 200:
                errors.append(f'{endpoint}: HTTP {resp.status_code}')
                continue
            payload = resp.json()
            if not isinstance(payload, dict):
                errors.append(f'{endpoint}: 返回格式不是JSON对象')
                continue
            data = payload
            break
        except Exception as exc:
            errors.append(f'{endpoint}: {exc}')
            exc = None
            del exc

    if data is None:
        return UpdateResult(
            False,
            current_version=current,
            message='无法连接更新服务器：' + '；'.join(errors[-2:]),
        )

    latest = normalize_version(str(
        data.get('latest_version') or data.get('version') or ''
    ))
    if not latest:
        return UpdateResult(
            False,
            current_version=current,
            message='服务器未返回最新版本号',
        )

    download_url = _absolute_download_url(server, str(
        data.get('download_url') or ''
    ))
    force_update = bool(data.get('force_update', False))
    update_log = str(
        data.get('feature_description')
        or data.get('update_log')
        or data.get('changelog')
        or ''
    ).strip()
    sha256 = re.sub(
        r'[^0-9a-fA-F]', '',
        str(data.get('download_sha256') or data.get('sha256') or ''),
    ).lower()
    if len(sha256) != 64:
        sha256 = ''

    try:
        size = max(0, int(
            data.get('download_size') or data.get('file_size') or 0
        ))
    except Exception:
        size = 0

    common = dict(
        latest_version=latest,
        current_version=current,
        force_update=force_update,
        download_url=download_url,
        download_sha256=sha256,
        download_size=size,
        update_log=update_log,
    )

    if version_tuple(latest) > version_tuple(current):
        return UpdateResult(
            **{'has_update': True, 'message': f'发现新版本 V{latest}'},
            **common,
        )
    return UpdateResult(
        **{'has_update': False, 'message': f'当前已是最新版本：V{current}'},
        **common,
    )


ProgressCallback = Callable[[int, int], None]


def _download_filename(
    url: str,
    content_disposition: str,
    latest_version: str,
) -> str:
    name = ''
    if content_disposition:
        match = re.search(
            r'filename\*?=(?:UTF-8\'\'|")?([^";]+)',
            content_disposition,
            re.I,
        )
        if match:
            name = unquote(match.group(1)).strip().strip('"')

    if not name:
        name = unquote(Path(urlparse(url).path).name)

    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', name).strip(' ._')

    if not name or Path(name).suffix.lower() not in {'.exe', '.msi'}:
        version = normalize_version(latest_version) or 'latest'
        name = f'疆途智能巡查管理平台V{version}_Setup.exe'

    return name


def download_update(
    download_url: str,
    target_dir: str | os.PathLike,
    latest_version: str,
    progress_callback: Optional[ProgressCallback],
    cancel_event=None,
    timeout: tuple[int, int] = (10, 180),
    expected_sha256: str = '',
    expected_size: int = 0,
) -> Path:
    """流式下载安装包并校验大小、PE/MSI签名和可选SHA256。"""
    url = str(download_url or '').strip()
    if not url:
        raise ValueError('未配置安装包下载地址')

    folder = Path(target_dir)
    folder.mkdir(parents=True, exist_ok=True)

    expected_sha256 = re.sub(
        r'[^0-9a-fA-F]', '',
        str(expected_sha256 or ''),
    ).lower()
    if len(expected_sha256) != 64:
        expected_sha256 = ''
    expected_size = max(0, int(expected_size or 0))

    with requests.get(
        url, stream=True, timeout=timeout, allow_redirects=True,
    ) as resp:
        resp.raise_for_status()

        filename = _download_filename(
            url,
            resp.headers.get('Content-Disposition', ''),
            latest_version,
        )
        target = folder / filename
        temp = target.with_name(target.name + '.part')

        total = int(resp.headers.get('Content-Length') or expected_size or 0)
        received = 0
        digest = hashlib.sha256()

        with temp.open('wb') as f:
            for chunk in resp.iter_content(chunk_size=262144):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError('下载已取消')
                if not chunk:
                    continue
                f.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)

    if received <= 0:
        raise RuntimeError('下载文件为空')

    if expected_size and received != expected_size:
        raise RuntimeError(
            f'安装包大小校验失败：应为 {expected_size} 字节，实际 {received} 字节'
        )

    actual_sha256 = digest.hexdigest().lower()
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise RuntimeError('安装包SHA256校验失败，文件可能未上传完整或已被替换')

    with temp.open('rb') as check_file:
        signature = check_file.read(8)

    suffix = target.suffix.lower()
    if suffix == '.exe' and not signature.startswith(b'MZ'):
        raise RuntimeError('下载内容不是有效的 Windows EXE 安装程序')
    if suffix == '.msi' and signature != bytes.fromhex('D0CF11E0A1B11AE1'):
        raise RuntimeError('下载内容不是有效的 Windows MSI 安装程序')

    os.replace(temp, target)

    return target
