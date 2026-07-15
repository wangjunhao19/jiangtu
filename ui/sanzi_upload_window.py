# Source Generated with Decompyle++
# File: sanzi_upload_window.pyc (Python 3.11)
# 骨架重建：三资材料工作台

from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from collections import Counter
from typing import Callable, Dict, List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from utils.ui_icon import apply_window_icon
from services.license_service import BASE_MODULE, authorize_formal_action
from services.sanzi_document_service import (
    SUPPORTED_PLACEHOLDERS, convert_project_word_to_pdf, create_default_template,
    ensure_project_templates, generate_project_documents, list_template_files,
    normalize_land_record, restore_default_templates, write_template_folder_guide,
)
from services.sanzi_project_check_service import check_platform_materials
from services.sanzi_photo_service import organize_project_photos
from services.sanzi_rules import accessory_label
from services.sanzi_upload_service import (
    SanziAuthenticationError, SanziClient, clear_login_cache, export_upload_log,
    import_login_har, load_login_cache, load_synced_records, options_from_cache,
    save_login_cache, scan_archive_materials, sync_all_sanzi_data,
    upload_archive_materials, refresh_uploaded_land_records, delete_platform_attachments,
)


class SanziUploadWindow(tk.Toplevel):
    """三资材料工作台 — 从字节码重建的骨架版本。"""

    def __init__(self, master=None, *_legacy_callbacks, **_kwargs):
        super().__init__(master)
        self.title('疆途·智能巡查管理平台 V1.0｜三资材料工作台')
        self.geometry('1240x820')
        self.minsize(1040, 700)
        self.resizable(True, True)
        try:
            apply_window_icon(self)
        except Exception:
            pass

        # 内部状态
        self._working = False
        self._login_process = None
        self._login_result_file = None
        self._login_status_file = None
        self._login_fresh_requested = False
        self._login_safe_retry_done = False
        self._login_command_base = []
        self._switch_account_snapshot = {}
        self.records: list = []
        self.record_by_iid: dict = {}
        self._task_started_at = 0

        # 加载登录缓存
        try:
            cache = load_login_cache()
        except Exception:
            cache = {}

        # Tkinter 变量
        self.web_url_var = tk.StringVar(value=cache.get('web_url', 'http://222.143.69.159:38590'))
        self.base_url_var = tk.StringVar(value=cache.get('base_url', 'http://222.143.69.159:38762'))
        self.login_url_var = tk.StringVar(value=cache.get('login_url', 'http://222.143.69.159:38590/dist/#/login'))
        self.token_var = tk.StringVar(value=cache.get('token', ''))
        self.token_header_var = tk.StringVar(value=cache.get('token_header', 'Token'))
        self.cookie_var = tk.StringVar(value=cache.get('cookie', ''))
        self.districtcode_var = tk.StringVar(value=cache.get('districtcode', ''))
        self.districtname_var = tk.StringVar(value=cache.get('districtname', ''))
        self.username_var = tk.StringVar(value=cache.get('username', ''))

        login_status = '已保存登录状态，尚未检测' if cache.get('token') else '未登录'
        self.login_status_var = tk.StringVar(value=login_status)

        default_project = str(cache.get('project_dir') or '')
        self.project_dir_var = tk.StringVar(value=default_project)

        if default_project:
            self.output_dir_var = tk.StringVar(value=str(Path(default_project) / '02_材料输出'))
        else:
            self.output_dir_var = tk.StringVar(value='')

        # 模板目录
        default_template_dir = ''
        if default_project:
            default_template_dir = str(Path(default_project) / '01_自定义模板')
        self.template_dir_var = tk.StringVar(value=default_template_dir)

        self.photo_source_var = tk.StringVar(value=str(cache.get('photo_source') or ''))
        self.snap_distance_var = tk.StringVar(value=str(cache.get('snap_distance', '10')))
        self.upload_scene_var = tk.BooleanVar(value=bool(cache.get('upload_scene', True)))
        self.upload_other_var = tk.BooleanVar(value=bool(cache.get('upload_other', True)))
        self.max_scene_photos_var = tk.StringVar(value=str(cache.get('max_scene_photos', '3')))
        self.photo_quality_var = tk.StringVar(value=str(cache.get('photo_quality', '75')))
        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value='全部')
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value='当前没有正在处理的任务')
        self.progress_percent_var = tk.StringVar(value='0%')
        self.progress_eta_var = tk.StringVar(value='剩余时间：--')
        self.upload_ack_var = tk.BooleanVar(value=False)

        # 构建 UI
        self._configure_styles()
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ================================================== styles
    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('Title.TLabel', font=('微软雅黑', 14, 'bold'))
        style.configure('Step.TLabel', font=('微软雅黑', 11, 'bold'))
        style.configure('Status.TLabel', font=('微软雅黑', 9))
        style.configure('Primary.TButton', font=('微软雅黑', 10, 'bold'))

    # ================================================== build UI
    def _build_ui(self):
        # 顶部标题栏
        header = ttk.Frame(self, padding=(16, 10))
        header.pack(fill=tk.X)
        ttk.Label(header, text='三资材料工作台', style='Title.TLabel').pack(side=tk.LEFT)
        self._header_login_label = ttk.Label(header, textvariable=self.login_status_var, style='Status.TLabel')
        self._header_login_label.pack(side=tk.RIGHT)

        # 主体 — Notebook 标签页
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self._build_sync_tab()
        self._build_doc_tab()
        self._build_upload_tab()
        self._build_photo_tab()

        # 底部进度条
        bottom = ttk.Frame(self, padding=(12, 6))
        bottom.pack(fill=tk.X)
        self.progress_bar = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))
        status_row = ttk.Frame(bottom)
        status_row.pack(fill=tk.X)
        ttk.Label(status_row, textvariable=self.progress_percent_var).pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.progress_text_var).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(status_row, textvariable=self.progress_eta_var).pack(side=tk.RIGHT)

    # ── 同步标签页 ──
    def _build_sync_tab(self):
        tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(tab, text='  数据同步  ')

        self._step_banner(tab, '步骤 1：登录三资平台')
        login_frame = ttk.Frame(tab)
        login_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(login_frame, text='用户名：').grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(login_frame, textvariable=self.username_var, width=30).grid(row=0, column=1, padx=(8, 0), pady=4)

        ttk.Label(login_frame, text='Token：').grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(login_frame, textvariable=self.token_var, width=60, show='*').grid(row=1, column=1, padx=(8, 0), pady=4)

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, pady=(0, 12))
        self._primary_button(btn_row, '测试登录', self.test_login).pack(side=tk.LEFT, padx=(0, 8))
        self._primary_button(btn_row, '打开官方登录页', self.open_official_login).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text='清除登录', command=self.clear_login).pack(side=tk.LEFT)

        self._step_banner(tab, '步骤 2：同步平台数据')
        sync_btn_row = ttk.Frame(tab)
        sync_btn_row.pack(fill=tk.X, pady=(0, 12))
        self._primary_button(sync_btn_row, '全量同步', self.sync_all).pack(side=tk.LEFT, padx=(0, 8))
        self._primary_button(sync_btn_row, '导入HAR', self.import_har).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(sync_btn_row, text='查看同步记录', command=self.refresh_tree).pack(side=tk.LEFT)

        # 图斑记录列表
        tree_frame = ttk.LabelFrame(tab, text='已同步图斑记录', padding=8)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('landcode', 'status', 'area', 'owner', 'remark')
        self.sync_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=10)
        self.sync_tree.heading('landcode', text='图斑编号')
        self.sync_tree.heading('status', text='使用状态')
        self.sync_tree.heading('area', text='面积(亩)')
        self.sync_tree.heading('owner', text='承包人')
        self.sync_tree.heading('remark', text='备注')
        for c in columns:
            self.sync_tree.column(c, width=140, minwidth=80)
        self.sync_tree.pack(fill=tk.BOTH, expand=True)

    # ── 材料标签页 ──
    def _build_doc_tab(self):
        tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(tab, text='  材料生成  ')

        self._step_banner(tab, '步骤 3：生成三资材料')

        ttk.Label(tab, text='项目目录：').pack(anchor=tk.W, pady=(4, 0))
        proj_row = ttk.Frame(tab)
        proj_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(proj_row, textvariable=self.project_dir_var, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(proj_row, text='选择', command=self.choose_project_dir).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(tab, text='模板目录：').pack(anchor=tk.W, pady=(4, 0))
        tpl_row = ttk.Frame(tab)
        tpl_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(tpl_row, textvariable=self.template_dir_var, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(tpl_row, text='选择', command=self.choose_template).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(tpl_row, text='打开', command=self.open_template_dir).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(tpl_row, text='恢复默认', command=self.restore_default_template).pack(side=tk.LEFT, padx=(4, 0))

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, pady=(8, 8))
        self._primary_button(btn_row, '生成材料文档', self.generate_docs).pack(side=tk.LEFT, padx=(0, 8))
        self._primary_button(btn_row, 'Word转PDF', self.convert_word_to_pdf).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text='打开输出目录', command=self.open_output_dir).pack(side=tk.LEFT)

        # 材料日志
        self.doc_log = scrolledtext.ScrolledText(tab, height=12, state=tk.DISABLED, font=('Consolas', 9))
        self.doc_log.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    # ── 上传标签页 ──
    def _build_upload_tab(self):
        tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(tab, text='  归档上传  ')

        self._step_banner(tab, '步骤 4：扫描归档材料')
        scan_btn_row = ttk.Frame(tab)
        scan_btn_row.pack(fill=tk.X, pady=(0, 12))
        self._primary_button(scan_btn_row, '扫描归档', self.scan_archive).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(scan_btn_row, text='打开项目目录', command=self.open_project_dir).pack(side=tk.LEFT)

        self._step_banner(tab, '步骤 5：上传到三资平台')
        upload_btn_row = ttk.Frame(tab)
        upload_btn_row.pack(fill=tk.X, pady=(0, 12))
        self._primary_button(upload_btn_row, '上传归档材料', self.upload_archive).pack(side=tk.LEFT, padx=(0, 8))
        self._primary_button(upload_btn_row, '检查附件', self.check_project_attachments).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(upload_btn_row, text='删除平台附件', command=self.delete_platform_materials).pack(side=tk.LEFT)

        # 上传选项
        opt_frame = ttk.LabelFrame(tab, text='上传选项', padding=8)
        opt_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(opt_frame, text='上传现场照片', variable=self.upload_scene_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(opt_frame, text='上传其他附件', variable=self.upload_other_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(opt_frame, text='现场照片上限：').pack(side=tk.LEFT)
        ttk.Entry(opt_frame, textvariable=self.max_scene_photos_var, width=4).pack(side=tk.LEFT, padx=(4, 0))

        # 上传日志
        self.upload_log = scrolledtext.ScrolledText(tab, height=10, state=tk.DISABLED, font=('Consolas', 9))
        self.upload_log.pack(fill=tk.BOTH, expand=True)

    # ── 照片标签页 ──
    def _build_photo_tab(self):
        tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(tab, text='  照片整理  ')

        self._step_banner(tab, '照片按图斑整理')
        ttk.Label(tab, text='照片来源目录：').pack(anchor=tk.W, pady=(4, 0))
        photo_row = ttk.Frame(tab)
        photo_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(photo_row, textvariable=self.photo_source_var, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(photo_row, text='选择', command=self.choose_photo_source).pack(side=tk.LEFT, padx=(8, 0))

        opt_frame = ttk.Frame(tab)
        opt_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(opt_frame, text='GPS匹配距离(米)：').pack(side=tk.LEFT)
        ttk.Entry(opt_frame, textvariable=self.snap_distance_var, width=6).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(opt_frame, text='照片质量：').pack(side=tk.LEFT, padx=(16, 0))
        ttk.Entry(opt_frame, textvariable=self.photo_quality_var, width=4).pack(side=tk.LEFT, padx=(4, 0))

        self._primary_button(tab, '整理照片', self.organize_photos).pack(fill=tk.X, pady=(0, 8))

        self.photo_log = scrolledtext.ScrolledText(tab, height=14, state=tk.DISABLED, font=('Consolas', 9))
        self.photo_log.pack(fill=tk.BOTH, expand=True)

    # ================================================== helpers
    def _step_banner(self, parent, text):
        ttk.Label(parent, text=text, style='Step.TLabel').pack(anchor=tk.W, pady=(12, 4))

    def _primary_button(self, parent, text, command):
        return ttk.Button(parent, text=text, command=command, style='Primary.TButton')

    def _append_doc_log(self, text):
        self.doc_log.config(state=tk.NORMAL)
        self.doc_log.insert(tk.END, f'{text}\n')
        self.doc_log.see(tk.END)
        self.doc_log.config(state=tk.DISABLED)

    def _append_upload_log(self, text):
        self.upload_log.config(state=tk.NORMAL)
        self.upload_log.insert(tk.END, f'{text}\n')
        self.upload_log.see(tk.END)
        self.upload_log.config(state=tk.DISABLED)

    def _append_photo_log(self, text):
        self.photo_log.config(state=tk.NORMAL)
        self.photo_log.insert(tk.END, f'{text}\n')
        self.photo_log.see(tk.END)
        self.photo_log.config(state=tk.DISABLED)

    def _set_progress(self, value=0, maximum=100):
        self.progress_var.set(value)
        self.progress_percent_var.set(f'{int(value)}%')

    def _run_background(self, task_name, worker, success=None, error=None):
        if self._working:
            messagebox.showwarning('提示', '当前有任务正在执行，请等待完成', parent=self)
            return
        self._working = True
        self._task_started_at = time.time()
        self.progress_text_var.set(f'正在执行：{task_name}')

        def task():
            try:
                result = worker()
                self.after(0, lambda: self._task_success(task_name, result, success))
            except Exception as exc:
                self.after(0, lambda: self._task_error(task_name, exc, error))

        threading.Thread(target=task, daemon=True).start()

    def _task_success(self, task_name, result, callback=None):
        self._working = False
        self.progress_var.set(100)
        self.progress_percent_var.set('100%')
        self.progress_text_var.set(f'{task_name} 完成')
        self.progress_eta_var.set('剩余时间：--')
        if callback:
            try:
                callback(result)
            except Exception:
                pass

    def _task_error(self, task_name, exc, callback=None):
        self._working = False
        self.progress_var.set(0)
        self.progress_percent_var.set('0%')
        self.progress_text_var.set(f'{task_name} 失败')
        self.progress_eta_var.set('剩余时间：--')
        if callback:
            try:
                callback(exc)
            except Exception:
                pass
        messagebox.showerror(f'{task_name} 失败', str(exc), parent=self)

    def _on_close(self):
        self.destroy()

    def _open_path(self, path):
        if sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        elif sys.platform == 'win32':
            os.startfile(str(path))
        else:
            subprocess.Popen(['xdg-open', str(path)])

    # ================================================== 项目与目录
    def choose_project_dir(self):
        d = filedialog.askdirectory(title='选择项目目录', parent=self)
        if d:
            self.project_dir_var.set(d)
            self.output_dir_var.set(str(Path(d) / '02_材料输出'))
            self.template_dir_var.set(str(Path(d) / '01_自定义模板'))
            self._update_project_paths()

    def _update_project_paths(self):
        project_dir = self.project_dir_var.get()
        if project_dir:
            self.output_dir_var.set(str(Path(project_dir) / '02_材料输出'))
            self.template_dir_var.set(str(Path(project_dir) / '01_自定义模板'))

    def choose_template(self):
        d = filedialog.askdirectory(title='选择模板目录', parent=self)
        if d:
            self.template_dir_var.set(d)

    def open_template_dir(self):
        d = self.template_dir_var.get()
        if d and Path(d).is_dir():
            self._open_path(d)
        else:
            messagebox.showinfo('提示', '模板目录不存在', parent=self)

    def open_output_dir(self):
        d = self.output_dir_var.get()
        if d and Path(d).is_dir():
            self._open_path(d)
        else:
            messagebox.showinfo('提示', '输出目录不存在', parent=self)

    def open_project_dir(self):
        d = self.project_dir_var.get()
        if d and Path(d).is_dir():
            self._open_path(d)
        else:
            messagebox.showinfo('提示', '项目目录不存在', parent=self)

    def choose_photo_source(self):
        d = filedialog.askdirectory(title='选择照片来源目录', parent=self)
        if d:
            self.photo_source_var.set(d)

    # ================================================== 登录
    def test_login(self):
        def worker():
            client = SanziClient(options=self._client_options())
            return client
        self._run_background('测试登录', worker, success=lambda c: self._set_login_state(True, '登录测试成功'))

    def _set_login_state(self, ok, message):
        self.login_status_var.set(message if ok else '未登录')

    def _client_options(self):
        from services.sanzi_upload_service import SanziUploadOptions
        opts = SanziUploadOptions()
        opts.web_url = self.web_url_var.get()
        opts.base_url = self.base_url_var.get()
        opts.token = self.token_var.get()
        opts.token_header = self.token_header_var.get()
        opts.cookie = self.cookie_var.get()
        opts.districtcode = self.districtcode_var.get()
        opts.districtname = self.districtname_var.get()
        return opts

    def clear_login(self):
        try:
            clear_login_cache()
        except Exception:
            pass
        self.token_var.set('')
        self.cookie_var.set('')
        self.username_var.set('')
        self.login_status_var.set('未登录')

    def open_official_login(self):
        url = self.login_url_var.get() or 'http://222.143.69.159:38590/dist/#/login'
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            messagebox.showinfo('提示', f'请在浏览器中访问：\n{url}', parent=self)

    def import_har(self):
        f = filedialog.askopenfilename(title='选择HAR文件', filetypes=[('HAR文件', '*.har')], parent=self)
        if not f:
            return
        try:
            result = import_login_har(f)
            if result:
                save_login_cache(result)
                self.token_var.set(result.get('token', ''))
                self.cookie_var.set(result.get('cookie', ''))
                self.login_status_var.set('已从HAR导入登录状态')
                messagebox.showinfo('导入成功', '已从HAR文件导入登录信息', parent=self)
            else:
                messagebox.showwarning('导入失败', '未能从HAR文件中提取登录信息', parent=self)
        except Exception as exc:
            messagebox.showerror('导入失败', str(exc), parent=self)

    # ================================================== 同步
    def sync_all(self):
        def worker():
            client = SanziClient(options=self._client_options())
            records, problems = sync_all_sanzi_data(client=client)
            self.records = records or []
            return records, problems
        self._run_background('全量同步', worker, success=self._on_sync_done)

    def _on_sync_done(self, result):
        records, problems = result or ([], [])
        self._append_doc_log(f'同步完成：{len(records)} 条记录')
        self._refresh_sync_tree()
        if problems:
            self._append_doc_log(f'问题：{len(problems)} 个')
        messagebox.showinfo('同步完成', f'成功同步 {len(records)} 条图斑记录', parent=self)

    def _refresh_sync_tree(self):
        for item in self.sync_tree.get_children():
            self.sync_tree.delete(item)
        for rec in self.records:
            try:
                landcode = rec.get('landcode', '')
                status = str(rec.get('use_status_label', rec.get('use_status', '')))
                area = rec.get('area_mu', rec.get('area', ''))
                owner = rec.get('contractor', rec.get('owner', ''))
                remark = rec.get('remark', '')
                self.sync_tree.insert('', tk.END, values=(landcode, status, area, owner, remark))
            except Exception:
                pass

    def refresh_tree(self):
        self._refresh_sync_tree()

    # ================================================== 材料生成
    def generate_docs(self):
        project_dir = self.project_dir_var.get()
        template_dir = self.template_dir_var.get()
        if not project_dir:
            messagebox.showwarning('提示', '请先选择项目目录', parent=self)
            return
        def worker():
            output_dir = self.output_dir_var.get() or str(Path(project_dir) / '02_材料输出')
            os.makedirs(output_dir, exist_ok=True)
            result = generate_project_documents(
                records=self.records,
                template_dir=template_dir,
            )
            return result
        self._run_background('生成材料文档', worker,
                             success=lambda r: self._append_doc_log(f'生成完成：{r}'))

    def convert_word_to_pdf(self):
        output_dir = self.output_dir_var.get()
        if not output_dir or not Path(output_dir).is_dir():
            messagebox.showwarning('提示', '输出目录不存在', parent=self)
            return
        def worker():
            return convert_project_word_to_pdf(output_dir)
        self._run_background('Word转PDF', worker,
                             success=lambda r: self._append_doc_log(f'转换完成：{r}'))

    def restore_default_template(self):
        try:
            template_dir = self.template_dir_var.get()
            if template_dir:
                restore_default_templates(template_dir, overwrite=False)
                messagebox.showinfo('提示', '默认模板已恢复', parent=self)
        except Exception as exc:
            messagebox.showerror('恢复失败', str(exc), parent=self)

    # ================================================== 归档上传
    def scan_archive(self):
        project_dir = self.project_dir_var.get()
        if not project_dir:
            messagebox.showwarning('提示', '请先选择项目目录', parent=self)
            return
        def worker():
            materials, problems = scan_archive_materials(
                archive_root=project_dir,
                records=self.records,
            )
            return materials, problems
        self._run_background('扫描归档', worker,
                             success=lambda r: self._append_upload_log(f'扫描完成：{len(r[0])} 个材料，{len(r[1])} 个问题'))

    def upload_archive(self):
        def worker():
            client = SanziClient(options=self._client_options())
            result = upload_archive_materials(client=client)
            return result
        self._run_background('上传归档', worker,
                             success=lambda r: self._append_upload_log(f'上传完成：{r}'))

    def check_project_attachments(self):
        project_dir = self.project_dir_var.get()
        if not project_dir:
            messagebox.showwarning('提示', '请先选择项目目录', parent=self)
            return
        def worker():
            result = check_platform_materials(
                records=self.records,
                project_dir=project_dir,
            )
            return result
        self._run_background('检查附件', worker,
                             success=lambda r: self._append_upload_log(f'检查完成：{r}'))

    def delete_platform_materials(self):
        if not messagebox.askyesno('确认', '确定要删除平台上的附件吗？此操作不可恢复。', parent=self):
            return
        def worker():
            client = SanziClient(options=self._client_options())
            result = delete_platform_attachments(client=client)
            return result
        self._run_background('删除平台附件', worker,
                             success=lambda r: self._append_upload_log(f'删除完成：{r}'))

    # ================================================== 照片整理
    def organize_photos(self):
        photo_source = self.photo_source_var.get()
        if not photo_source or not Path(photo_source).is_dir():
            messagebox.showwarning('提示', '请先选择照片来源目录', parent=self)
            return
        project_dir = self.project_dir_var.get()
        if not project_dir:
            messagebox.showwarning('提示', '请先选择项目目录', parent=self)
            return
        def worker():
            result = organize_project_photos(
                records=self.records,
                photo_root=photo_source,
                project_dir=project_dir,
                match_distance_m=float(self.snap_distance_var.get() or 10),
            )
            return result
        self._run_background('整理照片', worker,
                             success=lambda r: self._append_photo_log(f'整理完成：{r}'))

    # ================================================== 占位方法
    def _initial_project_prompt(self):
        """启动后提示用户选择项目目录。"""
        pass

    def _periodic_login_check(self):
        """定期检查登录状态。"""
        pass

    def _require_formal_authorization(self, action_type=''):
        return True, '本地模拟授权通过'

    def _read_login_status(self):
        return bool(self.token_var.get())

    def _save_cache(self):
        try:
            save_login_cache({
                'web_url': self.web_url_var.get(),
                'base_url': self.base_url_var.get(),
                'token': self.token_var.get(),
                'token_header': self.token_header_var.get(),
                'cookie': self.cookie_var.get(),
                'districtcode': self.districtcode_var.get(),
                'districtname': self.districtname_var.get(),
                'username': self.username_var.get(),
                'project_dir': self.project_dir_var.get(),
                'photo_source': self.photo_source_var.get(),
                'snap_distance': self.snap_distance_var.get(),
                'upload_scene': self.upload_scene_var.get(),
                'upload_other': self.upload_other_var.get(),
                'max_scene_photos': self.max_scene_photos_var.get(),
                'photo_quality': self.photo_quality_var.get(),
            })
        except Exception:
            pass

    def _cache_payload(self):
        return {}

    def _upload_flags_valid(self):
        return True, ''

    def _triple_delete_confirmation(self):
        return messagebox.askyesno('三重确认', '确定要删除吗？', parent=self)

    def _reset_project_variables(self):
        self.records = []
        self.record_by_iid = {}

    def _clear_current_project_for_new_account(self):
        pass

    def _handle_project_after_account_switch(self):
        pass

    def _clear_web_login_storage(self):
        pass

    def _sanzi_webview_storage_root(self):
        return Path(tempfile.gettempdir()) / 'jt_webview'

    def _launch_login_process(self):
        pass

    def _poll_login_result(self):
        pass

    def _apply_login_info(self, info=None):
        pass

    def _infer_current_village_from_records(self):
        return ''

    def _ensure_project(self):
        return bool(self.project_dir_var.get())

    def _load_existing_project(self):
        pass

    def _format_eta(self, elapsed=0, done=0, total=0):
        if done <= 0 or total <= done:
            return '--'
        remaining = elapsed / done * (total - done)
        if remaining >= 3600:
            return f'{int(remaining // 3600)}小时{int(remaining % 3600 // 60):02d}分'
        elif remaining >= 60:
            return f'{int(remaining // 60)}分{int(remaining % 60):02d}秒'
        return f'{int(remaining)}秒'

    def _on_workflow_mousewheel(self, event):
        pass

    def _focus_section(self, section_name=''):
        pass

    def _choose_landcodes_for_generation(self):
        return [r.get('landcode', '') for r in self.records if isinstance(r, dict)]


def run_sanzi_workbench():
    '''在独立进程中启动三资工作台，窗口不再跟随主软件最小化。'''
    app = SanziUploadWindow()
    app.mainloop()
    return 0
