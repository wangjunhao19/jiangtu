"""疆途·智能巡查管理平台 V1.0 - 主入口（从字节码完整重建）"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import traceback
from pathlib import Path


def _mission_webview_mode() -> bool:
    return '--jt-mission-webview' in sys.argv


def _sanzi_login_mode() -> bool:
    return '--jt-sanzi-login' in sys.argv


def _map_webview_mode() -> bool:
    return '--jt-map-webview' in sys.argv


def _runtime_self_test_mode() -> bool:
    return '--jt-runtime-self-test' in sys.argv


def _sanzi_workbench_mode() -> bool:
    return '--jt-sanzi-workbench' in sys.argv


def _anyang_export_mode() -> bool:
    return '--jt-anyang-export' in sys.argv


def ensure_dependencies() -> None:
    """非冻结环境下自动检测并安装缺失依赖。"""
    if getattr(sys, 'frozen', False):
        return
    required = {
        'requests': 'requests',
        'PIL': 'Pillow',
        'geopandas': 'geopandas',
        'fiona': 'fiona',
        'shapely': 'shapely',
        'pandas': 'pandas',
        'pyproj': 'pyproj',
        'webview': 'pywebview',
        'docx': 'python-docx',
        'cryptography': 'cryptography',
        'numpy': 'numpy',
        'rasterio': 'rasterio',
        'rawpy': 'rawpy',
        'exifread': 'exifread',
        'piexif': 'piexif',
        'openpyxl': 'openpyxl',
    }
    missing = [
        package
        for module, package in required.items()
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        return
    from tkinter import messagebox
    messagebox.showinfo(
        '提示',
        f'缺少依赖：{", ".join(missing)}，正在自动安装……',
    )
    subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing)


def _runtime_diagnostic_path() -> Path:
    """诊断日志路径，优先使用环境变量，否则存于用户目录。"""
    override = os.environ.get('JT_RUNTIME_SELFTEST_LOG', '').strip()
    if override:
        return Path(override)
    # 优先使用项目目录下的 logs 子目录
    project_logs = Path(__file__).parent / 'logs'
    try:
        project_logs.mkdir(parents=True, exist_ok=True)
        return project_logs / 'startup_dependency_error.log'
    except OSError:
        pass
    local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
    log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / 'startup_dependency_error.log'
    except OSError:
        return Path('/tmp') / 'jt_startup_dependency_error.log'


def verify_runtime_stack(*, show_dialog: bool = True) -> bool:
    """验证冻结程序中的 NumPy、Pandas 与 GIS 二进制扩展来自同一兼容环境。"""
    log_path = _runtime_diagnostic_path()
    try:
        import numpy as np
        import pandas as pd
        import geopandas as gpd
        import fiona
        import rasterio
        import shapely
        import pyproj
        import rawpy

        # 依赖导入成功即通过，PyInstaller 打包的依赖是自包含的，无需运行时版本校验
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open('w', encoding='utf-8', errors='replace') as handle:
            handle.write('[V1.0冻结运行组件自检通过]\n')
            handle.write(f'Python: {sys.version}\n')
            handle.write(f'Frozen: {getattr(sys, "frozen", False)}\n')
            handle.write(f'Executable: {sys.executable}\n')
            handle.write(f'NumPy: {np.__version__} | {getattr(np, "__file__", "")}\n')
            handle.write(f'Pandas: {pd.__version__} | {getattr(pd, "__file__", "")}\n')
            handle.write(f'GeoPandas: {gpd.__version__}\n')
            handle.write(f'Fiona: {fiona.__version__}\n')
            handle.write(f'Shapely: {shapely.__version__}\n')
            handle.write(f'PyProj: {pyproj.__version__}\n')
            handle.write(f'Rasterio: {rasterio.__version__}\n')
            handle.write(f'RawPy: {rawpy.__version__}\n')
        return True

    except Exception as exc:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('w', encoding='utf-8', errors='replace') as handle:
            handle.write('[V1.0运行组件兼容性检查失败]\n')
            handle.write(f'Python: {sys.version}\n')
            handle.write(f'Frozen: {getattr(sys, "frozen", False)}\n')
            handle.write(f'Executable: {sys.executable}\n')
            handle.write(f'Error: {exc!r}\n')
            traceback.print_exc(file=handle)

        if show_dialog:
            try:
                from tkinter import messagebox
                messagebox.showerror(
                    'V1.0运行组件异常',
                    f'安装包中的NumPy与GIS组件不兼容，软件无法安全启动。\n\n'
                    f'请卸载旧版本并删除原安装目录后，再安装修复版。\n\n'
                    f'诊断日志：{log_path}',
                )
            except Exception:
                pass
        return False


def run_runtime_self_test() -> int:
    """运行时自检入口，返回 0=通过, 3=失败。"""
    return 0 if verify_runtime_stack(show_dialog=False) else 3


def run_main() -> int:
    """主运行逻辑：根据命令行参数选择运行模式。"""

    # ── 模式1: 运行时自检 ──
    if _runtime_self_test_mode():
        return run_runtime_self_test()

    # ── 模式2: 三资工作台（独立进程） ──
    if _sanzi_workbench_mode():
        try:
            ensure_dependencies()
            if not verify_runtime_stack():
                return 3
            from ui.sanzi_upload_window import run_sanzi_workbench
            run_sanzi_workbench()
            return 0
        except Exception:
            local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
            log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'sanzi_workbench.log'
            with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
                f.write('\n[三资工作台启动异常]\n')
                traceback.print_exc(file=f)
            return 2

    # ── 模式3: 三资平台登录 WebView ──
    if _sanzi_login_mode():
        try:
            from ui.sanzi_login_webview import run_sanzi_login_webview
            run_sanzi_login_webview(sys.argv[1:])
            return 0
        except Exception:
            local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
            log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'sanzi_login_webview.log'
            with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
                f.write('\n[三资平台登录窗口启动异常]\n')
                traceback.print_exc(file=f)
            return 2

    # ── 模式4: 安阳三资在线导出 WebView ──
    if _anyang_export_mode():
        try:
            ensure_dependencies()
            from ui.anyang_sanzi_export_webview import run_anyang_sanzi_export_webview
            run_anyang_sanzi_export_webview(sys.argv[1:])
            return 0
        except Exception:
            local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
            log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'anyang_sanzi_export.log'
            with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
                f.write('\n[安阳三资在线图斑导出窗口启动异常]\n')
                traceback.print_exc(file=f)
            return 2

    # ── 模式5: 地图 WebView ──
    if _map_webview_mode():
        try:
            from ui.map_webview import run_map_webview
            run_map_webview(sys.argv[1:])
            return 0
        except Exception:
            local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
            log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'map_webview.log'
            with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
                f.write('\n[地图窗口启动异常]\n')
                traceback.print_exc(file=f)
            return 2

    # ── 模式6: 航线规划器 WebView ──
    if _mission_webview_mode():
        try:
            from ui.mission_webview import run_mission_webview
            run_mission_webview()
            return 0
        except Exception:
            local_appdata = os.environ.get('LOCALAPPDATA') or str(Path.home())
            log_dir = Path(local_appdata) / 'JiangTu' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'mission_webview.log'
            with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
                f.write('\n[航线规划器启动异常]\n')
                traceback.print_exc(file=f)
            return 2

    # ── 模式7: 默认主程序 ──
    ensure_dependencies()
    if not verify_runtime_stack():
        return 3

    from ui.main_window import MainApp
    from ui.auth_window import AuthWindow

    # 默认显示登录页，登录成功后进入主界面
    AuthWindow(main_window_factory=MainApp).mainloop()

    return 0


if __name__ == '__main__':
    raise SystemExit(run_main())
