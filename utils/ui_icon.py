# Source Generated with Decompyle++
# File: ui_icon.pyc (Python 3.11)

from __future__ import annotations
import sys
import tkinter as tk
from pathlib import Path
from typing import Any
_ICON_IMAGES: 'list[Any]' = []

def _resource_candidates(filename = None):
    values = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        values.append(Path(meipass) / filename)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        values.extend((exe_dir / filename, exe_dir / '_internal' / filename))
    values.extend((Path(__file__).resolve().parent.parent / filename, Path.cwd() / filename))
    return values


def _first_existing(filename = None):
    for path in _resource_candidates(filename):
        if path.is_file():
            return None, path
    return None


def apply_window_icon(window = None):
    '''Apply the new-airspace logo to Tk/Toplevel windows.

    macOS / Linux 环境下跳过图标设置（不影响功能）。
    '''
    try:
        result = _first_existing('logo.ico')
        if result is not None:
            _, icon_path = result
            window.iconbitmap(str(icon_path))
    except Exception:
        pass
    try:
        result = _first_existing('logo.png')
        if result is not None:
            _, icon_path = result
            icon = tk.PhotoImage(file=str(icon_path))
            _ICON_IMAGES.append(icon)
            window.iconphoto(True, icon)
    except Exception:
        pass

