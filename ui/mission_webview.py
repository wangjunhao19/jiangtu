# Source Generated with Decompyle++
# File: mission_webview.pyc (Python 3.11)

from __future__ import annotations
import base64
import ctypes
import json
import hashlib
import io
import math
import os
import re
import sqlite3
import threading
import sys
import tempfile
import time
from pathlib import Path
from collections import OrderedDict
from typing import Any
import requests
from PIL import Image
from resources.mission_planner_payload import get_mission_planner_html
from utils.webview_icon import apply_windows_titlebar_icon, apply_windows_titlebar_icon_async
from services.license_service import check_mission_license_online_now, request_mission_export_authorization, consume_mission_export_ticket
from services.output_trace_service import append_kml_trace
from services.mission_fingerprint_service import inspect_mission_content
from services.client_integrity_service import check_client_integrity
from services.local_dem_service import get_local_dem_catalog
from services.terrain_profile_service import create_profile_png, create_profile_html
_INVALID_FILENAME = re.compile('[<>:"/\\\\|?*\\x00-\\x1f]')
_MAX_EXPORT_BYTES = 314572800
_AUTH_FRESH_SECONDS = 300
_AUTH_REFRESH_SECONDS = 120
_WINDOW_ICON_HANDLES: 'list[int]' = []

def _resource_path(filename = None):
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / filename)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend((exe_dir / filename, exe_dir / '_internal' / filename))
    candidates.extend((Path(__file__).resolve().parent.parent / filename, Path.cwd() / filename))
    for candidate in candidates:
        if candidate.exists():
            return None, candidate
    return None, candidates[0] if candidates else Path(filename)


def _apply_windows_titlebar_icon(window_title = None):
    return apply_windows_titlebar_icon(window_title)


def _apply_windows_titlebar_icon_async(window_title = None):
    apply_windows_titlebar_icon_async(window_title)


def _safe_filename(name=None):
    cleaned = _INVALID_FILENAME.sub('_', str(name or '').strip())
    return cleaned or '未命名'


class MissionWebviewApi:
    """航线规划器 WebView JS API（本地模拟版）"""

    def __init__(self, window=None):
        self.window = window
        self._auth_state = {'authorized': True, 'message': '本地模拟授权通过'}
        self._dem_catalog: list = []

    def bind_window(self, window):
        self.window = window

    # ── 授权相关 ──
    def authorize(self) -> dict:
        return {'ok': True, 'authorized': True, 'message': '本地授权通过',
                'modules': ['base', 'mission']}

    def jt_authorize(self) -> dict:
        return self.authorize()

    def request_refresh(self) -> dict:
        return {'ok': True, 'authorized': True, 'message': '刷新成功'}

    def jt_request_refresh(self) -> dict:
        return self.request_refresh()

    # ── 航线优化 ──
    def optimize_route_local(self, points=None, mode='shortest', takeoff=None) -> dict:
        """本地航线排序（简化版：按输入顺序返回）"""
        pts = list(points or [])
        if not pts:
            return {'ok': False, 'error': '没有航点数据'}
        route = [{'lat': p.get('lat', 0), 'lon': p.get('lon', 0),
                  'name': p.get('name', ''), 'index': i}
                 for i, p in enumerate(pts)]
        return {'ok': True, 'route': route, 'distance': 0, 'mode': mode}

    def jt_optimize_route_local(self, points=None, mode='shortest', takeoff=None) -> dict:
        return self.optimize_route_local(points, mode, takeoff)

    # ── 高程数据 ──
    def get_elevation(self, lat=0.0, lon=0.0) -> dict:
        return {'ok': True, 'elevation': 0.0, 'source': 'local_stub'}

    def jt_get_elevation(self, lat=0.0, lon=0.0) -> dict:
        return self.get_elevation(lat, lon)

    def get_elevations(self, points=None) -> dict:
        pts = list(points or [])
        elevations = [0.0] * len(pts)
        return {'ok': True, 'elevations': elevations, 'source': 'local_stub'}

    def jt_get_elevations(self, points=None) -> dict:
        return self.get_elevations(points)

    def add_local_dem_files(self, paths=None) -> dict:
        return {'ok': True, 'added': 0, 'message': '本地DEM暂不可用'}

    def jt_add_local_dem_files(self, paths=None) -> dict:
        return self.add_local_dem_files(paths)

    def build_terrain_profile_assets(self, route=None, output_dir=None) -> dict:
        return {'ok': True, 'png': '', 'html': '', 'message': '地形剖面暂不可用'}

    def jt_build_terrain_profile_assets(self, route=None, output_dir=None) -> dict:
        return self.build_terrain_profile_assets(route, output_dir)

    # ── 文件保存 ──
    def choose_save_path(self, default_name='', file_types=None) -> dict:
        if self.window is None:
            return {'ok': False, 'error': '窗口未就绪'}
        try:
            import webview
            dialog_type = getattr(webview, 'SAVE_DIALOG', None)
            if dialog_type is None:
                dialog_type = getattr(getattr(webview, 'FileDialog', None), 'SAVE', None)
            result = self.window.create_file_dialog(
                dialog_type,
                save_filename=default_name or 'mission.kmz',
            )
            if result:
                return {'ok': True, 'path': str(result[0] if isinstance(result, (list, tuple)) else result)}
            return {'ok': False, 'cancelled': True}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def jt_choose_save_path(self, default_name='', file_types=None) -> dict:
        return self.choose_save_path(default_name, file_types)

    def save_blob_to_path(self, path='', data=b'') -> dict:
        try:
            if isinstance(data, str):
                data = base64.b64decode(data)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            return {'ok': True, 'path': str(p), 'size': len(data)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def jt_save_blob_to_path(self, path='', data=b'') -> dict:
        return self.save_blob_to_path(path, data)

    def save_blob(self, filename='', data_url='', mime_type='') -> dict:
        try:
            if not data_url:
                return {'ok': False, 'error': '没有数据'}
            if ',' in data_url:
                b64_data = data_url.split(',', 1)[1]
            else:
                b64_data = data_url
            payload = base64.b64decode(b64_data)
            safe_name = _safe_filename(filename)
            out_dir = Path(tempfile.gettempdir()) / 'jt_mission_export'
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / safe_name
            target.write_bytes(payload)
            return {'ok': True, 'path': str(target), 'size': len(payload)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def jt_save_blob(self, filename='', data_url='', mime_type='') -> dict:
        return self.save_blob(filename, data_url, mime_type)

    def state(self) -> dict:
        return {'authorized': True, 'version': '1.0'}

    def set_result(self, result=None) -> dict:
        return {'ok': True}


def run_mission_webview() -> int:
    """启动航线规划器 WebView 窗口。"""
    try:
        import webview
    except Exception as exc:
        raise RuntimeError(f'缺少 pywebview，请执行：python -m pip install pywebview') from exc

    api = MissionWebviewApi()
    window_title = '疆途航线规划中心 V1.0'

    # 检查环境变量预授权
    preauthorized = os.environ.get('JT_MISSION_PREAUTHORIZED', '').strip()
    preauth_message = os.environ.get('JT_MISSION_PREAUTH_MESSAGE', '在线授权有效')

    html_content = get_mission_planner_html()

    try:
        window = webview.create_window(
            window_title,
            html=html_content,
            js_api=api,
            width=1440,
            height=860,
            min_size=(760, 560),
            resizable=True,
            confirm_close=False,
            text_select=True,
            zoomable=True,
            background_color='#0b1020',
        )
    except TypeError:
        # pywebview 旧版不支持部分参数
        window = webview.create_window(
            window_title,
            html=html_content,
            js_api=api,
            width=1440,
            height=860,
            min_size=(760, 560),
        )

    api.bind_window(window)
    _apply_windows_titlebar_icon_async(window_title)

    def on_loaded():
        _apply_windows_titlebar_icon_async(window_title)

    try:
        window.events.loaded += on_loaded
    except Exception:
        pass

    try:
        if os.name == 'nt':
            webview.start(gui='edgechromium', debug=False)
        else:
            webview.start(debug=False)
    except Exception:
        webview.start(debug=False)

    return 0