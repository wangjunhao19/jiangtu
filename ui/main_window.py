# Source Generated with Decompyle++
# File: main_window.pyc (Python 3.11)
# Reconstructed from pycdas bytecode disassembly

import os
import sys
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime
from typing import List
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from config import APP_NAME, COMPANY_NAME, COMPANY_TEL, TIANDITU_KEY
from models.image_info import ImageInfo
from services.har_service import parse_har_classified_to_kml, parse_har_work_to_kml
from services.image_service import ImageCache, read_img_gps, convert_dng_folder_to_jpg
from services.kml_service import export_points_kml
from services.emg_kml_service import batch_convert_emg_to_kml
from services.license_service import (
    BASE_MODULE, MISSION_MODULE,
    check_license_file, check_mission_license_file,
    check_local_module_access, check_online_license_now,
    authorize_formal_action, get_machine_code,
)
from services.map_service import generate_map_html
from services.rename_service import batch_rename
from services.watermark_service import WatermarkOptions, add_watermark_to_image
from services.land_photo_service import export_land_centers, organize_photos_by_land, rename_photos_by_land
from services.dji_fly_service import DjiMissionOptions, export_dji_fly_kmz, export_mission_preview_kml
from ui.watermark_window import WatermarkSettingsWindow
from ui.ai_image_classification_window import AIImageClassificationWindow
from ui.dji_mission_window import DjiMissionWindow
from ui.mission_auth_window import MissionAuthWindow
from services.sanzi_upload_service import delete_field_photos, export_upload_log, upload_photo_groups
from services.update_service import check_for_update, download_update, get_current_version
from utils.file_utils import open_file
from utils.thread_bus import UiBus
from utils.ui_icon import apply_window_icon


class MainApp(tk.Tk):
    """疆途·智能巡查管理平台主窗口"""

    # ==================== 字体配置（macOS 系统优化）====================
    # 使用系统自带高可读性字体，确保深色模式下清晰显示
    _FONT_TITLE = ('-apple-system', 20, 'bold')      # 品牌标题
    _FONT_NAV   = ('-apple-system', 11)               # 导航按钮
    _FONT_BODY  = ('-apple-system', 13)               # 正文（增大字号提升可读性）
    _FONT_LABEL = ('-apple-system', 10)               # 标签文字
    _FONT_SMALL = ('-apple-system', 9)                # 小字说明
    _FONT_CODE  = ('Menlo', 10)                       # 等宽字体（日志区域）
    _FONT_BOLD  = ('-apple-system', 13, 'bold')       # 粗体强调

    # ------------------------------------------------------------------ init
    def __init__(self):
        super().__init__()
        self.title(f'{APP_NAME} - {COMPANY_NAME}')
        self.geometry('1200x850')
        self.resizable(True, True)
        self._set_app_icon()

        self.working = False
        self._task_started_at = 0
        self.cache = ImageCache()
        self.folder_path = ''
        self.img_list: List[ImageInfo] = []
        self.gps_points: list = []
        self.tdt_key = TIANDITU_KEY
        self.bus = UiBus()
        self.include_subdirs_var = tk.BooleanVar(value=True)
        self.rename_include_subdirs_var = tk.BooleanVar(value=False)
        self._auto_update_prompted = False

        self._build_ui()
        self.after(100, self._poll_bus)

        if getattr(sys, 'frozen', False):
            self.after(2200, self._auto_check_update)

    # -------------------------------------------------------- resource_path
    def _resource_path(self, relative_path):
        """兼容源码运行和 PyInstaller 打包后的资源路径。"""
        base_path = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)
        return str(Path(base_path) / relative_path)

    # -------------------------------------------------------- icon helpers
    def _set_app_icon(self):
        apply_window_icon(self)

    def _set_child_icon(self, window):
        apply_window_icon(window)

    # ------------------------------------------------------------ _build_ui
    def _build_ui(self):
        # 样式
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # ==================== 配色方案（中性深灰主题 - OLED优化）====================
        # 基于长时间使用友好原则：纯中性深灰 + 绿色状态指示 + 无蓝色倾向
        _BG       = '#121212'   # background (深灰，比纯黑更柔和)
        _BG_LIGHT = '#1E1E1E'   # card / surface-container-low (卡片底色)
        _PRIMARY  = '#4CAF50'   # primary (清新绿色，清晰但不刺眼)
        _ON_VAR   = '#A0A0A0'   # on-surface-variant (中灰，降低视觉疲劳)
        _BORDER   = '#333333'   # border / surface-container-high (低对比度边框)
        _HOVER    = '#262626'   # hover / surface-container (悬停背景)
        _ACTIVE_BG = '#383838'  # active item background (激活项背景)
        _ON_SURFACE = '#F8FAFC' # 主文字色

        self.configure(bg=_BG)

        # ==================== 顶部导航栏 ====================
        top_nav = tk.Frame(self, bg=_BG, height=72)
        top_nav.pack(fill=tk.X)
        top_nav.pack_propagate(False)

        # 底部渐变分割线（模拟 border-b border-white/10）
        tk.Frame(self, bg=_BORDER, height=1).pack(fill=tk.X)

        # 品牌标题（左侧）——"疆途 · 智能巡查"
        brand_frame = tk.Frame(top_nav, bg=_BG)
        brand_frame.pack(side=tk.LEFT, padx=(22, 12), pady=10)
        tk.Label(brand_frame, text='疆途', bg=_BG, fg=_PRIMARY,
                 font=self._FONT_TITLE).pack(side=tk.LEFT)
        tk.Label(brand_frame, text=' · 智能巡查', bg=_BG, fg=_PRIMARY,
                 font=self._FONT_LABEL).pack(side=tk.LEFT, padx=(4, 0))

        # 分隔线（竖向）
        tk.Frame(top_nav, bg=_BORDER, width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=16)

        # 导航按钮（中间水平排列）—— 扁平文字按钮风格
        nav_items = [
            ('dashboard', '首页', self._show_dashboard),
            ('photo_manage', '照片管理', self._show_photo_page),
            ('ai_classify', 'AI分类', self._show_ai_page),
            ('land_data', '图斑管理', self._show_land_page),
            ('map_view', '地图预览', self._show_map_page),
            ('mission_plan', '航线规划', self._show_mission_page),
            ('sanzi_upload', '三资平台', self._show_sanzi_page),
            ('settings', '设置', self._show_settings_page),
        ]

        self.nav_buttons: dict = {}
        self._nav_colors = {
            'bg': _BG, 'fg': _ON_VAR, 'active_fg': _PRIMARY,
            'hover_bg': _HOVER, 'active_bg': _ACTIVE_BG,
        }
        for key, text, cmd in nav_items:
            b = tk.Label(top_nav, text=text, bg=_BG, fg=_ON_VAR,
                         font=self._FONT_NAV, padx=12, pady=6,
                         cursor='hand2')
            b.pack(side=tk.LEFT, padx=2, pady=18)
            b.bind('<Button-1>', lambda e, c=cmd, k=key: c())
            # 悬停效果
            b.bind('<Enter>', lambda e, w=b: w.configure(bg=_HOVER))
            b.bind('<Leave>', lambda e, w=b, k2=key: w.configure(
                bg=self._nav_colors['active_bg'] if k2 == getattr(self, '_active_nav', '') else _BG))
            self.nav_buttons[key] = b

        # 右侧信息区 —— 授权状态 + 用户标识
        right_frame = tk.Frame(top_nav, bg=_BG)
        right_frame.pack(side=tk.RIGHT, padx=18)

        ok, info, _ = check_license_file()
        self.license_status_var = tk.StringVar(value=info)
        _status_color = '#47e266' if ok else '#ffb4ab'  # tertiary / error
        self._license_label = tk.Label(right_frame, textvariable=self.license_status_var,
                 bg=_BG, fg=_status_color,
                 font=self._FONT_SMALL)
        self._license_label.pack(side=tk.LEFT, padx=(0, 16))

        # ==================== 内容区域（深色主题）====================
        self._BG       = _BG
        self._BG_LIGHT = _BG_LIGHT
        self._PRIMARY  = _PRIMARY
        self._ON_VAR   = _ON_VAR
        self._BORDER   = _BORDER
        _ON_SURFACE    = '#F8FAFC'

        self.content = tk.Frame(self, bg=_BG, padx=24, pady=20)
        self.content.pack(fill=tk.BOTH, expand=True)

        # 页面字典
        self.pages: dict = {}

        # 头部区域
        self.header = tk.Frame(self.content, bg=_BG)
        self.header.pack(fill=tk.X, pady=(0, 8))

        tk.Label(self.header, text=APP_NAME, bg=_BG, fg=_ON_SURFACE,
                 font=('-apple-system', 18, 'bold')).pack(side=tk.LEFT)

        # 主体区域
        self.body = tk.Frame(self.content, bg=_BG)
        self.body.pack(fill=tk.BOTH, expand=True)

        # 进度条行
        progress_row = tk.Frame(self.content, bg=_BG)
        progress_row.pack(fill=tk.X, pady=(8, 4))

        self.progress = ttk.Progressbar(progress_row, mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.task_progress_text_var = tk.StringVar(value='就绪')
        tk.Label(progress_row, textvariable=self.task_progress_text_var,
                 bg=_BG, fg=_ON_VAR,
                 font=self._FONT_SMALL, width=34, anchor='e').pack(side=tk.RIGHT, padx=(10, 0))

        # 日志
        tk.Label(self.content, text='运行日志：', bg=_BG, fg=_ON_VAR,
                 font=self._FONT_SMALL).pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(
            self.content, height=8,
            bg='#262626', fg='#A0A0A0', insertbackground=_PRIMARY,
            font=('Consolas', 9), relief=tk.FLAT,
            highlightbackground=_BORDER, highlightthickness=1)
        self.log_text.pack(fill=tk.BOTH, expand=False, pady=(4, 0))

        # 默认显示卡片式仪表盘
        self._show_dashboard()

    # -------------------------------------------------------- nav helpers
    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _set_nav_active(self, key):
        """设置导航按钮的激活状态 — 玻璃拟态深色主题"""
        c = self._nav_colors
        self._active_nav = key
        for k, b in self.nav_buttons.items():
            if k == key:
                # 选中：蓝色文字 + 微亮背景（模拟 primary border-b 指示条）
                b.configure(bg=c['active_bg'], fg=c['active_fg'])
            else:
                # 未选中：灰蓝文字 + 深色背景
                b.configure(bg=c['bg'], fg=c['fg'])

    def _title(self, parent, title, subtitle=''):
        tk.Label(parent, text=title, bg=self._BG, fg='#F8FAFC',
                 font=('-apple-system', 16, 'bold')).pack(anchor=tk.W, pady=(0, 4))
        if subtitle:
            tk.Label(parent, text=subtitle, bg=self._BG, fg=self._ON_VAR,
                     font=self._FONT_LABEL, wraplength=820,
                     justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 14))

    def _card(self, parent, title, desc, buttons):
        card = tk.Frame(parent, bg=self._BG_LIGHT,
                        highlightbackground=self._BORDER, highlightthickness=1)
        card.pack(fill=tk.X, pady=8)

        title_lbl = tk.Label(card, text=title, bg=self._BG_LIGHT, fg='#F8FAFC',
                             font=('-apple-system', 12, 'bold'), anchor='w')
        title_lbl.pack(fill=tk.X, padx=14, pady=(12, 4))

        if desc:
            tk.Label(card, text=desc, bg=self._BG_LIGHT, fg=self._ON_VAR,
                     font=self._FONT_SMALL, wraplength=860, justify=tk.LEFT,
                     anchor='w').pack(fill=tk.X, padx=14, pady=(0, 8))

        if buttons:
            row = tk.Frame(card, bg=self._BG_LIGHT)
            row.pack(anchor=tk.W, padx=14, pady=(0, 12))
            for text, cmd in buttons:
                btn = tk.Label(row, text=text, bg='#383838', fg='#F8FAFC',
                               font=self._FONT_LABEL, padx=14, pady=6,
                               cursor='hand2')
                btn.pack(side=tk.LEFT, padx=(0, 8))
                btn.bind('<Button-1>', lambda e, c=cmd: c())
                btn.bind('<Enter>', lambda e, w=btn: w.configure(bg='#475569'))
                btn.bind('<Leave>', lambda e, w=btn: w.configure(bg='#383838'))
        return card

    # ========================================================== page methods

    def _show_dashboard(self):
        """Bento 网格仪表盘首页（深色玻璃拟态）"""
        self._set_nav_active('dashboard')
        self._clear_body()

        _BG       = self._BG
        _BG_LIGHT = self._BG_LIGHT
        _PRIMARY  = self._PRIMARY
        _ON_VAR   = self._ON_VAR
        _BORDER   = self._BORDER
        _ON_SURFACE = '#F8FAFC'
        _GLASS_BG = '#1B2336'   # glass card bg
        _FIELD_BG = '#1E293B'

        # ── 可滚动容器 ──────────────────────────────────────────
        canvas = tk.Canvas(self.body, bg=_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.body, orient='vertical', command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=_BG)
        scroll_frame.bind('<Configure>',
                          lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        _cw = canvas.create_window((0, 0), window=scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Canvas 宽度变化时同步内部 Frame 宽度
        def _on_canvas_configure(event):
            canvas.itemconfig(_cw, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)

        # 鼠标滚轮支持（macOS + Windows/Linux）
        def _on_mousewheel(event):
            # Canvas 销毁后忽略事件，避免 TclError
            if not canvas.winfo_exists():
                return
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            elif event.num == 4:
                canvas.yview_scroll(-1, 'units')
            elif event.num == 5:
                canvas.yview_scroll(1, 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        canvas.bind_all('<Button-4>', _on_mousewheel)
        canvas.bind_all('<Button-5>', _on_mousewheel)

        #  Bento Grid: 3行 × 2列统一布局 ────────────────────────
        grid_frame = tk.Frame(scroll_frame, bg=_BG)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置 3 行 2 列，所有单元格等宽等高
        for i in range(3):
            grid_frame.rowconfigure(i, weight=1, minsize=180)
        for j in range(2):
            grid_frame.columnconfigure(j, weight=1)

        # 第一行
        self._glass_card(grid_frame, '照片导入与管理',
                         '支持批量导入巡查航拍图片，自动提取EXIF位置信息并关联任务。',
                         '',
                         self._show_photo_page, _PRIMARY, (0, 0))

        self._glass_card(grid_frame, '图斑数据处理',
                         '集成GIS引擎，实时处理矢量图斑与遥感影像对比，识别用地变化趋势。',
                         '',
                         self._show_land_page, '#c2c1ff', (0, 1))

        # ── Bento Grid: 第二行 ──────────────────────────────────
        #  Bento Grid: 第二行（2列）────────────────────────────
        # 第二行
        self._glass_card(grid_frame, 'AI 图片分类归档',
                         '自研轻量化深度学习模型，智能识别违章建筑、裸露土地、水体污染等12类场景。',
                         '',
                         self._show_ai_page, '#47e266', (1, 0))

        self._glass_card(grid_frame, '地图预览',
                         '基于3D数字生底座，可视化呈现巡查轨迹、风险点位与资源分布。',
                         '',
                         self._show_map_page, _PRIMARY, (1, 1))

        # ── Bento Grid: 第三行（2列）────────────────────────────
        # 第三行
        self._glass_card(grid_frame, 'DJI 航线生成器',
                         '一键规划大疆无人机自动巡航路径，优化重叠率，适配多种飞行环境。',
                         '',
                         self._show_mission_page, '#6cff82', (2, 0))

        self._glass_card(grid_frame, '三资材料工作台',
                         '快速跳转至农村集体资金、资产、资源管理核心模块。',
                         '',
                         self._show_sanzi_page, '#4b8eff', (2, 1))

    def _glass_card(self, parent, title, desc, status_text, command, accent_color, pos):
        """创建深色玻璃拟态 Bento 卡片
        
        Args:
            pos: tuple (row, col) 网格位置
        """
        _GLASS_BG = '#1E1E1E'   # card background
        _BORDER   = '#333333'   # border
        _HOVER_BG = '#262626'   # hover state
        _ON_VAR   = '#A0A0A0'   # secondary text
        _ON_SURFACE = '#F8FAFC' # primary text

        row, col = pos
        card = tk.Frame(parent, bg=_GLASS_BG,
                        highlightbackground=_BORDER, highlightthickness=1)
        card.grid(row=row, column=col, sticky='nsew', padx=6, pady=6)

        # 标题 + 描述
        tk.Label(card, text=title, bg=_GLASS_BG, fg=_ON_SURFACE,
                 font=('-apple-system', 15, 'bold'), anchor='w').pack(
                     fill=tk.X, padx=20, pady=(14, 6))
        tk.Label(card, text=desc, bg=_GLASS_BG, fg=_ON_VAR,
                 font=self._FONT_SMALL, anchor='w', wraplength=280,
                 justify=tk.LEFT).pack(fill=tk.X, padx=20, pady=(0, 10))

        # 点击事件 + 悬停效果
        def _bind_all(widget):
            widget.bind('<Button-1>', lambda e: command())
            widget.bind('<Enter>', lambda e, c=card: c.configure(
                bg=_HOVER_BG, highlightbackground=accent_color))
            widget.bind('<Leave>', lambda e, c=card: c.configure(
                bg=_GLASS_BG, highlightbackground=_BORDER))
            for child in widget.winfo_children():
                _bind_all(child)
        _bind_all(card)

    def _glass_settings_card(self, parent, bg, border, primary, on_var, on_surface):
        """系统设置卡片（左侧宽卡）"""
        card = tk.Frame(parent, bg=bg,
                        highlightbackground=border, highlightthickness=1)
        card.grid(row=0, column=0, sticky='nsew', padx=6, pady=6)

        head = tk.Frame(card, bg=bg)
        head.pack(fill=tk.X, padx=20, pady=(18, 10))
        tk.Label(head, text='系统设置', bg=bg, fg=primary,
                 font=('-apple-system', 14, 'bold')).pack(side=tk.LEFT)

    def _glass_status_card(self, parent, bg, border, primary, on_var, on_surface):
        """系统状态卡片（右侧窄卡）"""
        card = tk.Frame(parent, bg=bg,
                        highlightbackground=border, highlightthickness=1)
        card.grid(row=0, column=1, sticky='nsew', padx=6, pady=6)

        tk.Label(card, text='系统状态', bg=bg, fg=primary,
                 font=('-apple-system', 14, 'bold')).pack(
                     anchor='w', padx=20, pady=(18, 10))

        info_frame = tk.Frame(card, bg=bg)
        info_frame.pack(fill=tk.X, padx=20, pady=(0, 18))

        tk.Label(info_frame, text=f'版本: V{get_current_version()}',
                 bg=bg, fg=on_var,
                 font=self._FONT_SMALL).pack(anchor='w', pady=2)

    def _show_project_page(self):
        """项目页 (deprecated alias → photo page)"""
        self._show_photo_page()

    def _show_photo_page(self):
        self._set_nav_active('photo_manage')
        self._clear_body()
        self._title(self.body, '图片管理',
                    '照片目录、按KML图斑整理、批量重命名、照片点位KML和水印模板。')

        _BG       = self._BG
        _BG_LIGHT = self._BG_LIGHT
        _PRIMARY  = self._PRIMARY
        _ON_VAR   = self._ON_VAR
        _BORDER   = self._BORDER

        # ── 照片目录 ──
        folder_frame = tk.Frame(self.body, bg=_BG_LIGHT,
                                highlightbackground=_BORDER, highlightthickness=1)
        folder_frame.pack(fill=tk.X, pady=8)

        tk.Label(folder_frame, text='照片目录', bg=_BG_LIGHT, fg='#F8FAFC',
                 font=('-apple-system', 12, 'bold'), anchor='w').pack(
                     fill=tk.X, padx=14, pady=(12, 4))

        grid = tk.Frame(folder_frame, bg=_BG_LIGHT)
        grid.pack(fill=tk.X, padx=14, pady=(0, 6))

        tk.Label(grid, text='图片目录：', bg=_BG_LIGHT, fg=_ON_VAR,
                 font=self._FONT_LABEL).grid(row=0, column=0, sticky=tk.W, pady=4)

        self.folder_var = tk.StringVar(value=self.folder_path)
        tk.Entry(grid, textvariable=self.folder_var,
                 bg='#262626', fg='#F8FAFC', insertbackground=_PRIMARY,
                 font=self._FONT_LABEL, relief=tk.FLAT,
                 highlightbackground=_BORDER, highlightthickness=1,
                 highlightcolor=_PRIMARY).grid(row=0, column=1, sticky=tk.EW, padx=6)

        self.btn_load = tk.Label(grid, text='选择并加载图片',
                                  bg='#383838', fg='#F8FAFC',
                                  font=self._FONT_LABEL, padx=14, pady=6,
                                  cursor='hand2')
        self.btn_load.grid(row=0, column=2, padx=(6, 0))
        self.btn_load.bind('<Button-1>', lambda e: self.load_images())
        self.btn_load.bind('<Enter>', lambda e: self.btn_load.configure(bg='#475569'))
        self.btn_load.bind('<Leave>', lambda e: self.btn_load.configure(bg='#383838'))
        grid.columnconfigure(1, weight=1)

        tk.Checkbutton(grid, text='加载照片包含子文件夹',
                       variable=self.include_subdirs_var,
                       bg=_BG_LIGHT, fg=_ON_VAR, selectcolor='#262626',
                       activebackground=_BG_LIGHT, activeforeground='#F8FAFC',
                       font=self._FONT_SMALL).grid(
            row=1, column=1, sticky=tk.W, padx=6, pady=(8, 4))

        # 重命名行
        rename_frame = tk.Frame(grid, bg=_BG_LIGHT)
        rename_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(4, 12))

        tk.Label(rename_frame, text='起始编号：', bg=_BG_LIGHT, fg=_ON_VAR,
                 font=self._FONT_LABEL).pack(side=tk.LEFT)

        self.rename_var = tk.StringVar(
            value=getattr(self, 'rename_var', tk.StringVar(value='A1')).get()
            if hasattr(self, 'rename_var') else 'A1')
        tk.Entry(rename_frame, textvariable=self.rename_var, width=18,
                 bg='#262626', fg='#F8FAFC', insertbackground=_PRIMARY,
                 font=self._FONT_LABEL, relief=tk.FLAT,
                 highlightbackground=_BORDER, highlightthickness=1,
                 highlightcolor=_PRIMARY).pack(side=tk.LEFT, padx=6)

        tk.Checkbutton(rename_frame, text='重命名包含子文件夹',
                       variable=self.rename_include_subdirs_var,
                       bg=_BG_LIGHT, fg=_ON_VAR, selectcolor='#262626',
                       activebackground=_BG_LIGHT, activeforeground='#F8FAFC',
                       font=self._FONT_SMALL).pack(side=tk.LEFT, padx=6)
        rn_btn = tk.Label(rename_frame, text='原地批量重命名',
                           bg='#383838', fg='#F8FAFC',
                           font=self._FONT_LABEL, padx=14, pady=6,
                           cursor='hand2')
        rn_btn.pack(side=tk.LEFT, padx=6)
        rn_btn.bind('<Button-1>', lambda e: self.do_rename())
        rn_btn.bind('<Enter>', lambda e: rn_btn.configure(bg='#475569'))
        rn_btn.bind('<Leave>', lambda e: rn_btn.configure(bg='#383838'))

        # ── 照片成果 ──
        self._card(self.body, '照片成果',
                   '导出照片点位KML、按图斑整理照片、添加照片水印、按图斑编号重命名照片，或把无人机DNG原片批量转换为JPG。',
                   [
                       ('导出照片KML点位', self.export_kml),
                       ('根据KML图斑整理照片', self.organize_photos_ui),
                       ('照片水印模板', self.open_watermark_settings),
                       ('按图斑重命名照片', self.rename_photos_by_land_ui),
                       ('DNG批量转JPG', self.convert_dng_to_jpg_ui),
                   ])

    def _show_ai_page(self):
        self._set_nav_active('ai_classify')
        self._clear_body()
        self._title(self.body, 'AI图片智能归档',
                    '用户自行建立训练类别，模型在本机学习；批量照片可自动识别类别、读取GPS与拍摄时间、'
                    '空间匹配图斑编号，并按自定义文件名、水印和文件夹模板输出。')

        self._card(self.body, 'AI图片智能归档中心',
                   '支持三种本地识别方法；训练文件夹名称即类别名称。可设置低置信度待确认、图斑边界容差、'
                   '图斑编号字段，以及 {图斑号}、{类别}、{村名}、{日期} 等模板变量。原始照片不会被修改。',
                   [('打开AI图片智能归档中心', self.open_ai_image_window)])

        self._card(self.body, '推荐流程',
                   '第一步：按类别建立训练文件夹并训练模型；第二步：选择照片与图斑文件；'
                   '第三步：设置分类文件名、分类文件夹和水印模板；第四步：批量输出照片与CSV/Excel处理清单。',
                   [])

    def _show_land_page(self):
        self._set_nav_active('land_data')
        self._clear_body()
        self._title(self.body, '图斑管理',
                    '图斑导出功能已按使用频率集中排列；图斑中心点单独放置，减少按钮分散和重复说明。')

        self._card(self.body, '图斑导出',
                   '按常用顺序使用：HAR解析工作图斑用于导出工作进度三状态；HAR分类导出用于按工作进度、'
                   '使用状态一张图、整改专题和问题整改分类；安阳在线导出仅适用于能够访问安阳三资内网的客户电脑；'
                   'EMG转KML用于转换EMD/EMG图斑数据。',
                   [
                       ('HAR解析工作图斑', self.parse_har_files),
                       ('HAR分类导出', self.parse_all_har_files),
                       ('打开安阳三资在线导出', self.open_anyang_sanzi_export_window),
                       ('EMG转KML', self.convert_emg_to_kml_ui),
                   ])

        self._card(self.body, '图斑中心点',
                   '从图斑KML导出中心点KML/TXT，供地图检查或航线规划使用。',
                   [('导出图斑中心点', self.export_land_centers_ui)])

    def _show_map_page(self):
        self._set_nav_active('map_view')
        self._clear_body()
        self._title(self.body, '地图管理',
                    '打开软件内地图叠加图斑、照片、航线和中心点；可直接加载照片文件夹，点击照片预览并复制原文件。')

        self._card(self.body, '地图与KML预览',
                   '支持直接加载照片文件夹、照片预览与复制原文件、KML图层和多种在线底图叠加预览。',
                   [('打开地图', self.open_gps_map),
                    ('设置天地图密钥', self.set_tdt_key)])

    def _show_mission_page(self):
        self._set_nav_active('mission_plan')
        self._clear_body()
        self._title(self.body, '航线规划',
                    'V1.0航线规划：支持KML/KMZ导入、虚线切割航线、'
                    '端点连接、禁飞区导入导出、Ctrl+Z撤回和KMZ批量导出。')

        ok, msg, _ = check_local_module_access(MISSION_MODULE)
        status = '已开通' if ok else '待授权'

        self._card(self.body, f'航线规划器（{status}）',
                   msg + '\n\n功能：统一导入 KML/KMZ；支持最短距离与优化交叉规划、虚线穿越切割、'
                   '起终点突出连接、图斑移动、Ctrl+Z撤回、禁飞区导入导出及 KMZ 一键批量导出。',
                   [('打开新航线规划器', self.open_dji_mission_window)])

    def _show_sanzi_page(self):
        self._set_nav_active('sanzi_upload')
        self._clear_body()
        self._title(self.body, '三资材料工作台',
                    '单界面完成：登录同步、自定义三种证明模板、按新吸附规则整理照片、检查后一键上传。')

        self._card(self.body, '三资平台只读同步与材料归档',
                   '功能：官方网页人工验证码登录、只读同步图斑/合同/付款/附件数据、'
                   '情况证明/飞地证明/村委会证明模板、按GPS两阶段吸附整理现场照片、'
                   '容错识别材料名称并一键上传。',
                   [('打开三资材料工作台', self.open_sanzi_upload_window)])

        self._card(self.body, '安全边界',
                   'V1.0不修改地块基本信息，不新增或挂接合同，不新增付款，'
                   '不提交、不撤回、不审核；仅执行只读查询和用户确认后的附件上传。',
                   [])

    def _show_settings_page(self):
        self._set_nav_active('settings')
        self._clear_body()
        self._title(self.body, '功能说明',
                    '围绕图斑巡查、AI图片分类、照片整理、地图预览、航线规划和三资平台上传提供一体化工具。')

        self._card(self.body, '软件信息',
                   f'软件名称：{APP_NAME}\n服务单位：{COMPANY_NAME}\n联系电话：{COMPANY_TEL}',
                   [('检查更新', self.check_update_ui),
                    ('刷新授权状态', self.reload_license_file)])

        self._card(self.body, '主要功能',
                   '图片管理：加载照片、按KML图斑整理、批量重命名、制作水印、导出照片点位。\n'
                   '图斑与地图：解析HAR、导出图斑及中心点，在地图中叠加查看图斑、照片和航线。\n'
                   '航线规划：支持三资巡查、正射测绘、倾斜摄影、手动航点、禁飞区避让、任务切割、'
                   '全部机型逐航点仿地与DJI KMZ导出。\n'
                   '三资材料：官方网页人工验证码登录，只读同步平台数据，生成待核实签章的Word材料，'
                   '按规范名称扫描归档并上传附件。\n'
                   '授权说明：继续使用现有在线授权与航线权限；V1.0服务器增加安装包版本、大小和SHA256'
                   '发布信息，用于软件内安全更新。',
                   [])

        self._card(self.body, '使用提示',
                   '使用航线规划、地图底图、三资平台同步、附件上传和检查更新时，请保持网络连接正常。'
                   '三资登录失效后重新登录，再次上传会自动跳过平台同名附件。',
                   [])

    # ====================================================== AI image window
    def open_ai_image_window(self):
        try:
            window = getattr(self, '_ai_image_window', None)
            if window is not None and window.winfo_exists():
                window.deiconify()
                window.lift()
                window.focus_force()
                return
        except Exception:
            pass
        self._ai_image_window = AIImageClassificationWindow(self)

    # ====================================================== update system
    def _auto_check_update(self):
        if self._auto_update_prompted or not self.winfo_exists():
            return

        def prompt(result):
            if self._auto_update_prompted or not self.winfo_exists():
                return
            self._auto_update_prompted = True
            text = (f'检测到新版本 V{result.latest_version}。\n'
                    f'当前版本：V{result.current_version}\n\n'
                    f'更新内容：\n{result.update_log or "优化软件稳定性与使用体验。"}\n\n')
            if result.force_update:
                text += '该版本已设置为必须更新。\n\n'
            if not result.download_url:
                messagebox.showinfo('发现新版本',
                                    text + '服务器尚未上传安装包，请稍后在\'功能说明—检查更新\'中重试。',
                                    parent=self)
                return
            if messagebox.askyesno('发现新版本', text + '是否现在下载并安装？', parent=self):
                self._download_and_install_update(result)

        def worker():
            try:
                result = check_for_update(timeout=8)
            except Exception:
                return
            if result.success and result.has_update:
                self.after(0, lambda: prompt(result))

        threading.Thread(target=worker, name='jt-auto-update-check', daemon=True).start()

    def check_update_ui(self):
        """打开检查更新对话框"""
        dialog = tk.Toplevel(self)
        dialog.title('检查更新')
        dialog.geometry('600x330')
        dialog.minsize(560, 310)
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()
        self._set_child_icon(dialog)
        dialog.configure(bg='#eef4fb')

        # 卡片容器
        card = tk.Frame(dialog, bg='white', highlightbackground='#d9e5f2',
                        highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        # 头部色块
        head = tk.Frame(card, bg='#0f5fa8', height=72)
        head.pack(fill=tk.X)
        title_box = tk.Frame(head, bg='#0f5fa8')
        title_box.pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(title_box, text='↻', bg='#0f5fa8', fg='white',
                 font=('微软雅黑', 27, 'bold')).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(title_box, text='软件更新中心', bg='#0f5fa8', fg='white',
                 font=('微软雅黑', 16, 'bold')).pack(anchor='w', pady=(13, 0))

        # 主体
        body = tk.Frame(card, bg='white')
        body.pack(fill=tk.BOTH, expand=True)

        status = tk.StringVar(value='正在连接疆途更新服务器……')
        detail = tk.StringVar(value='请保持网络连接，通常几秒内即可完成。')

        tk.Label(body, textvariable=status, bg='#d9edff', fg='#173b63',
                 font=('微软雅黑', 12, 'bold'), anchor='w').pack(fill=tk.X, pady=(7, 0))
        tk.Label(body, textvariable=detail, bg='#d9edff', fg='#66788a',
                 font=('微软雅黑', 9), anchor='w', justify=tk.LEFT,
                 wraplength=530).pack(fill=tk.X, pady=(0, 13))

        bar = ttk.Progressbar(body, mode='indeterminate')
        bar.pack(fill=tk.X, padx=22, pady=(0, 10))
        bar.start(10)

        tk.Label(body, text=f'当前版本：V{get_current_version()}',
                 bg='white', fg='#7a8795', font=('微软雅黑', 9),
                 anchor='w').pack(fill=tk.X, padx=10)

        # 底部按钮
        actions = tk.Frame(body, bg='#f7faff', height=50)
        actions.pack(fill=tk.X, side=tk.BOTTOM)

        close_btn = ttk.Button(actions, text='关闭', command=dialog.destroy)
        close_btn.pack(side=tk.RIGHT, padx=(8, 18), pady=(10, 0))

        retry_btn = ttk.Button(actions, text='重新检查', state=tk.DISABLED)
        retry_btn.pack(side=tk.RIGHT, pady=(10, 0))

        # 状态管理
        state = {'serial': 0, 'finished': False}

        def set_running():
            state['serial'] += 1
            serial = state['serial']
            state['finished'] = False
            status.set('正在连接疆途更新服务器……')
            detail.set('正在核对版本信息。若主线路不可用，软件会自动尝试备用接口。')
            bar.configure(mode='indeterminate', value=0)
            bar.start(10)
            retry_btn.configure(text='重新检查', state=tk.DISABLED, command=None)

            def timeout_guard():
                if not dialog.winfo_exists() or state['serial'] != serial or state['finished']:
                    return
                state['finished'] = True
                bar.stop()
                status.set('检查超时，但软件其他功能不受影响')
                detail.set('更新服务器响应时间过长。请确认网络后点击"重新检查"，不再出现无提示、无反应的情况。')
                retry_btn.configure(state=tk.NORMAL)

            def finish_result(serial, result):
                if not dialog.winfo_exists() or state['serial'] != serial:
                    return
                state['finished'] = True
                bar.stop()
                if result.success:
                    if result.has_update:
                        status.set(f'发现新版本 V{result.latest_version}')
                        detail.set(result.update_log or '优化软件稳定性与使用体验。')
                    else:
                        status.set('当前已是最新版本')
                        detail.set('')
                else:
                    status.set('检查失败')
                    detail.set(result.message if hasattr(result, 'message') else '请检查网络后重试。')
                retry_btn.configure(text='重新检查', state=tk.NORMAL, command=set_running)

            def finish_error(serial, exc):
                if not dialog.winfo_exists() or state['serial'] != serial:
                    return
                state['finished'] = True
                bar.stop()
                status.set('检查失败')
                detail.set(str(exc))
                retry_btn.configure(text='重新检查', state=tk.NORMAL, command=set_running)

            def worker():
                try:
                    result = check_for_update(timeout=10)
                    self.after(0, lambda r=result: finish_result(serial, r))
                except Exception as exc:
                    self.after(0, lambda e=exc: finish_error(serial, e))

            dialog.after(22000, timeout_guard)
            threading.Thread(target=worker, name=f'jt-update-check-{serial}', daemon=True).start()

        retry_btn.configure(command=set_running)
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        set_running()

    def _download_and_install_update(self, result):
        """下载并安装更新"""
        dialog = tk.Toplevel(self)
        dialog.title(f'正在下载 V{result.latest_version}')
        dialog.geometry('500x200')
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        self._set_child_icon(dialog)

        status = tk.StringVar(value='正在下载……')
        detail = tk.StringVar(value='')
        bar = ttk.Progressbar(dialog, mode='determinate')
        bar.pack(fill=tk.X, padx=20, pady=(20, 10))

        tk.Label(dialog, textvariable=status).pack()
        tk.Label(dialog, textvariable=detail, fg='#666').pack()

        def worker():
            try:
                local_path = download_update(
                    result.download_url,
                    target_dir=tempfile.gettempdir(),
                    latest_version=result.latest_version,
                    progress_callback=lambda done, total: self.after(0, lambda d=done, t=total: _update_progress(d, t)),
                    expected_sha256=result.download_sha256 or '',
                    expected_size=result.download_size or 0,
                )
                self.after(0, lambda: _on_done(local_path))
            except Exception as exc:
                self.after(0, lambda e=exc: _on_error(e))

        def _update_progress(done, total):
            if total > 0:
                bar['maximum'] = total
                bar['value'] = done
                pct = done * 100 // total
                status.set(f'正在下载…… {pct}%')
            else:
                status.set('正在下载……')

        def _on_done(local_path):
            status.set('下载完成，正在启动安装程序……')
            dialog.destroy()
            try:
                subprocess.Popen([local_path], shell=True)
                self.destroy()
            except Exception as exc:
                messagebox.showerror('安装失败', str(exc), parent=self)

        def _on_error(exc):
            status.set('下载失败')
            detail.set(str(exc))
            ttk.Button(dialog, text='关闭', command=dialog.destroy).pack(pady=10)

        threading.Thread(target=worker, daemon=True).start()

    # ====================================================== project folder
    def create_project_folder(self):
        base = filedialog.askdirectory(title='选择项目根目录', parent=self)
        if not base:
            return
        name = simpledialog.askstring('新建项目文件夹', '请输入文件夹名称：', parent=self)
        if not name:
            return
        target = os.path.join(base, name.strip())
        os.makedirs(target, exist_ok=True)
        messagebox.showinfo('完成', f'已创建：{target}', parent=self)

    # ====================================================== license
    def reload_license_file(self):
        if self.working:
            messagebox.showinfo('提示', '请等待当前任务完成', parent=self)
            return
        # 重新读取授权文件并刷新状态
        ok, info, _ = check_license_file()
        self.license_status_var.set(info)
        _sc = '#47e266' if ok else '#ffb4ab'
        self._license_label.configure(fg=_sc)
        # 弹出授权详情对话框
        dialog = tk.Toplevel(self)
        dialog.title('授权状态')
        dialog.geometry('520x400')
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        self._set_child_icon(dialog)

        tk.Label(dialog, text='授权状态详情', font=('微软雅黑', 14, 'bold')).pack(pady=(15, 5))
        tk.Label(dialog, text=f'状态：{info}',
                 fg='#087f23' if ok else '#b00020').pack(pady=5)

        # 在线授权检查
        ok2, msg2, _ = check_online_license_now()
        tk.Label(dialog, text=f'在线校验：{msg2}').pack(pady=5)

        # 机器码
        mc = get_machine_code()
        tk.Label(dialog, text=f'机器码：{mc}', wraplength=480).pack(pady=5)

        # 模块权限
        ok_m, msg_m, _ = check_local_module_access(MISSION_MODULE)
        tk.Label(dialog, text=f'航线模块：{msg_m}').pack(pady=5)

        ttk.Button(dialog, text='关闭', command=dialog.destroy).pack(pady=15)

    def _require_formal_authorization(self, action):
        """要求正式授权才能执行某操作"""
        ok, message, _data = authorize_formal_action()
        if not ok:
            messagebox.showerror('授权失败', message, parent=self)
            return False
        return True

    # ====================================================== bus / threading
    def _poll_bus(self):
        try:
            if self.winfo_exists():
                self.bus.drain(self._handle_bus_message)
                self.after(100, self._poll_bus)
        except tk.TclError:
            pass

    def _handle_bus_message(self, kind, payload):
        if kind == 'log':
            self.log(str(payload))
        elif kind == 'progress':
            try:
                data = payload or {}
                maximum = data.get('maximum')
                value = data.get('value')
                if maximum is not None:
                    self.progress['maximum'] = maximum
                if value is not None:
                    self.progress['value'] = value

                done = float(value or 0)
                total = float(maximum or self.progress['maximum'] or 0)
                pct = 100 * done / total if total > 0 else 0

                elapsed = max(0, __import__('time').time() - (self._task_started_at or __import__('time').time()))
                eta = elapsed / done * (total - done) if done > 0 and total > done else 0

                if eta >= 3600:
                    eta_text = f'{int(eta // 3600)}小时{int(eta % 3600 // 60):02d}分'
                elif eta >= 60:
                    eta_text = f'{int(eta // 60)}分{int(eta % 60):02d}秒'
                else:
                    eta_text = f'{int(eta)}秒'

                suffix = f' · 预计剩余 {eta_text}' if eta > 0 else ''
                self.task_progress_text_var.set(f'{pct:.0f}%{suffix}')
            except Exception:
                pass
        elif kind == 'info':
            title, msg = payload
            messagebox.showinfo(title, msg)
        elif kind == 'error':
            title, msg = payload
            messagebox.showerror(title, msg)
        elif kind == 'done':
            self.working = False
            self.progress['value'] = 0
            self.task_progress_text_var.set('就绪')
            if hasattr(self, 'btn_load'):
                self._safe_widget_config('btn_load', state=tk.NORMAL)

    def _safe_widget_config(self, widget_name, **kwargs):
        widget = getattr(self, widget_name, None)
        try:
            if widget is not None and widget.winfo_exists():
                widget.config(**kwargs)
        except tk.TclError:
            pass

    # ====================================================== log
    def log(self, msg):
        self.log_text.insert(tk.END, f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}\n')
        self.log_text.see(tk.END)

    # ====================================================== tdt key
    def set_tdt_key(self):
        key = simpledialog.askstring('输入天地图密钥', '请输入天地图 Web 访问密钥：',
                                     initialvalue=self.tdt_key)
        if key:
            self.tdt_key = key.strip()

    # ====================================================== task runner
    def _run_task(self, target, *args):
        if self.working:
            messagebox.showwarning('提示', '当前有任务正在执行，请等待完成')
            return False
        self.working = True
        self._task_started_at = __import__('time').time()
        self.task_progress_text_var.set('正在准备任务……')
        threading.Thread(target=target, args=args, daemon=True).start()
        return True

    # ====================================================== DNG → JPG
    def convert_dng_to_jpg_ui(self):
        if self.working:
            messagebox.showwarning('提示', '当前有任务正在执行，请等待完成')
            return
        source = filedialog.askdirectory(title='选择DNG照片总目录', parent=self)
        if not source:
            return
        output = filedialog.askdirectory(title='选择JPG输出目录',
                                         initialdir=str(Path(source).parent), parent=self)
        if not output:
            return
        quality = simpledialog.askinteger('JPG质量', '请输入JPG质量（推荐95）：',
                                          initialvalue=95, minvalue=70, maxvalue=100, parent=self)
        if quality is None:
            return
        self._run_task(self._convert_dng_to_jpg_worker, source, output, int(quality))

    def _convert_dng_to_jpg_worker(self, source, output, quality):
        try:
            self.bus.log(f'开始DNG转JPG：{source}')
            result = convert_dng_folder_to_jpg(
                source, output,
                include_subdirs=True, quality=quality, overwrite=False,
                progress=lambda done, total: self.bus.progress(done, total))
            self.bus.log(f'DNG转JPG完成：成功{len(result["converted"])}，'
                         f'跳过{len(result["skipped"])}，失败{len(result["failed"])}')
            self.bus.info('DNG转JPG完成',
                          f'成功：{len(result["converted"])}\n跳过：{len(result["skipped"])}\n'
                          f'失败：{len(result["failed"])}\n输出目录：{output}')
        except Exception as exc:
            self.bus.log(f'DNG转JPG失败：{exc}')
            self.bus.error('DNG转JPG失败', str(exc))
        self.bus.done()

    # ====================================================== load images
    @staticmethod
    def _list_image_files(folder, include_subdirs):
        """列出目录中的图片文件"""
        exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.dng', '.cr2', '.nef', '.arw'}
        results = []
        if include_subdirs:
            for root, _, files in os.walk(folder):
                for f in sorted(files):
                    if Path(f).suffix.lower() in exts:
                        results.append(os.path.join(root, f))
        else:
            for f in sorted(os.listdir(folder)):
                if Path(f).suffix.lower() in exts:
                    results.append(os.path.join(folder, f))
        return results

    def load_images(self):
        folder = filedialog.askdirectory(title='选择照片文件夹', parent=self)
        if not folder:
            return
        self.folder_path = folder
        self.folder_var.set(folder)
        include_subdirs = self.include_subdirs_var.get()
        self._run_task(self._load_images_worker, folder, include_subdirs)

    def _load_images_worker(self, folder, include_subdirs):
        try:
            files = self._list_image_files(folder, include_subdirs)
            total = len(files)
            self.bus.log(f'发现 {total} 个图片文件')
            images = []
            gps_points = []
            for i, f in enumerate(files):
                try:
                    info = read_img_gps(f)
                    images.append(info)
                    if info and info.lon and info.lat:
                        gps_points.append((info.lon, info.lat))
                except Exception:
                    pass
                if (i + 1) % 50 == 0 or i + 1 == total:
                    self.bus.progress(i + 1, total)
            self.img_list = images
            self.gps_points = gps_points
            self.cache = ImageCache()
            self.bus.log(f'加载完成：{len(images)} 张图片，{len(gps_points)} 个含GPS坐标')
            self.bus.info('加载完成', f'共加载 {len(images)} 张图片\n其中 {len(gps_points)} 张含GPS坐标')
        except Exception as exc:
            self.bus.log(f'加载失败：{exc}')
            self.bus.error('加载失败', str(exc))
        self.bus.done()

    # ====================================================== rename
    def do_rename(self):
        if not self.img_list:
            messagebox.showwarning('提示', '请先加载图片')
            return
        start_name = self.rename_var.get().strip()
        include_subdirs = self.rename_include_subdirs_var.get()
        self._run_task(self._do_rename_worker, start_name, include_subdirs)

    def _do_rename_worker(self, start_name, include_subdirs):
        try:
            folder = self.folder_path
            count = batch_rename(folder, start_name, include_subdirs)
            self.bus.log(f'重命名完成：成功 {count} 个')
            self.bus.info('重命名完成', f'成功重命名 {count} 个文件')
        except Exception as exc:
            self.bus.error('重命名失败', str(exc))
        self.bus.done()

    def _reload_current_folder_after_rename(self):
        if self.folder_path:
            self.load_images()

    # ====================================================== export
    def export_txt(self):
        if not self.gps_points:
            messagebox.showwarning('提示', '没有可用的GPS点位数据')
            return
        path = filedialog.asksaveasfilename(
            title='导出TXT', defaultextension='.txt',
            filetypes=[('Text', '*.txt')], parent=self)
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for lon, lat in self.gps_points:
                    f.write(f'{lon},{lat}\n')
            self.log(f'已导出TXT：{path}')
            messagebox.showinfo('完成', f'已导出 {len(self.gps_points)} 个点位')
        except Exception as exc:
            messagebox.showerror('导出失败', str(exc))

    def export_kml(self):
        if not self.img_list:
            messagebox.showwarning('提示', '请先加载图片')
            return
        path = filedialog.asksaveasfilename(
            title='导出照片点位KML', defaultextension='.kml',
            filetypes=[('KML', '*.kml')], parent=self)
        if not path:
            return
        try:
            export_points_kml(self.img_list, path)
            self.log(f'已导出KML：{path}')
            messagebox.showinfo('完成', f'已导出 {len(self.img_list)} 个照片点位')
        except Exception as exc:
            messagebox.showerror('导出失败', str(exc))

    # ====================================================== GPS map
    def open_gps_map(self):
        self._run_task(self._open_gps_map_worker)

    def _open_gps_map_worker(self):
        try:
            html_path = generate_map_html(
                points=self.gps_points,
                tdt_key=self.tdt_key)
            self.bus.log(f'地图已生成：{html_path}')
            open_file(html_path)
        except Exception as exc:
            self.bus.error('地图打开失败', str(exc))
        self.bus.done()

    # ====================================================== watermark
    def open_watermark_settings(self):
        def callback(opts: WatermarkOptions, output_folder: str):
            self._run_task(self._batch_add_watermark_worker, opts, output_folder)

        WatermarkSettingsWindow(self, callback=callback)

    def batch_add_watermark(self, opts: WatermarkOptions, output_folder: str):
        self._run_task(self._batch_add_watermark_worker, opts, output_folder)

    def _batch_add_watermark_worker(self, opts, output_folder):
        try:
            if not self.img_list:
                self.bus.error('水印处理', '请先加载图片')
                self.bus.done()
                return
            total = len(self.img_list)
            self.bus.log(f'开始添加水印，共 {total} 张图片')
            success = 0
            for i, img_info in enumerate(self.img_list):
                try:
                    add_watermark_to_image(img_info.path, output_folder, opts)
                    success += 1
                except Exception:
                    pass
                self.bus.progress(i + 1, total)
            self.bus.log(f'水印处理完成：成功 {success}/{total}')
            self.bus.info('水印处理完成', f'成功：{success}/{total}\n输出目录：{output_folder}')
        except Exception as exc:
            self.bus.error('水印处理失败', str(exc))
        self.bus.done()

    # ====================================================== land photo
    def export_land_centers_ui(self):
        kml_path = filedialog.askopenfilename(
            title='选择图斑KML文件', filetypes=[('KML/KMZ', '*.kml *.kmz')], parent=self)
        if not kml_path:
            return
        output = filedialog.asksaveasfilename(
            title='导出中心点KML', defaultextension='.kml',
            filetypes=[('KML', '*.kml'), ('TXT', '*.txt')], parent=self)
        if not output:
            return
        self._run_task(self._export_land_centers_worker, kml_path, output)

    def _export_land_centers_worker(self, kml_path, output):
        try:
            count = export_land_centers([kml_path], output)
            self.bus.log(f'图斑中心点导出完成：{count} 个')
            self.bus.info('导出完成', f'已导出 {count} 个图斑中心点')
        except Exception as exc:
            self.bus.error('导出失败', str(exc))
        self.bus.done()

    def organize_photos_ui(self):
        if not self.img_list:
            messagebox.showwarning('提示', '请先加载图片')
            return
        kml_path = filedialog.askopenfilename(
            title='选择图斑KML文件', filetypes=[('KML/KMZ', '*.kml *.kmz')], parent=self)
        if not kml_path:
            return
        distance = self._ask_photo_match_distance()
        if distance is None:
            return
        self._run_task(self._organize_photos_worker, kml_path, distance)

    def _ask_photo_match_distance(self):
        val = simpledialog.askfloat('照片匹配距离', '请输入照片与图斑的最大匹配距离（米）：',
                                    initialvalue=50.0, minvalue=1.0, maxvalue=5000.0, parent=self)
        return val

    def _organize_photos_worker(self, kml_path, distance):
        try:
            output_dir = self.folder_path or '.'
            result = organize_photos_by_land(
                self.img_list, [kml_path], output_dir,
                match_distance_m=distance)
            unmatched = result.get('未匹配图斑', 0)
            matched = sum(v for k, v in result.items() if k != '未匹配图斑')
            self.bus.log(f'照片整理完成：匹配 {matched} 张，未匹配 {unmatched} 张')
            self.bus.info('整理完成', f'匹配：{matched} 张\n'
                          f'未匹配：{unmatched} 张')
        except Exception as exc:
            self.bus.error('照片整理失败', str(exc))
        self.bus.done()

    def rename_photos_by_land_ui(self):
        if not self.img_list:
            messagebox.showwarning('提示', '请先加载图片')
            return
        kml_path = filedialog.askopenfilename(
            title='选择图斑KML文件', filetypes=[('KML/KMZ', '*.kml *.kmz')], parent=self)
        if not kml_path:
            return
        self._run_task(self._rename_photos_by_land_worker, kml_path)

    def _rename_photos_by_land_worker(self, kml_path):
        try:
            output_dir = self.folder_path or '.'
            result = rename_photos_by_land(
                self.img_list, [kml_path], output_dir,
                progress=lambda done, total: self.bus.progress(done, total))
            total = sum(result.values())
            self.bus.log(f'按图斑重命名完成：共 {total} 个')
            self.bus.info('重命名完成', f'共处理：{total} 个')
        except Exception as exc:
            self.bus.error('重命名失败', str(exc))
        self.bus.done()

    # ====================================================== DJI mission
    def open_dji_mission_window(self):
        # 检查航线模块授权
        ok, msg, _ = check_local_module_access(MISSION_MODULE)
        if not ok:
            auth_win = MissionAuthWindow(self)
            self.wait_window(auth_win)
            if not auth_win.granted:
                return

        def on_confirm(kml_paths=None, output_path=None, opts=None, preview=False):
            """接收 DjiMissionWindow 的 4 个回调参数。"""
            if opts is None:
                opts = DjiMissionOptions()
            if kml_paths:
                opts.kml_paths = list(kml_paths) if not isinstance(kml_paths, list) else kml_paths
            if output_path:
                opts.output_target = str(output_path)
            self._run_task(self._generate_dji_mission_worker, opts)

        DjiMissionWindow(self, callback=on_confirm)

    def generate_dji_mission(self, opts: DjiMissionOptions):
        self._run_task(self._generate_dji_mission_worker, opts)

    def _generate_dji_mission_worker(self, opts):
        try:
            self.bus.log('开始生成航线……')
            kmz_path = export_dji_fly_kmz(options=opts)
            self.bus.log(f'航线KMZ已生成：{kmz_path}')
            # 同时生成预览KML
            try:
                preview = export_mission_preview_kml(options=opts)
                self.bus.log(f'预览KML已生成：{preview}')
            except Exception:
                pass
            self.bus.info('航线生成完成', f'KMZ文件：{kmz_path}')
        except Exception as exc:
            self.bus.error('航线生成失败', str(exc))
        self.bus.done()

    # ====================================================== sanzi (三资)
    def open_anyang_sanzi_export_window(self):
        """打开安阳三资在线导出 (webview 独立进程)"""
        output = filedialog.askdirectory(title='选择安阳导出输出目录', parent=self)
        if not output:
            return
        try:
            subprocess.Popen([
                sys.executable, 'main.py',
                '--jt-anyang-export',
                '--output-dir', output,
            ], cwd=str(Path(__file__).resolve().parent.parent))
        except Exception as exc:
            messagebox.showerror('启动失败', str(exc), parent=self)

    def open_sanzi_upload_window(self):
        """打开三资材料上传工作台"""
        try:
            from ui.sanzi_upload_window import SanziUploadWindow
            SanziUploadWindow(self)
        except Exception as exc:
            messagebox.showwarning('提示', f'三资工作台打开失败：{exc}', parent=self)

    def start_sanzi_upload(self):
        self._run_task(self._sanzi_upload_worker)

    def start_sanzi_delete(self):
        self._run_task(self._sanzi_delete_worker)

    def _sanzi_upload_worker(self):
        try:
            self.bus.log('开始三资附件上传……')
            result = upload_photo_groups(
                progress=lambda done, total, msg: self.bus.progress(done, total))
            self.bus.log(f'上传完成：成功 {result.get("uploaded", 0)} 个')
            self.bus.info('上传完成', f'成功：{result.get("uploaded", 0)} 个\n'
                          f'跳过：{result.get("skipped", 0)} 个')
        except Exception as exc:
            self.bus.error('上传失败', str(exc))
        self.bus.done()

    def _sanzi_delete_worker(self):
        try:
            self.bus.log('开始删除现场照片……')
            result = delete_field_photos(
                progress=lambda done, total: self.bus.progress(done, total))
            self.bus.log(f'删除完成：{result.get("deleted", 0)} 个')
            self.bus.info('删除完成', f'已删除 {result.get("deleted", 0)} 个附件')
        except Exception as exc:
            self.bus.error('删除失败', str(exc))
        self.bus.done()

    # ====================================================== EMG → KML
    def convert_emg_to_kml_ui(self):
        folder = filedialog.askdirectory(title='选择EMG/EMD文件目录', parent=self)
        if not folder:
            return
        output = filedialog.askdirectory(title='选择KML输出目录', parent=self)
        if not output:
            return
        self._run_task(self._convert_emg_to_kml_worker, folder, output)

    def _convert_emg_to_kml_worker(self, folder, output):
        try:
            self.bus.log(f'开始EMG转KML：{folder}')
            from pathlib import Path as _Path
            emg_files = list(_Path(folder).glob('*.emg'))
            result = batch_convert_emg_to_kml(
                emg_files, output,
                progress=lambda done, total: self.bus.progress(done, total))
            success_count = len(result.get('success', []))
            fail_count = len(result.get('failed', []))
            self.bus.log(f'EMG转KML完成：成功 {success_count} 个，失败 {fail_count} 个')
            self.bus.info('转换完成', f'成功：{success_count} 个\n失败：{fail_count} 个')
        except Exception as exc:
            self.bus.error('转换失败', str(exc))
        self.bus.done()

    # ====================================================== HAR parsing
    def parse_har_files(self):
        self._parse_har_files_common('work')

    def parse_all_har_files(self):
        self._parse_har_files_common('classified')

    def _parse_har_files_common(self, mode):
        files = filedialog.askopenfilenames(
            title='选择HAR文件', filetypes=[('HAR', '*.har')], parent=self)
        if not files:
            return
        output = filedialog.askdirectory(title='选择KML输出目录', parent=self)
        if not output:
            return
        self._run_task(self._parse_har_worker, list(files), output, mode)

    def _parse_har_worker(self, files, output, mode):
        try:
            total = len(files)
            self.bus.log(f'开始解析 {total} 个HAR文件')
            for i, f in enumerate(files):
                try:
                    if mode == 'work':
                        parse_har_work_to_kml(f, output)
                    else:
                        parse_har_classified_to_kml(f, output)
                except Exception as e:
                    self.bus.log(f'解析失败 {Path(f).name}: {e}')
                self.bus.progress(i + 1, total)
            self.bus.log(f'HAR解析完成：{total} 个文件')
            self.bus.info('解析完成', f'已处理 {total} 个HAR文件\n输出目录：{output}')
        except Exception as exc:
            self.bus.error('HAR解析失败', str(exc))
        self.bus.done()
