from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from pathlib import Path

_WINDOW_ICON_HANDLES: list[int] = []


def resource_path(filename: str) -> Path:
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
            return candidate
    return candidates[0] if candidates else Path(filename)


def _find_windows_by_title(title_text: str) -> list[int]:
    """Find native windows whose title equals or contains the requested text.

    WebView2 may append renderer text to the visible title, so exact FindWindowW
    alone is not reliable on all Windows builds.
    """
    if os.name != 'nt':
        return []
    user32 = ctypes.windll.user32
    matches = []
    wanted = str(title_text or '').strip().lower()

    exact = user32.FindWindowW(None, title_text)
    if exact:
        matches.append(int(exact))

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            current = buf.value.strip().lower()
            if wanted and (wanted == current or wanted in current):
                value = int(hwnd)
                if value not in matches:
                    matches.append(value)
        except Exception:
            pass
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return matches


def apply_windows_titlebar_icon(window_title: str) -> bool:
    if os.name != 'nt':
        return False
    icon_path = resource_path('logo.ico')
    if not icon_path.exists():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = (
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        )
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = (
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p,
        )
        user32.SendMessageW.restype = ctypes.c_ssize_t
        hwnds = _find_windows_by_title(window_title)
        if not hwnds:
            return False
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 16
        WM_SETICON = 128
        ICON_SMALL = 0
        ICON_BIG = 1
        big_icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        small_icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not big_icon and not small_icon:
            return False
        for hwnd in hwnds:
            if big_icon:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_icon)
            if small_icon:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
        if big_icon:
            _WINDOW_ICON_HANDLES.append(int(big_icon))
        if small_icon:
            _WINDOW_ICON_HANDLES.append(int(small_icon))
        return True
    except Exception:
        return False


def apply_windows_titlebar_icon_async(window_title: str) -> None:
    if os.name != 'nt':
        return None

    def worker() -> None:
        success_count = 0
        for _ in range(90):
            if apply_windows_titlebar_icon(window_title):
                success_count += 1
                if success_count >= 4:
                    return None
            time.sleep(0.2)

    threading.Thread(target=worker, daemon=True, name='jt-webview-icon').start()
