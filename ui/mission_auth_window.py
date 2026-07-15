"""航线规划模块在线授权登录窗口。"""
import tkinter as tk
from tkinter import messagebox, ttk
from utils.ui_icon import apply_window_icon
from config import COMPANY_TEL, ONLINE_LICENSE_SERVER
from services.license_service import MISSION_MODULE, get_saved_customer, get_saved_phone, login_online, start_heartbeat_thread


class MissionAuthWindow(tk.Toplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title('航线规划在线登录')
        self.geometry('520x360')
        self.resizable(False, False)
        apply_window_icon(self)
        self.granted = False
        self.transient(parent)
        self.grab_set()

        frm = ttk.Frame(self, padding=22)
        frm.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(frm, text='航线规划功能在线登录', font=('微软雅黑', 14, 'bold')).pack(pady=(0, 8))

        # 说明
        ttk.Label(
            frm,
            text='请填写已登记的客户姓名和手机号；系统会在线校验航线规划权限、有效期和绑定设备。',
            foreground='#34495e',
            wraplength=450,
        ).pack(anchor=tk.W, pady=(0, 12))

        # 用户信息表单
        form = ttk.LabelFrame(frm, text='用户信息', padding=14)
        form.pack(fill=tk.X, pady=(0, 12))

        # 姓名行
        ttk.Label(form, text='姓名：', font=('微软雅黑', 10)).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.customer_var = tk.StringVar(value=get_saved_customer())
        ttk.Entry(form, textvariable=self.customer_var, font=('微软雅黑', 11), width=34).grid(
            row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=8)

        # 手机号行
        ttk.Label(form, text='手机号：', font=('微软雅黑', 10)).grid(row=1, column=0, sticky=tk.W, pady=8)
        self.phone_var = tk.StringVar(value=get_saved_phone())
        ttk.Entry(form, textvariable=self.phone_var, font=('Consolas', 11), width=34).grid(
            row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=8)

        form.columnconfigure(1, weight=1)

        # 状态标签
        self.status_var = tk.StringVar(value='状态：未登录')
        ttk.Label(
            frm,
            textvariable=self.status_var,
            foreground='#b00020',
            wraplength=450,
            font=('微软雅黑', 10, 'bold'),
        ).pack(anchor=tk.W, pady=(0, 10))

        # 按钮行
        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=4)

        ttk.Button(btn_row, text='登录并打开航线规划', command=self.activate).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text='关闭', command=self.destroy).pack(side=tk.RIGHT)

        # 底部信息
        tip = f'在线服务器：{ONLINE_LICENSE_SERVER}\n商家电话：{COMPANY_TEL}'
        ttk.Label(frm, text=tip, foreground='#666', justify=tk.LEFT, wraplength=450).pack(anchor=tk.W, pady=(10, 0))

        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Return>', lambda _e: self.activate())

    def activate(self):
        phone = self.phone_var.get().strip()
        customer = self.customer_var.get().strip()
        self.status_var.set('状态：正在连接在线服务器...')
        self.update_idletasks()

        ok, msg, _ = login_online(customer=customer, phone=phone, required_module=MISSION_MODULE)
        if not ok:
            self.status_var.set(f'状态：{msg}')
            messagebox.showerror('登录失败', msg)
            return

        self.granted = True
        start_heartbeat_thread()
        self.destroy()
