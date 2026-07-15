# Source Generated with Decompyle++
# File: anyang_sanzi_export_webview.pyc (Python 3.11)

from __future__ import annotations
import argparse
import base64
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from utils.webview_icon import apply_windows_titlebar_icon_async

DEFAULT_URL = 'http://59.227.115.172:10313/dataAcquisition/index?menu_code=2'


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return base / relative


def _safe_filename(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', str(value or '安阳三资图斑导出.zip')).strip(' .')
    if not name.lower().endswith('.zip'):
        name += '.zip'
    return name or '安阳三资图斑导出.zip'


def _target_host_port(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if not host:
        raise ValueError('安阳三资平台地址缺少主机名')
    if parsed.port:
        port = parsed.port
    elif parsed.scheme.lower() == 'https':
        port = 443
    else:
        port = 80
    return (host, port)


def _probe_target(url: str, *, timeout: float = 4.0) -> tuple[bool, str]:
    """只检测目标主机端口，避免依赖 requests 或外网环境。"""
    host, port = _target_host_port(url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return (False, f'无法连接安阳三资内网：{exc}')
    except Exception as exc:
        return (False, str(exc))
    return (True, f'已连接到安阳三资内网服务：{host}:{port}')


class ExportApi:

    def __init__(self, output_dir: Path, exporter_script: str, target_url: str) -> None:
        self.output_dir = output_dir
        self.exporter_script = exporter_script
        self.target_url = target_url
        self.window = None
        self._lock = threading.Lock()
        self._injecting = False
        self._retry_callback = None

    def bind_window(self, window) -> None:
        self.window = window

    def bind_retry_callback(self, callback: Callable[[], None]) -> None:
        self._retry_callback = callback

    def get_config(self) -> dict[str, Any]:
        return {'output_dir': str(self.output_dir), 'url': self.target_url}

    def retry_open(self) -> dict[str, Any]:
        if not self._retry_callback:
            return {'ok': False, 'error': '连接检测尚未初始化'}
        try:
            self._retry_callback()
            return {'ok': True}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def open_output_dir(self) -> dict[str, Any]:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(self.output_dir))
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', str(self.output_dir)])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', str(self.output_dir)])
            return {'ok': True}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def start_export(self, options=None) -> dict[str, Any]:
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except Exception:
                options = {}
        if not isinstance(options, dict):
            options = {}
        with self._lock:
            if self._injecting:
                return {'ok': False, 'error': '导出脚本正在启动，请稍候。'}
            self._injecting = True

        def worker() -> None:
            try:
                if self.window is None:
                    raise RuntimeError('网页窗口尚未准备完成')
                prefix = 'window.__JT_AY_EXPORT_OPTIONS__ = ' + json.dumps(options, ensure_ascii=False) + ';\n'
                self.window.evaluate_js(prefix + self.exporter_script)
            except Exception:
                traceback.print_exc()
            finally:
                with self._lock:
                    self._injecting = False

        threading.Thread(target=worker, daemon=True, name='anyang-export-inject').start()
        return {'ok': True}

    def save_zip(self, base64_data: str, filename: str) -> dict[str, Any]:
        try:
            if not isinstance(base64_data, str) or not base64_data:
                raise ValueError('没有收到导出数据')
            if len(base64_data) > 471859200:
                raise ValueError('导出数据异常过大，已停止保存')
            payload = base64.b64decode(base64_data, validate=False)
            if len(payload) < 4 or payload[:2] != b'PK':
                raise ValueError('导出内容不是有效ZIP')
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir / _safe_filename(filename)
            tmp = target.with_suffix(target.suffix + '.tmp')
            tmp.write_bytes(payload)
            tmp.replace(target)
            return {'ok': True, 'path': str(target), 'size': len(payload)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}


def _start_page_html(target_url: str, output_dir: str) -> str:
    target_json = json.dumps(target_url, ensure_ascii=False)
    output_json = json.dumps(output_dir, ensure_ascii=False)
    return (
        '<!doctype html>\n'
        '<html lang="zh-CN">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>安阳三资内网连接检测</title>\n'
        '<style>\n'
        "*{box-sizing:border-box} body{margin:0;background:#f2f6f8;color:#24323d;font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif}\n"
        '.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:28px}\n'
        '.card{width:min(760px,96vw);background:#fff;border:1px solid #dce5ea;border-radius:16px;box-shadow:0 18px 50px rgba(39,67,82,.14);padding:30px}\n'
        '.logo{display:inline-flex;align-items:center;gap:10px;font-weight:700;color:#116b52;font-size:22px}\n'
        '.dot{width:14px;height:14px;border-radius:50%;background:#138a67;box-shadow:0 0 0 6px #e2f4ee}\n'
        'h1{font-size:24px;margin:22px 0 10px} .tip{line-height:1.8;color:#52636f}\n'
        '.notice{margin:18px 0;padding:14px 16px;border-radius:10px;background:#fff8e6;border:1px solid #f0d995;color:#735b16;line-height:1.7}\n'
        '.status{margin:18px 0;padding:16px;border-radius:10px;background:#eef5f7;border:1px solid #d6e4e8;line-height:1.65;white-space:pre-wrap}\n'
        ".status.ok{background:#eaf8f1;border-color:#b9e4ce;color:#17623f} .status.err{background:#fff0f0;border-color:#efc0c0;color:#8b2d2d}\n"
        '.meta{font-size:13px;color:#71808a;line-height:1.7;word-break:break-all}\n'
        '.actions{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap} button{border:1px solid #b8c8d0;border-radius:8px;background:#fff;padding:9px 18px;font-size:14px;cursor:pointer}\n'
        'button.primary{background:#087f5b;color:#fff;border-color:#087f5b} button:disabled{opacity:.55;cursor:not-allowed}\n'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '<div class="wrap"><div class="card">\n'
        '<div class="logo"><span class="dot"></span>疆途·安阳三资在线导出</div>\n'
        '<h1>正在检测安阳三资内网连接</h1>\n'
        '<div class="tip">该模块必须在能够访问安阳三资内网的客户电脑上运行。公网、普通 VPN 或未接入指定内网时打不开属于正常情况。</div>\n'
        '<div class="notice">程序会先检测内网端口，检测成功后才打开官方网页；检测失败时停留在本提示页，不再直接加载造成长时间未响应。</div>\n'
        '<div id="status" class="status">正在准备连接检测，请稍候……</div>\n'
        '<div class="meta">平台地址：<span id="target"></span><br>输出目录：<span id="output"></span></div>\n'
        '<div class="actions"><button id="retry" class="primary">重新检测并打开</button><button id="folder">打开输出目录</button></div>\n'
        '</div></div>\n'
        '<script>\n'
        'const target=' + target_json + '; const output=' + output_json + ';\n'
        "document.getElementById('target').textContent=target;\n"
        "document.getElementById('output').textContent=output;\n"
        "window.jtSetConnectionStatus=function(kind,text){\n"
        "  const el=document.getElementById('status');\n"
        "  el.className='status '+(kind||''); el.textContent=text;\n"
        "  document.getElementById('retry').disabled=(kind==='checking');\n"
        "};\n"
        "document.getElementById('retry').onclick=async()=>{\n"
        "  window.jtSetConnectionStatus('checking','正在检测安阳三资内网，请稍候……');\n"
        "  try{const r=await window.pywebview.api.retry_open(); if(!r||r.ok===false) window.jtSetConnectionStatus('err',(r&&r.error)||'重新检测失败');}\n"
        "  catch(e){window.jtSetConnectionStatus('err','重新检测失败：'+e);}\n"
        "};\n"
        "document.getElementById('folder').onclick=async()=>{\n"
        "  try{const r=await window.pywebview.api.open_output_dir(); if(!r||r.ok===false) window.jtSetConnectionStatus('err',(r&&r.error)||'打开目录失败');}\n"
        "  catch(e){window.jtSetConnectionStatus('err','打开目录失败：'+e);}\n"
        "};\n"
        "</script>\n"
        "</body></html>"
    )


def _launcher_script(output_dir: str) -> str:
    return (
        '\n(function () {\n'
        "  const old = document.getElementById('jt-anyang-launcher');\n"
        '  if (old) old.remove();\n'
        "  const box = document.createElement('div');\n"
        "  box.id = 'jt-anyang-launcher';\n"
        '  box.innerHTML = `\n'
        '    <div class="jt-title"><b>疆途·安阳三资在线图斑</b><button id="jt-launch-min">—</button></div>\n'
        '    <div class="jt-launch-body">\n'
        '      <label><input id="jt-work" type="checkbox" checked> 工作进度</label>\n'
        '      <label><input id="jt-rectify" type="checkbox" checked> 整改专题</label>\n'
        '      <label><input id="jt-detail" type="checkbox" checked> 补齐正式图斑号</label>\n'
        '      <div class="jt-row"><span>并发：</span><select id="jt-concurrency"><option>2</option><option selected>4</option><option>6</option></select></div>\n'
        '      <div class="jt-output">输出目录：OUTPUT_DIR</div>\n'
        '      <div class="jt-buttons"><button id="jt-start">一键读取并导出</button><button id="jt-open-folder">打开输出目录</button></div>\n'
        '      <div id="jt-launch-msg">登录并进入当前村后，点击"一键读取并导出"。</div>\n'
        '    </div>`;\n'
        '  Object.assign(box.style, {\n'
        "    position: 'fixed', left: '16px', top: '16px', width: '345px', zIndex: '2147483646',\n"
        "    background: '#fff', border: '1px solid #cfd8df', borderRadius: '11px', overflow: 'hidden',\n"
        "    boxShadow: '0 12px 36px rgba(0,0,0,.23)', color: '#17202a', fontSize: '13px',\n"
        "    fontFamily: 'Microsoft YaHei UI,Microsoft YaHei,system-ui,sans-serif'\n"
        '  });\n'
        "  const style = document.createElement('style');\n"
        '  style.textContent = `\n'
        "    #jt-anyang-launcher .jt-title{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:#126b52;color:white}\n"
        "    #jt-anyang-launcher .jt-title button{border:0;background:transparent;color:white;font-size:18px;cursor:pointer}\n"
        "    #jt-anyang-launcher .jt-launch-body{padding:11px 12px}\n"
        "    #jt-anyang-launcher label{margin-right:10px;white-space:nowrap}\n"
        "    #jt-anyang-launcher .jt-row{margin-top:9px}\n"
        "    #jt-anyang-launcher select{padding:3px 8px}\n"
        "    #jt-anyang-launcher .jt-output{margin-top:8px;color:#66717a;word-break:break-all;line-height:1.45}\n"
        "    #jt-anyang-launcher .jt-buttons{display:flex;gap:8px;margin-top:10px}\n"
        "    #jt-anyang-launcher .jt-buttons button{border:1px solid #b9c7d0;border-radius:6px;background:#fff;padding:6px 10px;cursor:pointer}\n"
        "    #jt-anyang-launcher #jt-start{background:#087f5b;color:#fff;border-color:#087f5b}\n"
        "    #jt-anyang-launcher #jt-launch-msg{margin-top:8px;color:#66717a;line-height:1.45}\n"
        '  `;\n'
        '  document.documentElement.appendChild(style);\n'
        '  document.documentElement.appendChild(box);\n'
        "  const body = box.querySelector('.jt-launch-body');\n"
        "  box.querySelector('#jt-launch-min').onclick = () => body.style.display = body.style.display === 'none' ? 'block' : 'none';\n"
        "  box.querySelector('#jt-open-folder').onclick = async () => {\n"
        '    const r = await window.pywebview.api.open_output_dir();\n'
        "    if (!r || r.ok === false) box.querySelector('#jt-launch-msg').textContent = r?.error || '打开目录失败';\n"
        '  };\n'
        "  box.querySelector('#jt-start').onclick = async () => {\n"
        "    const msg = box.querySelector('#jt-launch-msg');\n"
        "    msg.textContent = '正在启动读取，请查看右上角进度窗口……';\n"
        '    const options = {\n'
        "      includeWork: box.querySelector('#jt-work').checked,\n"
        "      includeRectify: box.querySelector('#jt-rectify').checked,\n"
        "      fetchDetails: box.querySelector('#jt-detail').checked,\n"
        "      concurrency: Number(box.querySelector('#jt-concurrency').value || 4)\n"
        '    };\n'
        '    const r = await window.pywebview.api.start_export(options);\n'
        "    if (!r || r.ok === false) msg.textContent = r?.error || '启动失败';\n"
        '  };\n'
        '  return true;\n'
        '})();\n'
    ).replace('OUTPUT_DIR', json.dumps(output_dir, ensure_ascii=False)[1:-1])


def run_anyang_sanzi_export_webview(argv: list[str] | None) -> int:
    import webview

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--jt-anyang-export', action='store_true')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--url', default=DEFAULT_URL)
    args, _ = parser.parse_known_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    exporter_path = _resource_path('resources/anyang_online_exporter.js')
    if not exporter_path.is_file():
        raise FileNotFoundError(f'缺少安阳在线导出脚本：{exporter_path}')
    exporter_script = exporter_path.read_text(encoding='utf-8')

    api = ExportApi(output_dir, exporter_script, args.url)

    title = '疆途·智能巡查管理平台 V1.0｜安阳三资在线图斑导出'

    window = webview.create_window(
        title,
        html=_start_page_html(args.url, str(output_dir)),
        js_api=api,
        width=1380,
        height=880,
        min_size=(1040, 680),
        confirm_close=False,
    )

    api.bind_window(window)
    apply_windows_titlebar_icon_async(title)

    launcher = _launcher_script(str(output_dir))

    state_lock = threading.Lock()
    state = {'checking': False, 'remote_started': False, 'initial_started': False}

    def set_connection_status(kind: str, message: str) -> None:
        try:
            window.evaluate_js(
                'window.jtSetConnectionStatus && window.jtSetConnectionStatus('
                + json.dumps(kind, ensure_ascii=False)
                + ','
                + json.dumps(message, ensure_ascii=False)
                + ');'
            )
        except Exception:
            pass

    def inject_launcher() -> None:
        try:
            window.evaluate_js(launcher)
        except Exception:
            pass

    def open_target() -> None:
        with state_lock:
            if state['checking'] or state['remote_started']:
                return
            state['checking'] = True

        set_connection_status('checking', '正在检测安阳三资内网，请稍候……')

        def worker() -> None:
            ok, detail = _probe_target(args.url, timeout=4.0)
            if not ok:
                with state_lock:
                    state['checking'] = False
                set_connection_status('err', detail + '\n\n当前电脑未连接安阳三资内网，或VPN/网络路由无法访问该内网地址。' + '\n请先在Chrome中确认平台能够正常打开，再点击"重新检测并打开"。')
                return

            set_connection_status('ok', detail + '\n正在打开安阳三资官方页面……')
            time.sleep(0.35)

            try:
                with state_lock:
                    state['remote_started'] = True
                    state['checking'] = False
                window.load_url(args.url)
            except Exception as exc:
                with state_lock:
                    state['remote_started'] = False
                    state['checking'] = False
                set_connection_status('err', f'内网端口可连接，但网页打开失败：{exc}\n请重新检测或在Chrome中测试平台。')

        threading.Thread(target=worker, daemon=True, name='anyang-network-probe').start()

    api.bind_retry_callback(open_target)

    def on_loaded() -> None:
        apply_windows_titlebar_icon_async(title)
        with state_lock:
            remote_started = state['remote_started']
            initial_started = state['initial_started']
            if not initial_started:
                state['initial_started'] = True

        if remote_started:
            threading.Timer(0.8, inject_launcher).start()
            return
        if not initial_started:
            threading.Timer(0.45, open_target).start()

    window.events.loaded += on_loaded

    storage_root = Path(os.getenv('APPDATA') or Path.home()) / 'JiangTu' / 'anyang_sanzi_webview'
    storage_root.mkdir(parents=True, exist_ok=True)

    try:
        webview.start(
            gui='edgechromium' if os.name == 'nt' else None,
            debug=False,
            storage_path=str(storage_root),
        )
    except TypeError:
        webview.start(
            debug=False,
            storage_path=str(storage_root),
        )
    except Exception:
        traceback.print_exc()
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(run_anyang_sanzi_export_webview(sys.argv[1:]))
