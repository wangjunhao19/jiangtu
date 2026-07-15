# Source Generated with Decompyle++
# File: map_webview.pyc (Python 3.11)

from __future__ import annotations
import argparse
import ctypes
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlparse
from services.image_service import ImageCache, read_img_gps
from utils.webview_icon import apply_windows_titlebar_icon_async


def _normalize_local_path(value: str = None) -> Path:
    text = str(value or '').strip()
    if text.lower().startswith('file:'):
        parsed = urlparse(text)
        text = unquote(parsed.path or '')
        if os.name == 'nt':
            candidate = text.lstrip('/')
            if re_drive_prefix(candidate):
                text = candidate
    text = text.replace('/', os.sep) if os.name == 'nt' else text
    return Path(text).expanduser()


def re_drive_prefix(text: str) -> bool:
    return len(text) >= 2 and text[1] == ':'


def _set_windows_file_clipboard(path: Path) -> None:
    """Write a single file to Windows CF_HDROP without PowerShell."""
    if os.name != 'nt':
        raise RuntimeError('复制原文件到剪贴板功能目前仅支持 Windows。')
    path_text = str(path)
    header_size = 20
    payload = path_text.encode('utf-16le') + b'\x00\x00\x00\x00'
    size = header_size + len(payload)
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    GMEM_MOVEABLE = 2
    CF_HDROP = 15
    kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    hglobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not hglobal:
        raise OSError('无法分配剪贴板内存。')
    locked = kernel32.GlobalLock(hglobal)
    if not locked:
        kernel32.GlobalFree(hglobal)
        raise OSError('无法锁定剪贴板内存。')
    try:
        header = (20).to_bytes(4, 'little') + b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00' + (1).to_bytes(4, 'little')
        ctypes.memmove(locked, header, len(header))
        ctypes.memmove(int(locked) + header_size, payload, len(payload))
        kernel32.GlobalUnlock(hglobal)
    except:
        kernel32.GlobalUnlock(hglobal)
        raise
    opened = False
    for _ in range(12):
        if user32.OpenClipboard(None):
            opened = True
            break
        import time
        time.sleep(0.05)
    if not opened:
        kernel32.GlobalFree(hglobal)
        raise OSError('无法打开系统剪贴板，请关闭占用剪贴板的程序后重试。')
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_HDROP, hglobal):
            kernel32.GlobalFree(hglobal)
            raise OSError('写入系统剪贴板失败。')
        hglobal = None
        user32.CloseClipboard()
    except:
        user32.CloseClipboard()
        raise
    return None


def _set_windows_text_clipboard(text: str) -> None:
    """写入Unicode文本剪贴板，供地图图斑信息一键复制。"""
    value = str(text or '')
    if os.name != 'nt':
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
        root.destroy()
        return None
    import ctypes
    from ctypes import wintypes
    GMEM_MOVEABLE = 2
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    encoded = value.encode('utf-16-le') + b'\x00\x00'
    hglobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not hglobal:
        raise OSError('无法申请剪贴板内存。')
    locked = kernel32.GlobalLock(hglobal)
    if not locked:
        kernel32.GlobalFree(hglobal)
        raise OSError('无法锁定剪贴板内存。')
    try:
        ctypes.memmove(locked, encoded, len(encoded))
        kernel32.GlobalUnlock(hglobal)
    except:
        kernel32.GlobalUnlock(hglobal)
        raise
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(hglobal)
        raise OSError('无法打开系统剪贴板，请关闭占用剪贴板的程序后重试。')
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, hglobal):
            kernel32.GlobalFree(hglobal)
            raise OSError('写入系统剪贴板失败。')
        hglobal = None
        user32.CloseClipboard()
    except:
        user32.CloseClipboard()
        raise
    return None


class MapApi:
    def __init__(self, points_file: Path | None = None):
        self.window = None
        self.points_file = points_file
        self._initial_points = None
        self._initial_total = None
        self._initial_stream = None
        self._initial_stream_offset = 0
        self._folder_points = []
        self._folder_scan_lock = threading.RLock()
        self._folder_scan_generation = 0
        self._folder_scan_running = False
        self._folder_scan_done = False
        self._folder_scan_total = 0
        self._folder_scan_processed = 0
        self._folder_scan_error = ''
        self._folder_scan_folder = ''

    def _load_legacy_initial_points(self) -> list[dict]:
        if self._initial_points is not None:
            return self._initial_points
        points = []
        try:
            if self.points_file and self.points_file.is_file():
                data = json.loads(self.points_file.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    points = [x for x in data if isinstance(x, dict)]
        except Exception:
            points = []
        self._initial_points = points
        return points

    def _open_jsonl_stream(self, reset: bool = False) -> None:
        if reset and self._initial_stream is not None:
            try:
                self._initial_stream.close()
            except Exception:
                pass
            self._initial_stream = None
        if self._initial_stream is not None:
            return None
        if not self.points_file or not self.points_file.is_file():
            self._initial_total = 0
            return None
        stream = self.points_file.open('r', encoding='utf-8')
        first = stream.readline()
        total = 0
        try:
            meta = json.loads(first)
            if isinstance(meta, dict):
                total = int(meta.get('__meta__', {}).get('total', 0) or 0)
        except Exception:
            stream.seek(0)
        self._initial_total = max(0, total)
        self._initial_stream = stream
        self._initial_stream_offset = 0
        return None

    def _read_jsonl_page(self, offset: int, limit: int) -> tuple[int, list[dict]]:
        self._open_jsonl_stream()
        if self._initial_stream is None:
            return (0, [])
        if offset != self._initial_stream_offset:
            self._open_jsonl_stream(reset=True)
            if self._initial_stream is None:
                return (0, [])
            for _ in range(offset):
                if not self._initial_stream.readline():
                    break
            self._initial_stream_offset = offset
        items = []
        while len(items) < limit:
            line = self._initial_stream.readline()
            if not line:
                break
            self._initial_stream_offset += 1
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                items.append(item)
        total = int(self._initial_total or 0)
        if total <= 0 and not items:
            total = self._initial_stream_offset
        return (total, items)

    def get_initial_photo_points(self, offset: int = 0, limit: int = 500):
        """流式分块返回照片点位，避免地图启动时一次读取全部照片。"""
        offset = max(0, int(offset or 0))
        limit = min(2000, max(1, int(limit or 500)))
        try:
            if self.points_file and self.points_file.suffix.lower() == '.jsonl':
                total, items = self._read_jsonl_page(offset, limit)
            else:
                points = self._load_legacy_initial_points()
                total = len(points)
                items = points[offset:offset + limit]
            return {'ok': True, 'total': total, 'offset': offset, 'items': items}
        except Exception as exc:
            return {'ok': False, 'message': str(exc), 'total': 0, 'items': []}

    def _append_folder_point(self, info) -> None:
        if not info or not getattr(info, 'has_gps', False):
            return None
        lat = getattr(info, 'lat', None)
        lon = getattr(info, 'lon', None)
        if lat is None or lon is None:
            return None
        with self._folder_scan_lock:
            self._folder_points.append({
                'lat': lat,
                'lon': lon,
                'name': getattr(info, 'filename', '') or Path(getattr(info, 'full_path', '')).name,
                'fullPath': str(Path(getattr(info, 'full_path', ''))),
            })
        return None

    def _scan_photo_folder_worker(self, folder: Path, generation: int) -> None:
        cache = ImageCache()
        try:
            files = sorted(
                [p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in frozenset({'.jpg', '.png', '.jpeg'})],
                key=lambda p: str(p).lower(),
            )
            with self._folder_scan_lock:
                if generation != self._folder_scan_generation:
                    with self._folder_scan_lock:
                        if generation == self._folder_scan_generation:
                            self._folder_scan_running = False
                            self._folder_scan_done = True
                    return None
            with self._folder_scan_lock:
                self._folder_scan_total = len(files)
            pending = []
            for path in files:
                with self._folder_scan_lock:
                    if generation != self._folder_scan_generation:
                        with self._folder_scan_lock:
                            if generation == self._folder_scan_generation:
                                self._folder_scan_running = False
                                self._folder_scan_done = True
                        return None
                cached = cache.get(str(path))
                if cached is None:
                    pending.append(path)
                    continue
                self._append_folder_point(cached)
                with self._folder_scan_lock:
                    self._folder_scan_processed += 1
            workers = min(4, max(1, os.cpu_count() or 1))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(read_img_gps, str(path)): path for path in pending}
                for future in as_completed(futures):
                    with self._folder_scan_lock:
                        if generation != self._folder_scan_generation:
                            with self._folder_scan_lock:
                                if generation == self._folder_scan_generation:
                                    self._folder_scan_running = False
                                    self._folder_scan_done = True
                            return None
                    path = futures[future]
                    try:
                        info = future.result()
                    except Exception:
                        info = None
                    if info is not None:
                        cache.set(str(path), info)
                        self._append_folder_point(info)
                    with self._folder_scan_lock:
                        self._folder_scan_processed += 1
            cache.save_cache()
        except Exception as exc:
            with self._folder_scan_lock:
                if generation == self._folder_scan_generation:
                    self._folder_scan_error = str(exc)
        finally:
            with self._folder_scan_lock:
                if generation == self._folder_scan_generation:
                    self._folder_scan_running = False
                    self._folder_scan_done = True
        return None

    def choose_photo_folder(self):
        """选择照片目录后立即返回，EXIF读取在后台执行，避免地图窗口假死。"""
        import webview
        if self.window is None:
            return {'ok': False, 'message': '地图窗口尚未就绪。'}
        dialog_enum = getattr(getattr(webview, 'FileDialog', None), 'FOLDER', None)
        if dialog_enum is None:
            dialog_enum = getattr(webview, 'FOLDER_DIALOG', None)
        result = self.window.create_file_dialog(dialog_enum)
        if not result:
            return {'ok': False, 'cancelled': True}
        folder = Path(result[0])
        with self._folder_scan_lock:
            self._folder_scan_generation += 1
            generation = self._folder_scan_generation
            self._folder_points = []
            self._folder_scan_running = True
            self._folder_scan_done = False
            self._folder_scan_total = 0
            self._folder_scan_processed = 0
            self._folder_scan_error = ''
            self._folder_scan_folder = str(folder)
        threading.Thread(
            target=self._scan_photo_folder_worker,
            args=(folder, generation),
            name='JTMapPhotoScanner',
            daemon=True,
        ).start()
        return {'ok': True, 'folder': str(folder), 'scan_generation': generation}

    def get_photo_scan_status(self):
        with self._folder_scan_lock:
            return {
                'ok': True,
                'folder': self._folder_scan_folder,
                'running': self._folder_scan_running,
                'done': self._folder_scan_done,
                'total': self._folder_scan_total,
                'processed': self._folder_scan_processed,
                'gps_total': len(self._folder_points),
                'error': self._folder_scan_error,
                'scan_generation': self._folder_scan_generation,
            }

    def get_folder_photo_points(self, offset: int = 0, limit: int = 500):
        """增量返回已经完成EXIF读取的照片点，扫描过程中也可持续调用。"""
        offset = max(0, int(offset or 0))
        limit = min(800, max(1, int(limit or 500)))
        try:
            with self._folder_scan_lock:
                total = len(self._folder_points)
                items = list(self._folder_points[offset:offset + limit])
                done = self._folder_scan_done
            return {'ok': True, 'total': total, 'offset': offset, 'items': items, 'done': done}
        except Exception as exc:
            return {'ok': False, 'message': str(exc), 'total': 0, 'items': []}

    def close(self):
        """释放点位流和后台扫描资源；地图关闭后允许主程序立即再次打开。"""
        with self._folder_scan_lock:
            self._folder_scan_generation += 1
            self._folder_scan_running = False
            self._folder_scan_done = True
        if self._initial_stream is not None:
            try:
                self._initial_stream.close()
            except Exception:
                pass
            self._initial_stream = None
        return {'ok': True}

    def copy_photo(self, path: str):
        """把照片原文件写入Windows文件剪贴板，用户可在任意文件夹Ctrl+V。"""
        photo = _normalize_local_path(path)
        if not photo.is_file():
            return {'ok': False, 'message': f'照片不存在：{photo}'}
        _set_windows_file_clipboard(photo)
        return {'ok': True, 'path': str(photo)}

    def copy_text(self, text: str):
        """复制图斑规范信息到系统剪贴板。"""
        _set_windows_text_clipboard(str(text or ''))
        return {'ok': True}


def run_map_webview(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--jt-map-webview', action='store_true')
    parser.add_argument('--html', required=True)
    parser.add_argument('--points-file', default='')
    args, _ = parser.parse_known_args(argv)
    html_path = Path(args.html).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f'地图文件不存在：{html_path}')
    if args.points_file:
        points_file = Path(args.points_file).resolve()
    else:
        jsonl_path = html_path.with_suffix('.points.jsonl')
        points_file = jsonl_path if jsonl_path.exists() else html_path.with_suffix('.points.json')
    import webview
    api = MapApi(points_file)
    title = '疆途地图查看 V1.0'
    try:
        window = webview.create_window(
            title,
            html_path.as_uri(),
            js_api=api,
            width=1500,
            height=920,
            min_size=(980, 650),
            background_color='#dfeaf5',
        )
    except TypeError:
        window = webview.create_window(
            title,
            html_path.as_uri(),
            js_api=api,
            width=1500,
            height=920,
            min_size=(980, 650),
        )
    window.api = api
    apply_windows_titlebar_icon_async(title)
    try:
        window.events.loaded += lambda: apply_windows_titlebar_icon_async(title)
    except Exception:
        pass

    def cleanup_temp_files():
        api.close()
        for path in (points_file, html_path):
            try:
                if path and path.is_file():
                    path.unlink(missing_ok=True)
            except Exception:
                pass

    try:
        window.events.closing += lambda: api.close()
        window.events.closed += cleanup_temp_files
    except Exception:
        pass
    if os.name == 'nt':
        try:
            webview.start(gui='edgechromium', debug=False)
        except Exception:
            webview.start(debug=False)
    else:
        webview.start(debug=False)
    cleanup_temp_files()
    return 0
