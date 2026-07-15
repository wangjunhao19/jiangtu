from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from services.ai_image_classifier_service import (
    BatchOptions, TrainOptions, get_land_fields, load_model,
    process_image_folder, summarize_training_folder, train_folder_model,
)
from utils.ui_icon import apply_window_icon

ALGORITHM_LABELS = {
    '智能融合（推荐）': 'hybrid',
    '相似样本近邻': 'knn',
    '类别中心快速识别': 'centroid',
}


class AIImageClassificationWindow(tk.Toplevel):

    def __init__(self, master):
        super().__init__(master)
        self.title('AI图片智能归档中心 - 疆途 V1.0')
        self.geometry('1180x820')
        self.minsize(1050, 720)
        apply_window_icon(self)
        self.configure(bg='#f3f6fb')
        self.events = queue.Queue()
        self.running = False
        self._build_ui()
        self.after(120, self._poll_events)

    def _build_ui(self):
        header = tk.Frame(self)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text='AI 图片智能归档', font=('微软雅黑', 16, 'bold')).pack(side=tk.LEFT, padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.train_tab = ttk.Frame(self.notebook)
        self.process_tab = ttk.Frame(self.notebook)
        self.help_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.train_tab, text='模型训练')
        self.notebook.add(self.process_tab, text='批量归档')
        self.notebook.add(self.help_tab, text='帮助')

        self._build_train_tab()
        self._build_process_tab()
        self._build_help_tab()

    @staticmethod
    def _path_row(parent, row, label_text, var, browse_command):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, padx=5, pady=4)
        ttk.Entry(parent, textvariable=var, width=50).grid(row=row, column=1, sticky='ew', padx=5)
        ttk.Button(parent, text='浏览…', command=browse_command).grid(row=row, column=2, padx=5)

    def _build_train_tab(self):
        ttk.Label(self.train_tab, text='用分类文件夹训练本地识别模型',
                  font=('微软雅黑', 16, 'bold')).pack(anchor=tk.W)
        ttk.Label(self.train_tab,
                  text='训练数据总目录下，每个一级文件夹就是一个类别。类别名称完全由用户自己定义，模型训练完成后可反复使用。',
                  foreground='#555').pack(anchor=tk.W, pady=(4, 12))

        settings = ttk.LabelFrame(self.train_tab, text='训练设置', padding=12)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        self.training_dir_var = tk.StringVar()
        self.model_save_var = tk.StringVar()
        self.algorithm_var = tk.StringVar(value='智能融合（推荐）')
        self.augment_var = tk.BooleanVar(value=True)

        self._path_row(settings, 0, '训练目录', self.training_dir_var, self._choose_training_dir)
        self._path_row(settings, 1, '模型保存', self.model_save_var, self._choose_model_save)

        ttk.Label(settings, text='算法').grid(row=2, column=0, sticky=tk.W, padx=5)
        ttk.Combobox(settings, textvariable=self.algorithm_var, state='readonly',
                      values=list(ALGORITHM_LABELS.keys()), width=20).grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(settings, text='数据增强（翻转+旋转）', variable=self.augment_var).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=4)

        actions = ttk.Frame(self.train_tab)
        actions.pack(fill=tk.X, pady=8)
        ttk.Button(actions, text='扫描训练数据', command=self._scan_training_data).pack(side=tk.LEFT, padx=5)
        self.train_button = ttk.Button(actions, text='开始训练', command=self._start_training)
        self.train_button.pack(side=tk.LEFT, padx=5)

        body = ttk.Panedwindow(self.train_tab, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left)
        body.add(right)

        self.class_tree = ttk.Treeview(left, columns=('count',), show='tree headings')
        self.class_tree.heading('#0', text='类别')
        self.class_tree.heading('count', text='样本数')
        self.class_tree.column('#0', width=200)
        self.class_tree.column('count', width=80, anchor=tk.CENTER)
        self.class_tree.pack(fill=tk.BOTH, expand=True)

        self.train_log = scrolledtext.ScrolledText(right, wrap=tk.WORD, width=50)
        self.train_log.pack(fill=tk.BOTH, expand=True)

    def _build_process_tab(self):
        ttk.Label(self.process_tab, text='使用已有模型批量归档照片',
                  font=('微软雅黑', 16, 'bold')).pack(anchor=tk.W)

        settings = ttk.LabelFrame(self.process_tab, text='归档设置', padding=12)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        self.model_var = tk.StringVar()
        self.image_dir_var = tk.StringVar()
        self.land_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.process_algorithm_var = tk.StringVar(value='智能融合（推荐）')
        self.confidence_var = tk.DoubleVar(value=0.6)
        self.process_augment_var = tk.BooleanVar(value=False)

        self._path_row(settings, 0, '模型文件', self.model_var, self._choose_model)
        self._path_row(settings, 1, '图片目录', self.image_dir_var, self._choose_image_dir)
        self._path_row(settings, 2, '图斑KML', self.land_file_var, self._choose_land_file)
        self._path_row(settings, 3, '输出目录', self.output_dir_var, self._choose_output_dir)

        ttk.Label(settings, text='算法').grid(row=4, column=0, sticky=tk.W, padx=5)
        ttk.Combobox(settings, textvariable=self.process_algorithm_var, state='readonly',
                      values=list(ALGORITHM_LABELS.keys()), width=20).grid(row=4, column=1, sticky=tk.W, padx=5)

        ttk.Button(settings, text='加载图斑字段', command=self._load_land_fields).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=4)

        # 输出预设按钮行
        preset_frame = ttk.Frame(settings)
        preset_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, padx=5, pady=4)
        ttk.Label(preset_frame, text='输出预设：').pack(side=tk.LEFT)
        for label in ('按类别分文件夹', '按图斑分文件夹', '全部平铺'):
            ttk.Button(preset_frame, text=label,
                       command=lambda l=label: self._set_output_preset(l)).pack(side=tk.LEFT, padx=3)

        actions = ttk.Frame(self.process_tab)
        actions.pack(fill=tk.X, pady=8)
        self.process_button = ttk.Button(actions, text='开始批量归档', command=self._start_processing)
        self.process_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text='打开输出目录', command=self._open_output_dir).pack(side=tk.LEFT, padx=5)

        self.process_log = scrolledtext.ScrolledText(self.process_tab, wrap=tk.WORD)
        self.process_log.pack(fill=tk.BOTH, expand=True)

    def _build_help_tab(self):
        help_text = (
            '【AI图片智能归档使用说明】\n\n'
            '1. 准备训练数据：将照片按类别放入子文件夹\n'
            '   例如: training/建筑/*.jpg, training/农田/*.jpg\n\n'
            '2. 训练模型：在"模型训练"标签页选择训练目录和保存路径，点击开始训练\n\n'
            '3. 批量归档：在"批量归档"标签页选择模型、图片目录和输出目录\n\n'
            '4. 算法说明：\n'
            '   - 智能融合（推荐）：综合多种特征，准确率最高\n'
            '   - 相似样本近邻：KNN算法，适合类别差异明显的场景\n'
            '   - 类别中心快速识别：计算类别中心，速度最快\n\n'
            '5. 支持的数据增强：水平翻转 + 90°旋转\n\n'
            '6. 模型文件为 .npz 格式，完全保存在本地，不上传任何数据'
        )
        ttk.Label(self.help_tab, text=help_text, justify=tk.LEFT,
                  font=('微软雅黑', 10)).pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

    # ===== 目录选择 =====
    def _choose_training_dir(self):
        folder = filedialog.askdirectory(title='选择训练数据总目录')
        if folder:
            self.training_dir_var.set(folder)

    def _choose_model_save(self):
        path = filedialog.asksaveasfilename(
            title='保存模型文件', defaultextension='.npz',
            filetypes=[('NPZ模型', '*.npz')])
        if path:
            self.model_save_var.set(path)

    def _choose_model(self):
        path = filedialog.askopenfilename(
            title='选择已训练的模型文件',
            filetypes=[('NPZ模型', '*.npz')])
        if path:
            self.model_var.set(path)

    def _choose_image_dir(self):
        folder = filedialog.askdirectory(title='选择待归档图片目录')
        if folder:
            self.image_dir_var.set(folder)

    def _choose_land_file(self):
        path = filedialog.askopenfilename(
            title='选择图斑KML文件',
            filetypes=[('KML/KMZ', '*.kml *.kmz')])
        if path:
            self.land_file_var.set(path)

    def _choose_output_dir(self):
        folder = filedialog.askdirectory(title='选择输出目录')
        if folder:
            self.output_dir_var.set(folder)

    def _load_land_fields(self):
        kml_path = self.land_file_var.get().strip()
        if not kml_path:
            messagebox.showwarning('提示', '请先选择图斑KML文件', parent=self)
            return
        try:
            fields = get_land_fields(kml_path)
            self._append_process_log(f'已加载 {len(fields)} 个图斑字段\n')
        except Exception as e:
            messagebox.showerror('错误', str(e), parent=self)

    def _scan_training_data(self):
        folder = self.training_dir_var.get().strip()
        if not folder:
            messagebox.showwarning('提示', '请先选择训练目录', parent=self)
            return
        try:
            summary = summarize_training_folder(folder)
            self.class_tree.delete(*self.class_tree.get_children())
            for class_name, count in summary.items():
                self.class_tree.insert('', tk.END, text=class_name, values=(count,))
            self._append_train_log(f'扫描完成：{len(summary)} 个类别，共 {sum(summary.values())} 个样本\n')
        except Exception as e:
            messagebox.showerror('扫描失败', str(e), parent=self)

    def _start_training(self):
        if self.running:
            messagebox.showwarning('提示', '当前任务尚未完成。', parent=self)
            return
        training_dir = self.training_dir_var.get().strip()
        model_path = self.model_save_var.get().strip()
        if not training_dir or not model_path:
            messagebox.showwarning('提示', '请选择训练目录和模型保存位置。', parent=self)
            return

        algorithm = ALGORITHM_LABELS.get(self.algorithm_var.get(), 'hybrid')
        options = TrainOptions(algorithm=algorithm, augment=bool(self.augment_var.get()))
        self._set_running(True)
        self._append_train_log('开始训练，模型完全保存在本机。\n')

        def worker():
            try:
                result = train_folder_model(
                    training_dir, model_path, options,
                    progress=lambda done, total, msg: self.events.put(('progress', done, total, msg)),
                )
                self.events.put(('train_done', result))
            except Exception as exc:
                self.events.put(('error', '模型训练失败', str(exc)))
            self.events.put(('idle',))

        threading.Thread(target=worker, daemon=True).start()

    def _set_output_preset(self, label):
        """设置输出目录预设模式"""
        base = self.output_dir_var.get().strip()
        if not base:
            return
        if label == '按类别分文件夹':
            self._append_process_log('已设置输出模式：按类别分文件夹\n')
        elif label == '按图斑分文件夹':
            self._append_process_log('已设置输出模式：按图斑分文件夹\n')
        else:
            self._append_process_log('已设置输出模式：全部平铺\n')

    def _start_processing(self):
        if self.running:
            messagebox.showwarning('提示', '当前任务尚未完成。', parent=self)
            return
        model_path = self.model_var.get().strip()
        image_dir = self.image_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        if not model_path or not image_dir or not output_dir:
            messagebox.showwarning('提示', '请完整填写模型文件、图片目录和输出目录。', parent=self)
            return

        algorithm = ALGORITHM_LABELS.get(self.process_algorithm_var.get(), 'hybrid')
        model = load_model(model_path)
        batch_opts = BatchOptions(algorithm=algorithm)
        self._set_running(True)
        self._append_process_log('开始批量归档处理……\n')

        def worker():
            try:
                process_image_folder(
                    model, image_dir, output_dir, batch_opts,
                    progress=lambda done, total, msg: self.events.put(('progress', done, total, msg)),
                    log=lambda msg: self.events.put(('log_process', msg)),
                )
                self.events.put(('process_done',))
            except Exception as exc:
                self.events.put(('error', '批量归档失败', str(exc)))
            self.events.put(('idle',))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == 'progress':
                _, done, total, msg = event
                self._append_train_log(f'[{done}/{total}] {msg}\n')
            elif kind == 'train_done':
                result = event[1]
                self._append_train_log(f'\n训练完成！模型已保存。\n{result}\n')
                messagebox.showinfo('完成', '模型训练完成！', parent=self)
            elif kind == 'process_done':
                self._append_process_log('\n批量归档完成！\n')
                messagebox.showinfo('完成', '批量归档完成！', parent=self)
            elif kind == 'error':
                _, title, detail = event
                self._append_train_log(f'错误: {detail}\n')
                messagebox.showerror(title, detail, parent=self)
            elif kind == 'log_process':
                self._append_process_log(event[1])
            elif kind == 'log_train':
                self._append_train_log(event[1])
            elif kind == 'idle':
                self._set_running(False)
        self.after(120, self._poll_events)

    def _set_running(self, state):
        self.running = state
        btn_state = 'disabled' if state else 'normal'
        if hasattr(self, 'train_button'):
            self.train_button.configure(state=btn_state)
        if hasattr(self, 'process_button'):
            self.process_button.configure(state=btn_state)

    def _append_train_log(self, text):
        self.train_log.insert(tk.END, text)
        self.train_log.see(tk.END)

    def _append_process_log(self, text):
        self.process_log.insert(tk.END, text)
        self.process_log.see(tk.END)

    def _open_output_dir(self):
        output = self.output_dir_var.get().strip()
        if output and os.path.isdir(output):
            if sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', output])
            elif sys.platform == 'win32':
                os.startfile(output)
            else:
                import subprocess
                subprocess.Popen(['xdg-open', output])
        else:
            messagebox.showwarning('提示', '输出目录不存在', parent=self)
