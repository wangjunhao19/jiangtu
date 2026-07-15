# Source Generated with Decompyle++
# File: license_service.pyc (Python 3.11)

import hashlib
import json
import os
import platform
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import requests
from config import ONLINE_ACTIVATION_FILE, ONLINE_LICENSE_SERVER
BASE_MODULE = 'base'
MISSION_MODULE = 'mission'
MODULE_NAMES = {
    'all': '全部功能',
    MISSION_MODULE: '航线规划功能',
    BASE_MODULE: '基础功能',
    'ai_classify': 'AI 智能分类',
    'mission_planner': '航线规划器',
    'sanzi_export': '三资平台导出' }
CLIENT_AUTH_VERSION = '1.0'
AUTH_POLICY_VERSION = 'jt-auth-2026.06'
EXPORT_GATE_VERSION = 'export-gate-1.3-audit'
ACTION_GATE_VERSION = 'action-gate-1.0'
REQUEST_TIMEOUT = (5, 15)
CORE_ROUTE_REQUEST_TIMEOUT = (5, 90)
CLOCK_SKEW_SECONDS = 600
_HEARTBEAT_THREAD: threading.Thread | None = None
_HEARTBEAT_STOP = threading.Event()
_MACHINE_CODE_CACHE: str | None = None
_AUTH_CACHE_DATA: dict = { }
_AUTH_CACHE_TIME: float = 0
AUTH_CACHE_SECONDS = 180
ACCEPTED_SCHEMA_VERSIONS = {
    '1.0',
    '1.3.1',
    '1.3.2',
    '1.3.3',
    '1.3.4',
    '1.3.6',
    '1.4.1'}
_INVALID_HW_VALUES = {
    'n/a',
    'not available',
    'not specified',
    'default string',
    'to be filled by oem',
    'system serial number',
    'to be filled by o.e.m.',
    'base board serial number',
    '00000000-0000-0000-0000-000000000000',
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    '',
    '0',
    'na',
    'none',
    'null',
    'unknown'}


def _app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _activation_path() -> Path:
    path = Path(ONLINE_ACTIVATION_FILE)
    if not path.is_absolute():
        path = _app_dir() / path
    return path


def _legacy_activation_path() -> Path:
    return _app_dir() / 'online_activation.json'


def _run_cmd(cmd: str = None, timeout: int = None) -> str:
    '''静默执行系统命令，兼容 PyInstaller 无控制台模式。'''
    kwargs = {
        'shell': True,
        'text': True,
        'stderr': subprocess.DEVNULL,
        'stdin': subprocess.DEVNULL,
        'timeout': timeout }
    if platform.system() == 'Windows':
        kwargs['creationflags'] = 134217728
    return subprocess.check_output(cmd, **kwargs).strip()


def _clean_hw_value(value: str = None) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub('\\s+', ' ', text)
    if '=' in text and len(text.split('=', 1)[0]) < 40:
        text = text.split('=', 1)[1].strip()
    low = text.strip().lower()
    if low in _INVALID_HW_VALUES:
        return ''
    only = re.sub('[^0-9a-fA-F]', '', text)
    if only and (set(only) <= {'0'} or set(only.lower()) <= {'f'}):
        return ''
    if len(only) < 6 and not re.search('[A-Za-z]{3,}', text):
        return ''
    return text


def _collect_from_command(parts: list[str], label: str, cmd: str, *, lines: bool = True) -> None:
    try:
        out = _run_cmd(cmd)
    except Exception:
        return None
    if not out:
        return None
    values = out.splitlines() if lines else [out]
    for value in values:
        cleaned = _clean_hw_value(value)
        if cleaned:
            parts.append(f'{label}:{cleaned}')
    return None


def _collect_mac(parts: list[str]) -> None:
    system = platform.system()
    cmds = []
    if system == 'Windows':
        cmds = ['getmac /fo csv /nh', 'ipconfig /all']
    else:
        cmds = ['ip link', 'ifconfig -a']
    for cmd in cmds:
        try:
            out = _run_cmd(cmd)
        except Exception:
            continue
        for mac in re.findall('(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}', out or ''):
            mac2 = mac.replace('-', ':').lower()
            if mac2 not in {'00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff'}:
                parts.append(f'MAC:{mac2}')
        if parts:
            return None
    return None


def _collect_windows_hardware_fast(parts: list[str]) -> None:
    '''一次 PowerShell 调用读主要硬件信息，避免多次启动 wmic/PowerShell 卡顿。'''
    ps_lines = [
        "$ErrorActionPreference='SilentlyContinue'",
        "$cs=Get-CimInstance Win32_ComputerSystemProduct; if($cs.UUID){'CS_UUID=' + $cs.UUID}",
        "$bios=Get-CimInstance Win32_BIOS; if($bios.SerialNumber){'BIOS_SN=' + $bios.SerialNumber}",
        "$bb=Get-CimInstance Win32_BaseBoard; if($bb.SerialNumber){'BOARD_SN=' + $bb.SerialNumber}",
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1; if($cpu.ProcessorId){'CPU_ID=' + $cpu.ProcessorId}",
        '$os=Get-CimInstance Win32_OperatingSystem; $sys=$os.SystemDrive; $ld=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID=\'$sys\'"; if($ld){$part=Get-CimAssociatedInstance -InputObject $ld -Association Win32_LogicalDiskToPartition | Select-Object -First 1; if($part){$disk=Get-CimAssociatedInstance -InputObject $part -Association Win32_DiskDriveToDiskPartition | Select-Object -First 1; if($disk.SerialNumber){\'SYS_DISK_SN=\' + $disk.SerialNumber}}}'
    ]
    ps_script = '; '.join(ps_lines)
    cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "' + ps_script.replace('"', '\\"') + '"'
    try:
        out = _run_cmd(cmd, timeout=8)
    except Exception:
        return None
    for line in (out or '').splitlines():
        if '=' not in line:
            continue
        label, value = line.split('=', 1)
        label = re.sub('[^A-Za-z0-9_]', '', label).strip() or 'HW'
        cleaned = _clean_hw_value(value)
        if cleaned:
            parts.append(f'{label}:{cleaned}')
    return None


def get_machine_code() -> str:
    '''
    读取稳定本机硬件识别码。

    速度优化：
    - 本次运行只读取一次硬件信息，后续授权、保存、心跳直接使用内存缓存；
    - Windows 优先使用一次 PowerShell CIM 合并读取，避免多次启动 wmic/PowerShell 卡顿；
    - 读取不到有效硬件信息仍然返回空字符串，继续严格禁止登录。
    '''
    global _MACHINE_CODE_CACHE
    if _MACHINE_CODE_CACHE:
        return _MACHINE_CODE_CACHE
    inherited = str(os.environ.get('JT_PARENT_MACHINE_CODE', '')).strip().lower()
    if re.fullmatch('[0-9a-f]{32,64}', inherited):
        _MACHINE_CODE_CACHE = inherited[:32]
        return _MACHINE_CODE_CACHE
    system = platform.system()
    parts = []
    if system == 'Windows':
        _collect_windows_hardware_fast(parts)
        if len(set(parts)) < 2:
            commands = [
                ('CS_UUID', 'wmic csproduct get UUID /value'),
                ('BIOS_SN', 'wmic bios get SerialNumber /value'),
                ('BOARD_SN', 'wmic baseboard get SerialNumber /value'),
                ('CPU_ID', 'wmic cpu get ProcessorId /value'),
                ('SYS_DISK_SN', "wmic logicaldisk where DeviceID='%SystemDrive%' get VolumeSerialNumber /value"),
            ]
            for label, cmd in commands:
                try:
                    out = _run_cmd(cmd, timeout=3)
                except Exception:
                    continue
                for value in out.splitlines():
                    cleaned = _clean_hw_value(value)
                    if cleaned:
                        parts.append(f'{label}:{cleaned}')
        if len(set(parts)) < 2:
            _collect_mac(parts)
    else:
        commands = [
            ('MACHINE_ID', 'cat /etc/machine-id'),
            ('BOARD_SN', 'cat /sys/class/dmi/id/board_serial'),
            ('PRODUCT_UUID', 'cat /sys/class/dmi/id/product_uuid'),
            ('BIOS_SN', 'cat /sys/class/dmi/id/product_serial'),
        ]
        for label, cmd in commands:
            _collect_from_command(parts, label, cmd)
        _collect_mac(parts)
    unique = sorted(set(_clean_hw_value(p.split(':', 1)[-1]) for p in parts if _clean_hw_value(p.split(':', 1)[-1])))
    if not unique:
        return ''
    raw = '|'.join(unique).lower()
    _MACHINE_CODE_CACHE = hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:32]
    return _MACHINE_CODE_CACHE


def _machine_code_or_error() -> tuple[bool, str]:
    code = get_machine_code()
    if not code:
        return (False, '无法读取本机硬件ID，软件禁止登录。请以管理员身份运行，或检查系统硬件信息读取权限。')
    return (True, code)


def _normalize_modules(modules: Any) -> list[str]:
    if modules is None:
        return []
    if isinstance(modules, str):
        try:
            parsed = json.loads(modules)
            modules = parsed if isinstance(parsed, list) else [modules]
        except Exception:
            modules = [x.strip() for x in modules.replace('，', ',').split(',') if x.strip()]
    out = []
    for m in modules:
        m = str(m).strip().lower()
        if m in ('all', 'full', '全功能', '航线版', '航线规划版'):
            for item in (BASE_MODULE, MISSION_MODULE):
                if item not in out:
                    out.append(item)
        elif m and m not in out:
            out.append(m)
    return out


def _set_auth_cache(data: dict) -> None:
    global _AUTH_CACHE_DATA, _AUTH_CACHE_TIME
    _AUTH_CACHE_DATA = dict(data or {})
    _AUTH_CACHE_TIME = time.time()
    return None


def _get_recent_auth_cache() -> dict:
    if _AUTH_CACHE_DATA and time.time() - _AUTH_CACHE_TIME <= AUTH_CACHE_SECONDS:
        return dict(_AUTH_CACHE_DATA)
    return {}


def _cached_result_for_module(required_module: str = BASE_MODULE) -> tuple[bool, str, str] | None:
    data = _get_recent_auth_cache()
    if not data:
        return None
    modules = _normalize_modules(data.get('modules'))
    if required_module and required_module not in modules:
        return (False, f'当前登录用户未开通{MODULE_NAMES.get(required_module, required_module)}', '')
    return (True, _format_detail('在线授权有效', data, customer=str(data.get('customer', ''))), 'online')


def _server_url() -> str:
    return ONLINE_LICENSE_SERVER.rstrip('/')


def _normalize_phone(phone: str) -> str:
    return re.sub('\\D+', '', phone or '')


def validate_phone(phone: str) -> tuple[bool, str]:
    p = _normalize_phone(phone)
    if not p:
        return (False, '请输入手机号')
    if len(p) != 11 or not p.startswith('1'):
        return (False, '请输入11位中国大陆手机号')
    return (True, p)


def validate_customer(customer: str) -> tuple[bool, str]:
    name = (customer or '').strip()
    if not name:
        return (False, '请输入姓名')
    if len(name) < 2:
        return (False, '姓名至少填写2个字符')
    return (True, name)


def _attach_client_clock(payload: dict) -> dict:
    '''每次授权请求都提交本机时间戳，服务器据此识别电脑时间被人为修改的情况。'''
    data = dict(payload or {})
    data['client_timestamp'] = int(time.time())
    data['client_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return data


def _verify_server_clock(data: dict) -> tuple[bool, str]:
    '''授权结果必须带服务器时间，客户端不得单独相信本机时间。'''
    server_ts = data.get('server_timestamp')
    if server_ts is None:
        return (False, '授权服务器未返回服务器时间，请先更新服务器端 app.py 后再登录。')
    try:
        server_ts_f = float(server_ts)
    except Exception:
        return (False, '授权服务器返回的时间格式异常，请检查服务器端 app.py。')
    diff = abs(time.time() - server_ts_f)
    if diff > CLOCK_SKEW_SECONDS:
        minutes = max(1, int(CLOCK_SKEW_SECONDS / 60))
        return (False, f'本机时间与授权服务器时间相差超过 {minutes} 分钟，授权已拒绝。请开启系统自动同步时间后重试。')
    return (True, '')


def _post_json(path: str, payload: dict, *, timeout=None, timeout_message='连接在线服务器超时。为防止未授权使用，超时状态禁止进入软件。') -> tuple[bool, str, dict]:
    url = f'{_server_url()}{path}'
    payload = _attach_client_clock(payload)
    request_timeout = REQUEST_TIMEOUT if timeout is None else timeout
    try:
        response = requests.post(url, payload, timeout=request_timeout)
        if response.status_code == 404:
            return (False, '服务器接口版本不匹配，请升级疆途授权服务器并重启。', {})
        response.raise_for_status()
        try:
            data = response.json()
        except Exception:
            return (False, '服务器返回内容不是有效JSON，请检查服务器程序。', {})
    except requests.exceptions.ConnectionError:
        return (False, '无法连接在线服务器。为防止未授权使用，离线状态禁止进入软件。请检查服务器地址和网络连接。', {})
    except requests.exceptions.Timeout:
        return (False, timeout_message, {})
    except Exception as e:
        return (False, f'在线服务器请求失败，禁止进入软件：{e}', {})
    if not data.get('success'):
        return (False, str(data.get('message') or '服务器拒绝授权'), data)
    ok_clock, clock_msg = _verify_server_clock(data)
    if not ok_clock:
        return (False, clock_msg, data)
    policy = str(data.get('auth_policy_version') or '').strip()
    if policy != AUTH_POLICY_VERSION:
        return (False, f'授权服务器安全策略版本不匹配。请先部署本版本服务器替换文件并重启服务，客户端要求：{AUTH_POLICY_VERSION}，服务器返回：{policy or "未返回"}。', data)
    return (True, str(data.get('message') or '登录成功'), data)


def _request_customer_login(customer: str, phone: str) -> tuple[bool, str, dict]:
    ok_name, name_or_msg = validate_customer(customer)
    if not ok_name:
        return (False, name_or_msg, {})
    ok_phone, phone_or_msg = validate_phone(phone)
    if not ok_phone:
        return (False, phone_or_msg, {})
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/customer_login', {
        'customer': name_or_msg,
        'phone': phone_or_msg,
        'machine_code': machine_or_msg,
        'client_version': CLIENT_AUTH_VERSION })


def _request_customer_check(license_key: str = '', phone: str = '', customer: str = '') -> tuple[bool, str, dict]:
    key = (license_key or '').strip()
    p = _normalize_phone(phone)
    if not key and not p:
        return (False, '请先输入姓名和手机号登录', {})
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/check_customer', {
        'license_key': key,
        'customer': (customer or '').strip(),
        'phone': p,
        'machine_code': machine_or_msg,
        'session_id': get_saved_session_id(),
        'client_version': CLIENT_AUTH_VERSION })


def _request_check(license_key: str) -> tuple[bool, str, dict]:
    '''兼容旧接口。V1.3 客户端正常不再主动使用授权码。'''
    key = (license_key or '').strip()
    if not key:
        return (False, '请重新填写姓名和手机号登录', {})
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/check_license', {
        'license_key': key,
        'machine_code': machine_or_msg,
        'client_version': CLIENT_AUTH_VERSION })


def request_core_route_order(points: list[dict], mode: str = 'shortest', takeoff: dict | None = None) -> tuple[bool, str, dict]:
    '''核心航线排序必须由服务器完成，每次核验机器码、会话、有效期和航线模块。'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/core/route_order', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': str(mode or 'shortest'),
        'mode': str(mode or 'shortest'),
        'points': list(points or []),
        'takeoff': takeoff if isinstance(takeoff, dict) else None },
        timeout=CORE_ROUTE_REQUEST_TIMEOUT,
        timeout_message='服务器正在计算航线，但在90秒内未返回结果。授权状态仍然有效，请稍后重试或减少单次航点数量。')


def request_mission_export_authorization(filename: str = '', file_size: int = 0, file_sha256: str = '', export_type: str = 'mission', semantic_sha256: str = '', waypoint_count: int = 0, fingerprint_engine: str = '') -> tuple[bool, str, dict]:
    '''航线在本机计算；保存任何任务文件前由服务器核验会话和航线模块。'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    ok, message, result = _post_json('/api/core/export_authorize', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': CLIENT_AUTH_VERSION,
        'filename': str(filename or ''),
        'file_size': int(file_size or 0),
        'file_sha256': str(file_sha256 or '').strip().lower(),
        'export_type': str(export_type or 'mission'),
        'semantic_sha256': str(semantic_sha256 or '').strip().lower(),
        'waypoint_count': int(waypoint_count or 0),
        'fingerprint_engine': str(fingerprint_engine or '') },
        timeout=(5, 15),
        timeout_message='连接导出授权服务器超时。本地航线不会丢失，请检查网络后重新点击导出。')
    if ok and str(result.get('export_gate_version') or '').strip() != EXPORT_GATE_VERSION:
        return (False, '服务器导出签名版本不匹配，请先部署新版服务器文件。', result)
    return (ok, message, result)


def consume_mission_export_ticket(export_ticket: str = '', filename: str = '', file_size: int = 0, file_sha256: str = '', export_type: str = 'mission', semantic_sha256: str = '', waypoint_count: int = 0, fingerprint_engine: str = '') -> tuple[bool, str, dict]:
    '''Consume the short-lived signed ticket exactly once before writing the local file.'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    ok, message, result = _post_json('/api/core/export_consume', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': CLIENT_AUTH_VERSION,
        'filename': str(filename or ''),
        'file_size': int(file_size or 0),
        'file_sha256': str(file_sha256 or '').strip().lower(),
        'export_type': str(export_type or 'mission'),
        'semantic_sha256': str(semantic_sha256 or '').strip().lower(),
        'waypoint_count': int(waypoint_count or 0),
        'fingerprint_engine': str(fingerprint_engine or ''),
        'export_ticket': str(export_ticket or '').strip() },
        timeout=(5, 15),
        timeout_message='连接导出签名服务器超时。本地航线不会丢失，请检查网络后重新点击导出。')
    if ok and str(result.get('export_gate_version') or '').strip() != EXPORT_GATE_VERSION:
        return (False, '服务器导出签名版本不匹配，请先部署新版服务器文件。', result)
    return (ok, message, result)


def request_action_authorization(action_type: str = '', context_hash: str = '') -> tuple[bool, str, dict]:
    '''向服务器请求操作授权凭证。'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/core/action_authorize', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': CLIENT_AUTH_VERSION,
        'action_type': action_type,
        'context_hash': context_hash })


def consume_action_ticket(action_ticket: str = '', action_type: str = '', context_hash: str = '') -> tuple[bool, str, dict]:
    '''向服务器消费操作凭证（一次性）。'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/core/action_consume', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': CLIENT_AUTH_VERSION,
        'action_ticket': action_ticket,
        'action_type': action_type,
        'context_hash': context_hash })


def authorize_formal_action(action_type: str = '', context_hash: str = '') -> tuple[bool, str, dict]:
    '''正式操作授权快捷通道（规格书 4.3）。'''
    data = _load_activation()
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/core/action_formal', {
        'license_key': str(data.get('license_key', '')).strip(),
        'phone': _normalize_phone(str(data.get('phone', ''))),
        'machine_code': machine_or_msg,
        'session_id': str(data.get('session_id', '')).strip(),
        'client_version': CLIENT_AUTH_VERSION })


def _request_activate(license_key: str = '', phone: str = '', customer: str = '') -> tuple[bool, str, dict]:
    '''兼容旧函数。无授权码时走姓名手机号在线登录。'''
    key = (license_key or '').strip()
    if not key:
        return _request_customer_login(customer, phone)
    ok_phone, phone_or_msg = validate_phone(phone)
    if not ok_phone:
        return (False, phone_or_msg, {})
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return (False, machine_or_msg, {})
    return _post_json('/api/activate', {
        'license_key': key,
        'machine_code': machine_or_msg,
        'phone': phone_or_msg,
        'customer': (customer or '').strip(),
        'client_version': CLIENT_AUTH_VERSION })


def _save_activation(license_key: str, data: dict, phone: str = '', customer: str = '') -> None:
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        raise RuntimeError(machine_or_msg)
    phone = _normalize_phone(phone or data.get('phone', ''))
    customer = (customer or data.get('customer', '')).strip()
    payload = {
        'schema_version': CLIENT_AUTH_VERSION,
        'login_mode': 'name_phone_online_strict',
        'license_key': (license_key or data.get('license_key', '')).strip(),
        'machine_code': machine_or_msg,
        'server': _server_url(),
        'customer': customer,
        'phone': phone,
        'expire_date': data.get('expire_date', ''),
        'modules': _normalize_modules(data.get('modules')),
        'machine_locked': bool(data.get('machine_locked', True)),
        'session_id': str(data.get('session_id', '')).strip(),
        'last_ip': data.get('last_ip', ''),
        'login_count': data.get('login_count', ''),
        'last_check': data.get('server_time', ''),
        'server_timestamp': data.get('server_timestamp', ''),
        'auth_policy_version': data.get('auth_policy_version', ''),
        'client_timestamp': int(time.time()) }
    path = _activation_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)
    _set_auth_cache(payload)
    return None


def _load_activation() -> dict:
    path = _activation_path()
    if not path.exists():
        legacy = _legacy_activation_path()
        if legacy.exists() and legacy != path:
            try:
                data = json.loads(legacy.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    return data
            except Exception:
                pass
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_saved_license_key() -> str:
    data = _load_activation()
    if str(data.get('schema_version', '')) not in ACCEPTED_SCHEMA_VERSIONS:
        return ''
    return str(data.get('license_key', '')).strip()


def get_saved_phone() -> str:
    data = _load_activation()
    if str(data.get('schema_version', '')) not in ACCEPTED_SCHEMA_VERSIONS:
        return ''
    return str(data.get('phone', '')).strip()


def get_saved_customer() -> str:
    data = _load_activation()
    if str(data.get('schema_version', '')) not in ACCEPTED_SCHEMA_VERSIONS:
        return ''
    return str(data.get('customer', '')).strip()


def get_saved_session_id() -> str:
    data = _load_activation()
    if str(data.get('schema_version', '')) not in ACCEPTED_SCHEMA_VERSIONS:
        return ''
    return str(data.get('session_id', '')).strip()


def _format_detail(prefix: str = '', data: dict = {}, customer: str = '') -> str:
    expire = data.get('expire_date', '')
    customer_name = customer or data.get('customer', '')
    detail = prefix
    if expire:
        detail += f'｜有效期：{expire}'
    if customer_name:
        detail += f'｜用户：{customer_name}'
    return detail


def login_online(customer: str = BASE_MODULE, phone: str = '', required_module: str | None = None) -> tuple[bool, str, str]:
    '''在线登录：向服务器验证客户身份并保存激活缓存。'''
    ok, msg, data = _request_customer_login(customer, phone)
    if not ok:
        return (False, msg, '')
    _save_activation(data.get('license_key', ''), data, phone=data.get('phone', phone), customer=data.get('customer', customer))
    # 检查模块权限
    if required_module:
        modules = _normalize_modules(data.get('modules'))
        if required_module not in modules:
            return (False, f'当前登录用户未开通{MODULE_NAMES.get(required_module, required_module)}', '')
    detail = _format_detail('在线登录成功', data, customer=data.get('customer', customer))
    return (True, detail, 'online')


def activate_online(license_key='', phone='', customer='', required_module: str | None = None) -> tuple[bool, str, str]:
    '''在线激活：使用授权码激活并保存缓存。'''
    ok, msg, data = _request_activate(license_key, phone, customer)
    if not ok:
        return (False, msg, '')
    _save_activation(data.get('license_key', license_key), data, phone=phone, customer=customer)
    detail = _format_detail('激活成功', data, customer=customer)
    return (True, detail, 'online')


def check_online_cached_license(required_module: str = BASE_MODULE) -> tuple[bool, str, str]:
    '''检查在线缓存授权：优先使用三分钟缓存，过期则向服务器重新校验。'''
    cached = _cached_result_for_module(required_module)
    if cached:
        return cached
    # 缓存过期，向服务器重新校验
    data = _load_activation()
    if not data:
        return (False, '未登录，请先登录后再校验授权。', '')
    ok, msg, result = _request_customer_check(
        license_key=data.get('license_key', ''),
        phone=data.get('phone', ''),
        customer=data.get('customer', ''))
    if not ok:
        return (False, msg, '')
    _set_auth_cache(result)
    modules = _normalize_modules(result.get('modules'))
    if required_module and required_module not in modules:
        return (False, f'当前登录用户未开通{MODULE_NAMES.get(required_module, required_module)}', '')
    detail = _format_detail('在线授权有效', result, customer=result.get('customer', ''))
    return (True, detail, 'online')


def send_heartbeat(license_key: str | None = None) -> bool:
    '''向服务器发送心跳，维持会话在线状态。'''
    data = _load_activation()
    if not data:
        return False
    session_id = str(data.get('session_id', '')).strip()
    if not session_id:
        return False
    ok_machine, machine_or_msg = _machine_code_or_error()
    if not ok_machine:
        return False
    ok, msg, result = _post_json('/api/heartbeat', {
        'session_id': session_id,
        'machine_code': machine_or_msg,
        'client_version': CLIENT_AUTH_VERSION },
        timeout=(5, 10),
        timeout_message='心跳上报超时')
    if ok:
        # 更新缓存中的最后检查时间
        data['last_check'] = result.get('server_time', '')
        data['server_timestamp'] = result.get('server_timestamp', '')
        _set_auth_cache(data)
    return ok


def start_heartbeat_thread(license_key: str | None = None) -> None:
    global _HEARTBEAT_THREAD
    key = (license_key or get_saved_license_key()).strip()
    if not key:
        return None
    if _HEARTBEAT_THREAD and _HEARTBEAT_THREAD.is_alive():
        return None
    _HEARTBEAT_STOP.clear()
    def worker():
        failures = 0
        while not _HEARTBEAT_STOP.is_set():
            if send_heartbeat(key):
                failures = 0
            else:
                failures += 1
                failures = min(failures, 999)
            _HEARTBEAT_STOP.wait(120)
    _HEARTBEAT_THREAD = threading.Thread(target=worker, daemon=True)
    _HEARTBEAT_THREAD.start()
    return None


def stop_heartbeat_thread() -> None:
    _HEARTBEAT_STOP.set()
    return None


def check_local_module_access(required_module: str = BASE_MODULE) -> tuple[bool, str, str]:
    '''本地缓存校验模块权限：优先缓存，过期则在线校验。'''
    data = _load_activation()
    if not data:
        return (False, '未登录，请先登录后再校验模块权限。', '')
    modules = _normalize_modules(data.get('modules'))
    if required_module and required_module not in modules:
        return (False, f'当前登录用户未开通{MODULE_NAMES.get(required_module, required_module)}', '')
    detail = _format_detail('模块授权有效', data, customer=data.get('customer', ''))
    return (True, detail, 'online')


def check_license_file(_license_path: str | None = None) -> tuple[bool, str, str]:
    '''本地缓存授权检查：读取已保存的在线激活缓存，未过期则直接通过。'''
    data = _load_activation()
    if not data:
        return (False, '未登录，请先填写姓名和手机号登录。', '')
    # 检查缓存是否过期（通过 server_timestamp 判断）
    server_ts = data.get('server_timestamp')
    if server_ts:
        try:
            diff = abs(time.time() - float(server_ts))
            if diff > AUTH_CACHE_SECONDS:
                # 缓存已过期，需要重新在线校验
                return check_online_cached_license(BASE_MODULE)
        except (TypeError, ValueError):
            pass
    detail = _format_detail('授权有效', data, customer=data.get('customer', ''))
    return (True, detail, 'online')


def check_mission_license_file(_license_path: str | None = None) -> tuple[bool, str, str]:
    '''本地缓存航线规划模块检查：读取已保存的在线激活缓存。'''
    data = _load_activation()
    if not data:
        return (False, '未登录，请先填写姓名和手机号登录。', '')
    modules = _normalize_modules(data.get('modules'))
    if MISSION_MODULE not in modules:
        return (False, '当前登录用户未开通航线规划功能', '')
    detail = _format_detail('授权有效（航线规划）', data, customer=data.get('customer', ''))
    return (True, detail, 'online')


def check_online_license_now(required_module: str = BASE_MODULE) -> tuple[bool, str, str]:
    '''忽略三分钟内存缓存，立即向服务器重新校验。'''
    global _AUTH_CACHE_TIME
    _AUTH_CACHE_TIME = 0
    return check_online_cached_license(required_module)


def check_mission_license_online_now() -> tuple[bool, str, str]:
    '''立即向服务器检查航线规划权限。'''
    return check_online_license_now(MISSION_MODULE)


def decode_license_file(_license_path: str | None = None) -> dict:
    '''兼容旧工具函数：只返回当前在线登录缓存，不做本地离线授权。'''
    data = _load_activation()
    modules = _normalize_modules(data.get('modules'))
    ok_machine, machine_or_msg = _machine_code_or_error()
    return {
        'online_only': True,
        'strict_online_auth': True,
        'login_mode': 'name_phone_online_strict',
        'server': data.get('server', _server_url()),
        'license_key': data.get('license_key', ''),
        'phone': data.get('phone', ''),
        'customer': data.get('customer', ''),
        'machine_code': machine_or_msg if ok_machine else '',
        'machine_readable': ok_machine,
        'session_id': data.get('session_id', ''),
        'last_ip': data.get('last_ip', ''),
        'expire_date': data.get('expire_date', ''),
        'modules': modules,
        'module_names': [MODULE_NAMES.get(m, m) for m in modules],
        'last_check': data.get('last_check', '') }
