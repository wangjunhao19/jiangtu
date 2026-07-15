import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from utils.ui_icon import apply_window_icon
from services.dji_fly_service import DjiMissionOptions, DRONE_PROFILES, drone_profile_summary, get_drone_profile


class DjiMissionWindow(tk.Toplevel):
    TYPE_MAP = {'图斑正射拍摄': 'asset_photo', '正射网格': 'grid', '沿边巡查': 'edge'}
    TEMPLATE_MAP = {'三资巡查': 'asset', '正射影像': 'orthophoto', '自定义': 'custom'}
    ACTION_MAP = {'拍照': 'photo', '悬停': 'hover', '录像': 'video'}
    ORDER_MAP = {'按图斑编号/名称': 'name', '西 → 东': 'west_east', '南 → 北': 'south_north', '最短路径': 'nearest'}

    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title('航线规划 - DJI Fly / 行业机WPML任务导出')
        self.geometry('1080x760')
        self.minsize(920, 660)
        self.resizable(True, True)
        apply_window_icon(self)
        self.callback = callback
        self.kml_paths = []
        self.output_path = ''
        self.template_param_frames = {}
        self._build_ui()
        self.apply_template()
        self._refresh_takeoff_controls()
        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        self._init_vars()
        container = ttk.Frame(self, padding=8)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)
        self._scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        self._build_file_section(self._scroll_frame)
        self._build_base_section(self._scroll_frame)
        self._build_template_sections(self._scroll_frame)
        self._build_asset_section(self._scroll_frame)
        self._build_ortho_section(self._scroll_frame)
        self._build_custom_section(self._scroll_frame)
        self._build_output_section(self._scroll_frame)
        self._build_help_section(self._scroll_frame)
        self._build_summary_section(self._scroll_frame)

    def _init_vars(self):
        self.kml_var = tk.StringVar(value='未选择图斑KML')
        self.out_var = tk.StringVar(value='未选择，点击底部生成按钮时选择保存文件夹')
        self.name_var = tk.StringVar(value='三资图斑正射拍摄')
        self.drone_var = tk.StringVar(value='Air 3 / Air 3S')
        self.drone_info_var = tk.StringVar(value=drone_profile_summary('Air 3 / Air 3S'))
        self.template_var = tk.StringVar(value='三资巡查')
        self.type_var = tk.StringVar(value='图斑正射拍摄')
        self.height_var = tk.DoubleVar(value=60)
        self.speed_var = tk.DoubleVar(value=10)
        self.gimbal_var = tk.DoubleVar(value=-90)
        self.side_gimbal_var = tk.DoubleVar(value=-90)
        self.action_var = tk.StringVar(value='拍照')
        self.order_var = tk.StringVar(value='最短路径')
        self.spacing_var = tk.DoubleVar(value=25)
        self.margin_var = tk.DoubleVar(value=10)
        self.max_wp_var = tk.IntVar(value=200)
        self.takeoff_height_var = tk.DoubleVar(value=111)
        self.batch_land_count_var = tk.IntVar(value=0)
        self.large_land_threshold_sqm_var = tk.DoubleVar(value=3000)
        self.large_land_spacing_var = tk.DoubleVar(value=45)
        self.max_centers_per_land_var = tk.IntVar(value=10)
        self.front_overlap_var = tk.DoubleVar(value=80)
        self.side_overlap_var = tk.DoubleVar(value=70)
        self.model_overlap_var = tk.DoubleVar(value=85)
        self.orbit_layers_var = tk.IntVar(value=1)
        self.layer_step_var = tk.DoubleVar(value=10)
        self.preview_var = tk.BooleanVar(value=True)
        self.preview_mode_var = tk.StringVar(value='序号+线路')
        self.takeoff_lon_var = tk.StringVar(value='')
        self.takeoff_lat_var = tk.StringVar(value='')

    def _build_file_section(self, parent):
        box = ttk.LabelFrame(parent, text='1. 输入图斑KML')
        box.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, textvariable=self.kml_var, foreground='#333').grid(
            row=0, column=0, columnspan=2, sticky='ew', padx=10, pady=5)
        ttk.Button(box, text='选择KML文件', command=self.choose_kml).grid(
            row=1, column=0, padx=10, pady=5)

    def _build_base_section(self, parent):
        box = ttk.LabelFrame(parent, text='2. 基础飞行参数')
        box.grid(row=1, column=0, sticky='ew', pady=(0, 10))

        self._label(box, 0, 0, '任务名称')
        ttk.Entry(box, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky='ew', padx=5)

        self._label(box, 0, 2, '机型')
        drone_combo = ttk.Combobox(box, textvariable=self.drone_var, state='readonly',
                                    values=list(DRONE_PROFILES.keys()), width=22)
        drone_combo.grid(row=0, column=3, padx=5)
        drone_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_drone_profile())

        ttk.Label(box, textvariable=self.drone_info_var, foreground='#666').grid(
            row=1, column=0, columnspan=4, sticky='w', padx=10, pady=2)

        self._label(box, 2, 0, '模板')
        ttk.Combobox(box, textvariable=self.template_var, state='readonly',
                      values=list(self.TEMPLATE_MAP.keys()), width=16).grid(row=2, column=1, padx=5)

        self._label(box, 2, 2, '类型')
        ttk.Combobox(box, textvariable=self.type_var, state='readonly',
                      values=list(self.TYPE_MAP.keys()), width=16).grid(row=2, column=3, padx=5)

        self._label(box, 3, 0, '飞行高度(m)')
        ttk.Entry(box, textvariable=self.height_var, width=10).grid(row=3, column=1, padx=5)
        self._label(box, 3, 2, '速度(m/s)')
        ttk.Entry(box, textvariable=self.speed_var, width=10).grid(row=3, column=3, padx=5)

        self._label(box, 4, 0, '云台角度')
        ttk.Entry(box, textvariable=self.gimbal_var, width=10).grid(row=4, column=1, padx=5)
        self._label(box, 4, 2, '侧拍云台')
        ttk.Entry(box, textvariable=self.side_gimbal_var, width=10).grid(row=4, column=3, padx=5)

        self._label(box, 5, 0, '动作')
        ttk.Combobox(box, textvariable=self.action_var, state='readonly',
                      values=list(self.ACTION_MAP.keys()), width=12).grid(row=5, column=1, padx=5)
        self._label(box, 5, 2, '排序')
        ttk.Combobox(box, textvariable=self.order_var, state='readonly',
                      values=list(self.ORDER_MAP.keys()), width=14).grid(row=5, column=3, padx=5)

        self._label(box, 6, 0, '间距(m)')
        ttk.Entry(box, textvariable=self.spacing_var, width=10).grid(row=6, column=1, padx=5)
        self._label(box, 6, 2, '外扩(m)')
        ttk.Entry(box, textvariable=self.margin_var, width=10).grid(row=6, column=3, padx=5)

        self._label(box, 7, 0, '最大航点数')
        ttk.Entry(box, textvariable=self.max_wp_var, width=10).grid(row=7, column=1, padx=5)
        self._label(box, 7, 2, '起飞高度(m)')
        ttk.Entry(box, textvariable=self.takeoff_height_var, width=10).grid(row=7, column=3, padx=5)

    def _build_template_sections(self, parent):
        """占位：每个模板的参数调节面板（template_param_frames 字典）"""
        pass

    def _build_asset_section(self, parent):
        box = ttk.LabelFrame(parent, text='3. 三资巡查参数')
        box.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        self._label(box, 0, 0, '批量图斑数')
        ttk.Entry(box, textvariable=self.batch_land_count_var, width=10).grid(row=0, column=1, padx=5)
        self._label(box, 1, 0, '大图斑阈值(m²)')
        ttk.Entry(box, textvariable=self.large_land_threshold_sqm_var, width=10).grid(row=1, column=1, padx=5)
        self._label(box, 1, 2, '大图斑间距(m)')
        ttk.Entry(box, textvariable=self.large_land_spacing_var, width=10).grid(row=1, column=3, padx=5)
        self._label(box, 2, 0, '每图斑最多中心数')
        ttk.Entry(box, textvariable=self.max_centers_per_land_var, width=10).grid(row=2, column=1, padx=5)

    def _build_ortho_section(self, parent):
        box = ttk.LabelFrame(parent, text='4. 正射影像参数')
        box.grid(row=3, column=0, sticky='ew', pady=(0, 10))
        self._label(box, 0, 0, '前向重叠率(%)')
        ttk.Entry(box, textvariable=self.front_overlap_var, width=10).grid(row=0, column=1, padx=5)
        self._label(box, 0, 2, '侧向重叠率(%)')
        ttk.Entry(box, textvariable=self.side_overlap_var, width=10).grid(row=0, column=3, padx=5)
        self._label(box, 1, 0, '模型重叠率(%)')
        ttk.Entry(box, textvariable=self.model_overlap_var, width=10).grid(row=1, column=1, padx=5)
        self._label(box, 1, 2, '环绕层数')
        ttk.Entry(box, textvariable=self.orbit_layers_var, width=10).grid(row=1, column=3, padx=5)
        self._label(box, 2, 0, '层高(m)')
        ttk.Entry(box, textvariable=self.layer_step_var, width=10).grid(row=2, column=1, padx=5)

    def _build_custom_section(self, parent):
        box = ttk.LabelFrame(parent, text='5. 自定义参数（高级）')
        box.grid(row=4, column=0, sticky='ew', pady=(0, 10))
        self._label(box, 0, 0, '起飞点经度')
        ttk.Entry(box, textvariable=self.takeoff_lon_var, width=18).grid(row=0, column=1, padx=5)
        self._label(box, 0, 2, '起飞点纬度')
        ttk.Entry(box, textvariable=self.takeoff_lat_var, width=18).grid(row=0, column=3, padx=5)

    def _build_output_section(self, parent):
        box = ttk.LabelFrame(parent, text='6. 输出设置')
        box.grid(row=5, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(box, textvariable=self.out_var, foreground='#333').grid(
            row=0, column=0, columnspan=2, sticky='ew', padx=10, pady=5)

    def _build_help_section(self, parent):
        box = ttk.LabelFrame(parent, text='说明')
        box.grid(row=6, column=0, sticky='ew', pady=(0, 10))
        help_text = (
            '• 选择KML后可在地图上预览航线\n'
            '• 模板会预设推荐参数，可在上方微调\n'
            '• 大图斑阈值：面积超过此值的图斑使用独立航线策略\n'
            '• 起飞点留空则自动取KML几何中心\n'
            '• 行业机（M30/M300/M350等）会导出WPML格式\n'
            '• 消费级机型导出DJI Fly KMZ格式'
        )
        ttk.Label(box, text=help_text, foreground='#555', justify=tk.LEFT).grid(
            row=0, column=0, sticky='w', padx=10, pady=5)

    def _build_summary_section(self, parent):
        box = ttk.Frame(parent)
        box.grid(row=7, column=0, sticky='ew', pady=(0, 10))

        ttk.Checkbutton(box, text='生成后预览航线', variable=self.preview_var).pack(side=tk.LEFT, padx=10)
        ttk.Label(box, text='预览标注：').pack(side=tk.LEFT)
        ttk.Combobox(box, textvariable=self.preview_mode_var, state='readonly',
                      values=('序号', '线路', '序号+线路'), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(box, text='生成航线任务', command=self.on_confirm).pack(side=tk.RIGHT, padx=10)

    @staticmethod
    def _label(parent, row, col, text):
        ttk.Label(parent, text=text).grid(row=row, column=col, sticky=tk.W, padx=5, pady=3)

    def _is_enterprise_drone(self):
        profile = get_drone_profile(self.drone_var.get())
        if profile:
            return profile.get('enterprise', False)
        return False

    def _refresh_takeoff_controls(self):
        pass  # 根据机型动态显隐起飞点控件

    def apply_drone_profile(self, _event=None):
        name = self.drone_var.get()
        self.drone_info_var.set(drone_profile_summary(name))

    def apply_template(self, _event=None):
        tpl = self.template_var.get()
        if tpl == '三资巡查':
            self.type_var.set('图斑正射拍摄')
            self.height_var.set(60)
            self.speed_var.set(10)
            self.gimbal_var.set(-90)
            self.action_var.set('拍照')
            self.order_var.set('最短路径')
        elif tpl == '正射影像':
            self.type_var.set('正射网格')
            self.height_var.set(80)
            self.speed_var.set(10)
            self.gimbal_var.set(-90)
            self.side_gimbal_var.set(-90)
            self.action_var.set('拍照')
        elif tpl == '自定义':
            pass  # 保持用户当前设置

    def choose_kml(self):
        paths = filedialog.askopenfilenames(
            title='选择图斑KML文件（可多选）',
            filetypes=[('KML/KMZ', '*.kml *.kmz'), ('所有文件', '*.*')],
        )
        if paths:
            self.kml_paths = list(paths)
            names = [os.path.basename(p) for p in self.kml_paths]
            self.kml_var.set(f'已选择 {len(names)} 个文件: {", ".join(names[:3])}{"..." if len(names) > 3 else ""}')

    def choose_output(self):
        folder = filedialog.askdirectory(title='选择航线任务输出目录')
        if folder:
            self.output_path = folder
            self.out_var.set(folder)

    def build_options(self) -> DjiMissionOptions:
        tpl = self.template_var.get()
        height = float(self.height_var.get())
        speed = float(self.speed_var.get())
        gimbal = float(self.gimbal_var.get())
        side_gimbal = float(self.side_gimbal_var.get())
        spacing = float(self.spacing_var.get())
        margin = float(self.margin_var.get())
        front_overlap = float(self.front_overlap_var.get())
        side_overlap = float(self.side_overlap_var.get())
        large_land_threshold_sqm = float(self.large_land_threshold_sqm_var.get())
        large_land_spacing = float(self.large_land_spacing_var.get())
        max_centers_per_land = min(10, max(1, int(self.max_centers_per_land_var.get())))
        max_waypoints = int(self.max_wp_var.get())
        takeoff_security_height = float(self.takeoff_height_var.get())

        takeoff_lon = self.takeoff_lon_var.get().strip()
        takeoff_lat = self.takeoff_lat_var.get().strip()
        takeoff_lon_value = float(takeoff_lon) if takeoff_lon else None
        takeoff_lat_value = float(takeoff_lat) if takeoff_lat else None

        if (takeoff_lon_value is None) ^ (takeoff_lat_value is None):
            raise ValueError('起飞点经纬度需要同时填写，或都留空')
        if takeoff_lon_value is not None:
            if not (-180 <= takeoff_lon_value <= 180) or not (-90 <= takeoff_lat_value <= 90):
                raise ValueError('起飞点经纬度范围不正确')

        if tpl == '正射影像':
            gimbal = -90
            side_gimbal = -90
            self.action_var.set('拍照')

        if height <= 0 or height > 500:
            raise ValueError('飞行高度需在 0-500 米之间')
        if takeoff_security_height <= 0 or takeoff_security_height > 500:
            raise ValueError('起飞安全高度需在 0-500 米之间')
        if speed <= 0 or speed > 15:
            raise ValueError('飞行速度需在 0-15 m/s 之间')
        if not (0 <= front_overlap <= 95) or not (0 <= side_overlap <= 95):
            raise ValueError('正射重叠率需在 0-95% 之间')
        if gimbal < -90 or gimbal > 30 or side_gimbal < -90 or side_gimbal > 30:
            raise ValueError('云台角度建议在 -90 到 30 度之间')
        if large_land_threshold_sqm <= 0 or large_land_spacing <= 0:
            raise ValueError('大图斑参数必须大于0')
        if spacing <= 0:
            raise ValueError('间距必须大于0')
        if max_waypoints != 0 and max_waypoints < 2:
            raise ValueError('单文件航点数至少为2，或填0表示不分割')

        preview_mode_map = {'序号': 'point', '线路': 'line', '序号+线路': 'both'}

        mission_type = 'asset_photo' if tpl == '三资巡查' else self.TYPE_MAP.get(self.type_var.get(), 'edge')
        terrain_follow = False

        return DjiMissionOptions(**{
            'mission_name': self.name_var.get().strip() or '图斑自动航线',
            'mission_type': mission_type,
            'mission_template': self.TEMPLATE_MAP.get(tpl, 'custom'),
            'height': height,
            'speed': speed,
            'gimbal_pitch': gimbal,
            'side_gimbal_pitch': side_gimbal,
            'action': self.ACTION_MAP.get(self.action_var.get(), 'photo'),
            'order': self.ORDER_MAP.get(self.order_var.get(), 'south_north'),
            'edge_spacing': spacing,
            'margin': margin,
            'max_waypoints': max_waypoints,
            'batch_land_count': 0,
            'preview_mode': preview_mode_map.get(self.preview_mode_var.get(), 'both'),
            'large_land_multi_points': True,
            'large_land_threshold_sqm': large_land_threshold_sqm,
            'large_land_spacing': large_land_spacing,
            'max_centers_per_land': max_centers_per_land,
            'drone_model': self.drone_var.get(),
            'front_overlap': front_overlap,
            'side_overlap': side_overlap,
            'model_overlap': float(self.model_overlap_var.get()),
            'orbit_layers': 1,
            'layer_height_step': float(self.layer_step_var.get()),
            'terrain_follow': terrain_follow,
            'takeoff_security_height': takeoff_security_height,
            'takeoff_lon': takeoff_lon_value,
            'takeoff_lat': takeoff_lat_value,
        })

    def on_confirm(self):
        try:
            if not self.kml_paths:
                raise ValueError('请先选择图斑KML')
            if not self.output_path:
                self.choose_output()
                if not self.output_path:
                    return
            options = self.build_options()
            self.callback(self.kml_paths, self.output_path, options, self.preview_var.get())
        except Exception as e:
            messagebox.showerror('参数错误', str(e))


import os  # noqa: E402 (used by choose_kml)
