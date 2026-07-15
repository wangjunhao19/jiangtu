# Source Generated with Decompyle++
# File: client_integrity_service.pyc (Python 3.11)

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Any

EXPECTED_MISSION_HTML_SHA256 = '13793aafb0be3cfb0894307ff86bc770c0fc41e4b3bcd0e2ecdbc9ecd2d1c36c'
INTEGRITY_VERSION = 'jt-integrity-1.0'


def _user_log_path() -> Path:
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or str(Path.home())
    path = Path(base) / 'JiangTu' / 'logs' / 'integrity.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def check_client_integrity() -> tuple[bool, str, dict[str, Any]]:
    """Verify embedded critical resources before formal output/upload actions.

    The planner HTML is embedded in the executable, so the check works in both source and
    PyInstaller builds. It intentionally does not block only because a non-critical external file
    is missing, reducing false positives on legitimate customer computers.
    """
    details = {'version': INTEGRITY_VERSION}
    try:
        from resources.mission_planner_payload import get_mission_planner_html
        actual = hashlib.sha256(get_mission_planner_html().encode('utf-8')).hexdigest()
        details['mission_html_sha256'] = actual
        expected = str(EXPECTED_MISSION_HTML_SHA256 or '').strip().lower()
        if not expected or expected.lower() == 'to_be_generated':
            return (False, '客户端完整性清单尚未生成，请使用正式V1.0打包文件。', details)
        if actual.lower() != expected:
            return (False, '航线规划核心资源校验失败，请重新安装官方完整版本。', details)
        return (True, '客户端关键资源完整性校验通过', details)
    except Exception as exc:
        details['error'] = str(exc)
        try:
            with open(_user_log_path(), 'a', encoding='utf-8') as f:
                f.write(json.dumps(details, ensure_ascii=False) + '\n')
        except Exception:
            pass
        return (False, f'客户端完整性检查失败：{exc}', details)
