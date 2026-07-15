from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from utils.webview_icon import apply_windows_titlebar_icon_async

DEFAULT_LOGIN_URL: str = 'http://222.143.69.159:38590/dist/#/login'
DEFAULT_BASE_URL: str = 'http://222.143.69.159:38762'


def _parse_json(value: Any = None) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _merge_identity(result: Dict[str, str], value: Any) -> None:
    value = _parse_json(value)
    if isinstance(value, dict):
        for key, item in value.items():
            low = str(key).lower()
            if low in {'districtcode', 'distinctcode'} and item and not result.get('districtcode'):
                result['districtcode'] = str(item)
            elif low in {'distinctname', 'districtname'} and item and not result.get('districtname'):
                result['districtname'] = str(item)
            elif low in {'name', 'username', 'loginname'} and item and not result.get('username'):
                result['username'] = str(item)
            elif low in {'level', 'userlevel'} and item and not result.get('userlevel'):
                result['userlevel'] = str(item)
            elif low == 'tokenname' and item and not result.get('token_header'):
                result['token_header'] = str(item)
            elif low in {'token', 'tokenvalue', 'accesstoken', 'access_token'} and item and not result.get('token'):
                result['token'] = str(item)
            _merge_identity(result, item)
    elif isinstance(value, list):
        for item in value:
            _merge_identity(result, item)


def _atomic_write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def _write_status(path: Path | None, phase: str, message: str, **extra: Any) -> None:
    payload = {
        'phase': phase,
        'message': message,
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'pid': os.getpid(),
    }
    payload.update(extra)
    try:
        _atomic_write_json(path, payload)
    except Exception:
        pass


def _log_path() -> Path:
    local = os.getenv('LOCALAPPDATA') or os.getenv('APPDATA') or str(Path.home())
    path = Path(local) / 'JiangTu' / 'logs' / 'sanzi_login_webview.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_log(message: str) -> None:
    try:
        with _log_path().open('a', encoding='utf-8', errors='replace') as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def _extract_login_state(window: Any, login_url: str, base_url: str) -> Dict[str, str]:
    script = """
    (function () {
      function get(storage, key) {
        try { return storage.getItem(key) || ''; } catch (e) { return ''; }
      }
      return JSON.stringify({
        token: get(localStorage, 'token') || get(sessionStorage, 'token'),
        LoginId: get(sessionStorage, 'LoginId') || get(localStorage, 'LoginId'),
        LoginName: get(sessionStorage, 'LoginName') || get(localStorage, 'LoginName'),
        UserName: get(sessionStorage, 'UserName') || get(localStorage, 'UserName'),
        UserLevel: get(sessionStorage, 'UserLevel') || get(localStorage, 'UserLevel'),
        TokenName: get(sessionStorage, 'TokenName') || get(localStorage, 'TokenName'),
        currentDistrictCode: get(sessionStorage, 'currentDistrictCode') || get(localStorage, 'currentDistrictCode'),
        currentDistrictName: get(sessionStorage, 'currentDistrictName') || get(localStorage, 'currentDistrictName'),
        cookie: document.cookie || '',
        href: location.href || '',
        title: document.title || '',
        readyState: document.readyState || ''
      });
    })();
    """
    raw = window.evaluate_js(script)
    data = _parse_json(raw)
    if not isinstance(data, dict):
        data = {}
    parsed = urlparse(login_url)
    result = {
        'login_url': login_url,
        'web_url': f"{parsed.scheme}://{parsed.netloc}",
        'base_url': base_url,
        'token': '',
        'token_header': 'Token',
        'cookie': str(data.get('cookie')) or '',
        'districtcode': str(data.get('currentDistrictCode')) or '',
        'districtname': str(data.get('currentDistrictName')) or '',
        'username': str(data.get('LoginName') or data.get('UserName')) or '',
        'userlevel': str(data.get('UserLevel')) or '',
        'href': str(data.get('href')) or '',
        'page_title': str(data.get('title')) or '',
        'ready_state': str(data.get('readyState')) or '',
        'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    token_value = _parse_json(data.get('token'))
    if isinstance(token_value, dict):
        result['token'] = str(token_value.get('tokenValue') or token_value.get('token')) or ''
        result['token_header'] = str(token_value.get('tokenName') or data.get('TokenName')) or 'Token'
    elif token_value:
        result['token'] = str(token_value).strip('"')
        result['token_header'] = str(data.get('TokenName')) or 'Token'
    _merge_identity(result, data.get('LoginId'))
    _merge_identity(result, token_value)
    if result.get('token', '').lower().startswith('bearer '):
        result['token'] = result['token'].split(' ', 1)[1]
    return result


def _show_success_notice(window: Any) -> None:
    try:
        window.evaluate_js("""
        (function(){
          try {
            var old = document.getElementById('jt-login-success-mask');
            if (old) old.remove();
            var mask = document.createElement('div');
            mask.id = 'jt-login-success-mask';
            mask.style.cssText = 'position:fixed;z-index:2147483647;left:0;top:0;right:0;bottom:0;background:rgba(15,23,42,.72);display:flex;align-items:center;justify-content:center;font-family:Microsoft YaHei,Arial,sans-serif';
            var card = document.createElement('div');
            card.style.cssText = 'width:420px;background:#fff;border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.35);padding:30px;text-align:center;color:#183153';
            card.innerHTML = '<div style="font-size:42px;color:#16a34a">✓</div><div style="font-size:22px;font-weight:700;margin-top:8px">登录状态已同步</div><div style="font-size:14px;color:#64748b;margin-top:12px;line-height:1.7">正在返回三资材料工作台，请稍候……<br>这是正常关闭，不是网页闪退。</div>';
            mask.appendChild(card); document.body.appendChild(mask);
          } catch(e) {}
          return true;
        })();
        """)
    except Exception:
        pass


def _prepare_storage_root(fresh_login: bool, safe_rendering: bool) -> Path:
    jt_root = Path(os.getenv('APPDATA') or Path.home()) / 'JiangTu'
    jt_root.mkdir(parents=True, exist_ok=True)
    storage_root = jt_root / ('sanzi_webview_safe' if safe_rendering else 'sanzi_webview')
    if fresh_login:
        try:
            shutil.rmtree(storage_root, ignore_errors=True)
        except Exception:
            pass
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def run_sanzi_login_webview(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--jt-sanzi-login', action='store_true')
    parser.add_argument('--result-file', required=True)
    parser.add_argument('--status-file', default='')
    parser.add_argument('--login-url', default=DEFAULT_LOGIN_URL)
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    parser.add_argument('--fresh-login', action='store_true')
    parser.add_argument('--safe-rendering', action='store_true')
    args, _ = parser.parse_known_args(argv)

    result_path = Path(args.result_file)
    status_path = Path(args.status_file) if args.status_file else None
    result_path.parent.mkdir(parents=True, exist_ok=True)

    for path in (result_path, status_path):
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    _write_status(status_path, 'starting', '正在初始化官方平台登录窗口',
                  safe_rendering=bool(args.safe_rendering))
    _append_log(
        f"启动登录窗口 fresh={bool(args.fresh_login)}"
        f" safe={bool(args.safe_rendering)}"
        f" url={args.login_url}"
    )

    if args.safe_rendering:
        existing = os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '').strip()
        safe_args = '--disable-gpu --disable-gpu-compositing --disable-features=UseSkiaRenderer'
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (existing + ' ' + safe_args).strip()

    try:
        import webview
    except Exception as exc:
        _write_status(status_path, 'exception', f'无法加载网页组件：{exc}')
        _append_log('导入pywebview失败：' + traceback.format_exc())
        return 21

    storage_root = _prepare_storage_root(bool(args.fresh_login), bool(args.safe_rendering))
    title = '疆途·智能巡查管理平台 V1.0｜官方三资平台登录（请输入验证码）'
    stop = threading.Event()
    success = threading.Event()
    loaded_once = threading.Event()
    fresh_state = {'cleared': False, 'monitor_started': False}

    try:
        window = webview.create_window(
            title,
            args.login_url,
            width=1260,
            height=820,
            min_size=(960, 650),
            confirm_close=False,
            easy_drag=False,
        )
        _write_status(status_path, 'window_created', '登录窗口已创建',
                      storage_path=str(storage_root))
        apply_windows_titlebar_icon_async(title)
    except Exception as exc:
        _write_status(status_path, 'exception', f'创建登录窗口失败：{exc}')
        _append_log('创建登录窗口失败：' + traceback.format_exc())
        return 22

    def monitor() -> None:
        time.sleep(1.2)
        last_error = ''
        last_token = ''
        stable_hits = 0
        while not stop.is_set():
            try:
                state = _extract_login_state(window, args.login_url, args.base_url)
                state['fresh_login'] = bool(args.fresh_login)
                state['safe_rendering'] = bool(args.safe_rendering)
                state['storage_session'] = storage_root.name
                token = str(state.get('token') or '').strip()
                href = str(state.get('href') or '').strip().lower()
                still_on_login_page = ('#/login' in href) or href.rstrip('/').endswith('/login')
                if len(token) >= 12 and not still_on_login_page:
                    stable_hits = stable_hits + 1 if token == last_token else 1
                    last_token = token
                    if stable_hits >= 2:
                        _atomic_write_json(result_path, state)
                        success.set()
                        _write_status(
                            status_path,
                            'success',
                            '登录状态已同步，窗口即将正常关闭',
                            href=state.get('href', ''),
                            safe_rendering=bool(args.safe_rendering),
                        )
                        _append_log('登录状态捕获成功，准备平滑关闭登录窗口。')
                        try:
                            _show_success_notice(window)
                            window.set_title('登录成功｜正在返回三资材料工作台')
                        except Exception:
                            pass
                        time.sleep(2.0)
                        try:
                            window.destroy()
                        except Exception:
                            pass
                        return
                else:
                    stable_hits = 0
                    last_token = ''
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.8)
        if last_error and not result_path.exists():
            try:
                result_path.with_suffix('.error.txt').write_text(last_error, encoding='utf-8')
            except Exception:
                pass

    def on_loaded() -> None:
        loaded_once.set()
        apply_windows_titlebar_icon_async(title)
        _write_status(status_path, 'page_loaded', '官方平台页面已加载',
                      safe_rendering=bool(args.safe_rendering))
        if args.fresh_login and not fresh_state['cleared']:
            fresh_state['cleared'] = True
            try:
                window.evaluate_js("""
                (function(){
                  try { localStorage.clear(); } catch(e) {}
                  try { sessionStorage.clear(); } catch(e) {}
                  try {
                    document.cookie.split(';').forEach(function(c){
                      document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date(0).toUTCString() + ';path=/');
                    });
                  } catch(e) {}
                  setTimeout(function(){ location.replace(%s); }, 180);
                  return true;
                })();
                """ % json.dumps(args.login_url))
                return None
            except Exception as exc:
                _append_log(f'清理切换账号网页缓存失败，继续登录：{exc}')
        if not fresh_state['monitor_started']:
            fresh_state['monitor_started'] = True
            threading.Thread(target=monitor, daemon=True, name='sanzi-login-monitor').start()

    def on_closed() -> None:
        stop.set()
        if success.is_set() or result_path.exists():
            return None
        phase = 'user_closed' if loaded_once.is_set() else 'webview_closed_early'
        message = '用户关闭了登录窗口' if loaded_once.is_set() else '网页组件在页面加载前退出'
        _write_status(status_path, phase, message, safe_rendering=bool(args.safe_rendering))
        _append_log(message)

    window.events.loaded += on_loaded
    window.events.closed += on_closed

    try:
        _write_status(status_path, 'webview_starting', '正在启动WebView2',
                      safe_rendering=bool(args.safe_rendering))
        try:
            webview.start(
                gui='edgechromium' if os.name == 'nt' else None,
                debug=False,
                private_mode=False,
                storage_path=str(storage_root),
            )
        except TypeError:
            try:
                webview.start(debug=False, storage_path=str(storage_root))
            except TypeError:
                webview.start(debug=False)
    except Exception as exc:
        _write_status(status_path, 'exception', f'网页组件运行失败：{exc}',
                      safe_rendering=bool(args.safe_rendering))
        _append_log('WebView2运行异常：\n' + traceback.format_exc())
        stop.set()
        return 23
    finally:
        stop.set()

    return 0 if result_path.exists() else 10


if __name__ == '__main__':
    raise SystemExit(run_sanzi_login_webview())
