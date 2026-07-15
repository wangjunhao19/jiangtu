import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from services.watermark_service import WatermarkOptions
from utils.ui_icon import apply_window_icon


class WatermarkSettingsWindow(tk.Toplevel):

    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title('自定义水印设计')
        self.geometry('540x630')
        self.resizable(False, False)
        apply_window_icon(self)
        self.callback = callback

        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        # --- Tk 变量 ---
        self.center_enabled = tk.BooleanVar(value=True)
        self.center_text = tk.StringVar(value='现场拍照')
        self.center_ratio = tk.DoubleVar(value=0.1)
        self.center_opacity = tk.DoubleVar(value=0.7)
        self.center_color = tk.StringVar(value='#646464')
        self.center_stroke = tk.StringVar(value='#ffffff')

        self.left_enabled = tk.BooleanVar(value=True)
        self.left_size = tk.IntVar(value=80)
        self.left_color = tk.StringVar(value='#ffffff')
        self.left_stroke = tk.StringVar(value='#000000')
        self.left_stroke_width = tk.IntVar(value=1)

        self.include_lonlat = tk.BooleanVar(value=True)
        self.include_address = tk.BooleanVar(value=False)
        self.include_time = tk.BooleanVar(value=True)
        self.include_filename = tk.BooleanVar(value=False)

        # ===== 中央水印 =====
        center = ttk.LabelFrame(root, text='中央水印')
        center.pack(fill=tk.X, pady=6)

        ttk.Checkbutton(center, text='启用中央水印', variable=self.center_enabled).grid(
            row=0, column=0, sticky=tk.W, padx=8, pady=5)

        ttk.Label(center, text='文字').grid(row=1, column=0, sticky=tk.W, padx=8)
        ttk.Entry(center, textvariable=self.center_text, width=30).grid(
            row=1, column=1, columnspan=3, sticky=tk.W, pady=3)

        ttk.Label(center, text='大小比例').grid(row=2, column=0, sticky=tk.W, padx=8)
        ttk.Entry(center, textvariable=self.center_ratio, width=8).grid(row=2, column=1, sticky=tk.W)

        ttk.Label(center, text='透明度').grid(row=2, column=2, sticky=tk.W)
        ttk.Entry(center, textvariable=self.center_opacity, width=8).grid(row=2, column=3, sticky=tk.W)

        self._color_row(center, 3, '字体颜色', self.center_color, '描边颜色', self.center_stroke)

        # ===== 左下角信息水印 =====
        left = ttk.LabelFrame(root, text='左下角信息水印')
        left.pack(fill=tk.X, pady=6)

        ttk.Checkbutton(left, text='启用左下角水印', variable=self.left_enabled).grid(
            row=0, column=0, sticky=tk.W, padx=8, pady=5)
        ttk.Checkbutton(left, text='文件名', variable=self.include_filename).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(left, text='经纬度', variable=self.include_lonlat).grid(row=0, column=2, sticky=tk.W)
        ttk.Checkbutton(left, text='时间', variable=self.include_time).grid(row=0, column=3, sticky=tk.W)

        ttk.Label(left, text='文件名默认不选择；勾选后显示在左下角信息水印中。', foreground='#666').grid(
            row=1, column=0, columnspan=4, sticky=tk.W, padx=8, pady=(0, 4))

        ttk.Label(left, text='字体大小').grid(row=2, column=0, sticky=tk.W, padx=8)
        ttk.Entry(left, textvariable=self.left_size, width=8).grid(row=2, column=1, sticky=tk.W)

        ttk.Label(left, text='描边宽').grid(row=2, column=2, sticky=tk.W)
        ttk.Entry(left, textvariable=self.left_stroke_width, width=8).grid(row=2, column=3, sticky=tk.W)

        self._color_row(left, 3, '字体颜色', self.left_color, '描边颜色', self.left_stroke)

        # ===== 自定义附加文字 =====
        custom = ttk.LabelFrame(root, text='自定义附加文字（一行一条）')
        custom.pack(fill=tk.BOTH, expand=True, pady=6)

        self.custom_text = tk.Text(custom, height=5)
        self.custom_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.custom_text.insert('1.0', '')

        # ===== 按钮行 =====
        btn = ttk.Frame(root)
        btn.pack(fill=tk.X, pady=10)

        ttk.Button(btn, text='选择输出目录并批量加水印', command=self.on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text='取消', command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _pick_color(self, var):
        color = colorchooser.askcolor(color=var.get(), parent=self)[1]
        if color:
            var.set(color)
            return None
        return None

    def _color_row(self, parent, row, text1, var1, text2, var2):
        ttk.Label(parent, text=text1).grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        ttk.Entry(parent, textvariable=var1, width=10).grid(row=row, column=1, sticky=tk.W)
        ttk.Button(parent, text='选色', command=lambda: self._pick_color(var1)).grid(row=row, column=1, sticky=tk.E)

        ttk.Label(parent, text=text2).grid(row=row, column=2, sticky=tk.W)
        ttk.Entry(parent, textvariable=var2, width=10).grid(row=row, column=3, sticky=tk.W)
        ttk.Button(parent, text='选色', command=lambda: self._pick_color(var2)).grid(row=row, column=3, sticky=tk.E)

    def on_confirm(self):
        try:
            opts = WatermarkOptions(**{
                'center_text': self.center_text.get(),
                'center_enabled': self.center_enabled.get(),
                'center_font_ratio': float(self.center_ratio.get()),
                'center_opacity': float(self.center_opacity.get()),
                'center_color': self.center_color.get(),
                'center_stroke_color': self.center_stroke.get(),
                'left_enabled': self.left_enabled.get(),
                'left_font_size': int(self.left_size.get()),
                'left_color': self.left_color.get(),
                'left_stroke_color': self.left_stroke.get(),
                'left_stroke_width': int(self.left_stroke_width.get()),
                'include_lonlat': self.include_lonlat.get(),
                'include_address': self.include_address.get(),
                'include_time': self.include_time.get(),
                'include_filename': self.include_filename.get(),
                'custom_lines': self.custom_text.get('1.0', tk.END).strip(),
                'logo_enabled': False,
            })
            if not (8 <= opts.left_font_size <= 200):
                raise ValueError('左下角字体大小需在 8-200 之间')
            if not (0.02 <= opts.center_font_ratio <= 0.5):
                raise ValueError('中央水印大小比例建议 0.02-0.5')
            if not (0 <= opts.center_opacity <= 1):
                raise ValueError('透明度需在 0-1 之间')
        except Exception as e:
            messagebox.showerror('参数错误', str(e))
            return

        output_folder = filedialog.askdirectory(title='选择水印图片输出目录')
        if output_folder:
            self.callback(opts, output_folder)
            self.destroy()
