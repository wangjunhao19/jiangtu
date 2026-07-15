# -*- mode: python ; coding: utf-8 -*-
"""
疆途·智能巡查管理平台 V1.0 - PyInstaller 打包配置
使用方法: pyinstaller build.spec
"""
import os
import sys
from pathlib import Path

block_cipher = None
BASE = os.path.abspath('.')

a = Analysis(
    ['main.py'],
    pathex=[BASE],
    binaries=[],
    datas=[
        ('logo.ico', '.'),
        ('logo.png', '.'),
        ('resources', 'resources'),
    ],
    hiddenimports=[
        # ─ 核心业务模块 ──
        'config',
        'models',
        'models.image_info',
        # ── services ──
        'services',
        'services.ai_image_classifier_service',
        'services.client_integrity_service',
        'services.dji_fly_service',
        'services.emg_kml_service',
        'services.geocode_service',
        'services.har_service',
        'services.image_service',
        'services.kml_service',
        'services.land_photo_service',
        'services.license_service',
        'services.local_dem_service',
        'services.map_service',
        'services.mission_fingerprint_service',
        'services.output_trace_service',
        'services.platform_geometry_service',
        'services.rename_service',
        'services.sanzi_document_service',
        'services.sanzi_photo_service',
        'services.sanzi_project_check_service',
        'services.sanzi_rules',
        'services.sanzi_upload_service',
        'services.terrain_profile_service',
        'services.update_service',
        'services.watermark_service',
        # ── ui ──
        'ui',
        'ui.ai_image_classification_window',
        'ui.anyang_sanzi_export_webview',
        'ui.auth_window',
        'ui.dji_mission_window',
        'ui.main_window',
        'ui.map_webview',
        'ui.mission_auth_window',
        'ui.mission_webview',
        'ui.sanzi_login_webview',
        'ui.sanzi_upload_window',
        'ui.watermark_window',
        # ── utils ──
        'utils',
        'utils.file_utils',
        'utils.thread_bus',
        'utils.ui_icon',
        'utils.webview_icon',
        # ── 第三方依赖 (PyInstaller 常漏掉的) ──
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        # GIS
        'geopandas',
        'fiona',
        'fiona.env',
        'fiona._env',
        'shapely',
        'shapely.geometry',
        'shapely.ops',
        'pyproj',
        'pyproj.crs',
        'pyproj.database',
        'rasterio',
        'rasterio.crs',
        'rasterio.transform',
        'rasterio.warp',
        # 数据处理
        'numpy',
        'numpy.core',
        'pandas',
        'pandas.io',
        'openpyxl',
        # 文档
        'docx',
        'docx.opc',
        'docx.oxml',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        # 图像
        'PIL',
        'PIL.Image',
        'PIL.ExifTags',
        'rawpy',
        'exifread',
        'piexif',
        # 安全
        'cryptography',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        # GUI / WebView
        'webview',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'tkinter.simpledialog',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # 使用目录模式（非单文件）
    name='疆途·智能巡查管理平台V1.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,             # Windows GUI 程序，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='疆途·智能巡查管理平台V1.0',
)
