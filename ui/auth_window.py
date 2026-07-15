import os
import tkinter as tk
from tkinter import messagebox
from config import APP_NAME
from utils.ui_icon import apply_window_icon
from services.license_service import get_saved_customer, get_saved_phone, login_online, start_heartbeat_thread


# ── 调色板（中性深灰主题 - OLED优化）──────────────────────────
# 基于长时间使用友好原则：纯中性深灰 + 绿色状态指示 + 无蓝色倾向
_BG          = '#121212'   # background (深灰，比纯黑更柔和)
_PRIMARY     = '#4CAF50'   # primary (清新绿色，清晰但不刺眼)
_ON_SURFACE  = '#F8FAFC'   # on-surface (亮白)
_ON_VAR      = '#A0A0A0'   # on-surface-variant (中灰，降低视觉疲劳)
_OUTLINE     = '#666666'   # outline (边框色)
_INPUT_BG    = '#1E1E1E'   # surface-container-low（输入框背景）
_CARD_BG     = '#1E1E1E'   # 玻璃卡片底色
_FIELD_BG    = '#262626'   # 表单容器底色
_BORDER      = '#333333'   # border / surface-container-high (低对比度边框)
_ON_PRIMARY  = '#121212'   # on-primary（按钮文字深灰）
_ERROR       = '#EF4444'   # error (红色)

# ── 字体配置（macOS 系统优化）──────────────────────────────
_FONT_TITLE  = ('-apple-system', 32, 'bold')      # 登录页大标题
_FONT_LABEL  = ('-apple-system', 10)              # 标签文字
_FONT_BODY   = ('-apple-system', 11)              # 正文
_FONT_BUTTON = ('-apple-system', 14, 'bold')      # 按钮
_FONT_CODE   = ('Menlo', 11)                      # 等宽字体（激活码）


class AuthWindow(tk.Tk):

    def __init__(self, main_window_factory):
        super().__init__()
        self.main_window_factory = main_window_factory
        self.title(f'{APP_NAME} — 用户登录')
        self.geometry('560x520')
        self.resizable(False, False)
        apply_window_icon(self)
        self.configure(bg=_BG)

        # ── 主容器（上下弹簧实现垂直居中）───────────────────
        tk.Frame(self, bg=_BG).pack(fill=tk.BOTH, expand=True)  # 上方弹簧

        content = tk.Frame(self, bg=_BG)
        content.pack(fill=tk.X, padx=30)   # 水平填充 + 固定边距

        tk.Frame(self, bg=_BG).pack(fill=tk.BOTH, expand=True)  # 下方弹簧

        # ── Placeholder 管理 ──────────────────────────────────
        self._name_ph = '请输入您的真实姓名'
        self._phone_ph = '请输入11位手机号码'

        def _clear_placeholder(entry, default_text):
            if entry.get() == default_text:
                entry.delete(0, tk.END)
                entry.configure(fg=_ON_SURFACE)

        def _restore_placeholder(entry, default_text):
            if not entry.get():
                entry.insert(0, default_text)
                entry.configure(fg=_OUTLINE)

        self._clear_ph = _clear_placeholder
        self._restore_ph = _restore_placeholder

        # ── 品牌标题区 ────────────────────────────────────────
        brand_frame = tk.Frame(content, bg=_BG)
        brand_frame.pack(pady=(0, 6))

        tk.Label(brand_frame, text='疆途', bg=_BG, fg=_PRIMARY,
                 font=_FONT_TITLE).pack()

        # 副标题 + 左右装饰线
        sub_frame = tk.Frame(content, bg=_BG)
        sub_frame.pack(pady=(0, 28))
        tk.Frame(sub_frame, bg=_PRIMARY, height=1, width=60).pack(
            side=tk.LEFT, padx=(0, 8), pady=7)
        tk.Label(sub_frame, text='SMART INSPECTION PLATFORM',
                 bg=_BG, fg=_ON_VAR,
                 font=('-apple-system', 9, 'bold')).pack(side=tk.LEFT)
        tk.Frame(sub_frame, bg=_PRIMARY, height=1, width=60).pack(
            side=tk.LEFT, padx=(8, 0), pady=7)

        # ─ 玻璃卡片 ──────────────────────────────────────────
        card = tk.Frame(content, bg=_CARD_BG,
                        highlightbackground=_BORDER, highlightthickness=2)
        card.pack(fill=tk.X, ipady=8)

        # 卡片内上间距
        tk.Frame(card, bg=_CARD_BG, height=28).pack()

        # 说明文字
        notice = ('请填写已登记的客户姓名和手机号。\n'
                  '系统会自动完成在线授权校验、有效期检查和设备绑定。')
        tk.Label(card, text=notice, bg=_CARD_BG, fg=_ON_VAR,
                 font=_FONT_LABEL, wraplength=420,
                 justify=tk.CENTER).pack(pady=(0, 20))

        # ── 表单区域（深色底块）───────────────────────────────
        form_block = tk.Frame(card, bg=_FIELD_BG,
                              highlightbackground=_BORDER,
                              highlightthickness=1)
        form_block.pack(fill=tk.X, padx=28, pady=(0, 22))

        inner = tk.Frame(form_block, bg=_FIELD_BG)
        inner.pack(fill=tk.X, padx=20, pady=18)

        # 姓名行
        row1 = tk.Frame(inner, bg=_FIELD_BG)
        row1.pack(fill=tk.X, pady=(0, 14))
        tk.Label(row1, text='姓名:', bg=_FIELD_BG, fg=_OUTLINE,
                 font=_FONT_LABEL, width=7, anchor='e').pack(side=tk.LEFT)
        self.customer_var = tk.StringVar()
        self._name_entry = tk.Entry(
            row1, textvariable=self.customer_var,
            font=_FONT_BODY, width=30,
            bg=_INPUT_BG, fg=_OUTLINE, insertbackground=_PRIMARY,
            relief=tk.FLAT, highlightbackground=_BORDER,
            highlightthickness=1, highlightcolor=_PRIMARY)
        self._name_entry.pack(side=tk.LEFT, padx=(10, 0), ipady=7)
        saved_customer = get_saved_customer()
        if saved_customer:
            self.customer_var.set(saved_customer)
            self._name_entry.configure(fg=_ON_SURFACE)
        else:
            self._name_entry.insert(0, self._name_ph)
        self._name_entry.bind('<FocusIn>', lambda e: self._clear_ph(self._name_entry, self._name_ph))
        self._name_entry.bind('<FocusOut>', lambda e: self._restore_ph(self._name_entry, self._name_ph))

        # 手机号行
        row2 = tk.Frame(inner, bg=_FIELD_BG)
        row2.pack(fill=tk.X)
        tk.Label(row2, text='手机号:', bg=_FIELD_BG, fg=_OUTLINE,
                 font=_FONT_LABEL, width=7, anchor='e').pack(side=tk.LEFT)
        self.phone_var = tk.StringVar()
        self._phone_entry = tk.Entry(
            row2, textvariable=self.phone_var,
            font=_FONT_CODE, width=30,
            bg=_INPUT_BG, fg=_OUTLINE, insertbackground=_PRIMARY,
            relief=tk.FLAT, highlightbackground=_BORDER,
            highlightthickness=1, highlightcolor=_PRIMARY)
        self._phone_entry.pack(side=tk.LEFT, padx=(10, 0), ipady=7)
        saved_phone = get_saved_phone()
        if saved_phone:
            self.phone_var.set(saved_phone)
            self._phone_entry.configure(fg=_ON_SURFACE)
        else:
            self._phone_entry.insert(0, self._phone_ph)
        self._phone_entry.bind('<FocusIn>', lambda e: self._clear_ph(self._phone_entry, self._phone_ph))
        self._phone_entry.bind('<FocusOut>', lambda e: self._restore_ph(self._phone_entry, self._phone_ph))

        # ── 状态标签 ──────────────────────────────────────────
        self.status_var = tk.StringVar(value='')
        tk.Label(card, textvariable=self.status_var,
                 bg=_CARD_BG, fg=_ERROR,
                 font=_FONT_LABEL, wraplength=420).pack(pady=(0, 6))

        # ── 登录按钮（圆角全宽蓝色 pill）────────────────────
        btn_frame = tk.Frame(card, bg=_CARD_BG)
        btn_frame.pack(fill=tk.X, padx=28, pady=(8, 14))

        self._login_btn = tk.Label(
            btn_frame, text='登录进入软件  →',
            bg=_PRIMARY, fg=_ON_PRIMARY,
            font=_FONT_BUTTON,
            cursor='hand2', padx=20, pady=14)
        self._login_btn.pack(fill=tk.X)
        self._login_btn.bind('<Button-1>', lambda e: self.activate())
        self._login_btn.bind('<Enter>', lambda e: self._login_btn.configure(bg='#c8d8ff'))
        self._login_btn.bind('<Leave>', lambda e: self._login_btn.configure(bg=_PRIMARY))

        # ─ 演示模式链接 ──────────────────────────────────────
        demo_frame = tk.Frame(card, bg=_CARD_BG)
        demo_frame.pack(pady=(0, 26))
        self._demo_label = tk.Label(
            demo_frame, text='进入演示模式 →',
            bg=_CARD_BG, fg=_OUTLINE,
            font=_FONT_LABEL, cursor='hand2')
        self._demo_label.pack()
        self._demo_label.bind('<Button-1>', lambda e: self.open_demo())
        self._demo_label.bind('<Enter>', lambda e: self._demo_label.configure(fg=_PRIMARY))
        self._demo_label.bind('<Leave>', lambda e: self._demo_label.configure(fg=_OUTLINE))

        # ── 回车绑定登录 ──────────────────────────────────────
        self.bind('<Return>', lambda _e: self.activate())

    # ─────────────────────────── 登录逻辑 ─────────────────────────────
    def activate(self):
        customer = self.customer_var.get().strip()
        phone = self.phone_var.get().strip()

        # 清除 placeholder 文本
        if customer == self._name_ph:
            customer = ''
        if phone == self._phone_ph:
            phone = ''

        if not customer or not phone:
            messagebox.showwarning('提示', '请填写姓名和手机号')
            return

        self.status_var.set('正在连接在线服务器...')
        self.update_idletasks()

        ok, msg, _ = login_online(customer=customer, phone=phone)
        if not ok:
            self.status_var.set(msg)
            messagebox.showerror('登录失败', msg)
            return

        start_heartbeat_thread()
        self.destroy()
        self.main_window_factory().mainloop()

    # ──────────────────────────── 演示模式 ─────────────────────────────
    def open_demo(self):
        if not messagebox.askyesno(
            '进入演示模式',
            '演示模式可以查看界面、加载数据、规划和预览航线，'
            '但不能生成正式材料、上传三资平台或导出DJI可执行任务文件。是否继续？',
            parent=self,
        ):
            return
        os.environ['JT_DEMO_MODE'] = '1'
        self.destroy()
        self.main_window_factory().mainloop()
