from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

_PUBLIC_KEY_PEM = (
    b'-----BEGIN PUBLIC KEY-----\n'
    b'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzSS1Cxr0PDTvjxbqRov\n'
    b'ajcRlVdgbZ67meLFPoS0347Z46id0pT5D6sgYtKVED0KVGcoRvTDrOALbUAdCI58\n'
    b'2YSIKynVcMIiFufbUpwLD6G/6pQbWdba9rcHlPmw8/RIGtp4xPS9vJZIWWIxT6jL\n'
    b'/6tdooQgBvg/X/Pbc4mr8nl3qyVABeVaAAhzUwuZrOihcb1BIAee7XhyaWT3Ddbd\n'
    b'SjrjWUtoj9Fs+E+m1oR3uXIc0jggJUAO7iJDP+pHygpEHsobBpiWcRLygR7+xWa4\n'
    b'tlIW/ImkRFHIFGbrNoV07pDB/eDgb+b+aAKm3iNS7QS/mjA82WBIgcG0yabPFoiq\n'
    b'8wIDAQAB\n'
    b'-----END PUBLIC KEY-----\n'
)
_MARKER_PREFIX = 'JTTRACE1:'


def _short_hash(value: str, length: int = 16) -> str:
    if not value:
        return ''
    return hashlib.sha256(value.encode('utf-8', errors='ignore')).hexdigest()[:length]


def create_output_trace(context: str = 'output') -> str:
    """生成只能由开发者私钥解码的短标记；失败时返回空串，不影响正常输出。"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from services.license_service import (
            get_machine_code,
            get_saved_customer,
            get_saved_license_key,
            get_saved_phone,
        )

        customer = str(get_saved_customer() or '')[:28]
        phone = str(get_saved_phone() or '')[:20]
        license_key = str(get_saved_license_key() or '')
        machine_code = str(get_machine_code() or '')

        payload = {
            'v': 1,
            'c': customer,
            'p': phone,
            'l': _short_hash(license_key),
            'm': _short_hash(machine_code),
            't': int(time.time()),
            'o': str(context or 'output')[:24],
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        if len(raw) > 185:
            payload['c'] = customer[:12]
            payload['p'] = phone[-4:]
            payload['o'] = str(context or 'output')[:10]
            raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        public_key = serialization.load_pem_public_key(_PUBLIC_KEY_PEM)
        encrypted = public_key.encrypt(
            raw,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return _MARKER_PREFIX + base64.urlsafe_b64encode(encrypted).decode('ascii').rstrip('=') + ':END'
    except Exception:
        return ''


def append_kml_trace(kml_text: str, context: str = '') -> str:
    marker = create_output_trace(context)
    if not marker:
        return kml_text
    comment = f'<!--{marker}-->'
    if '</Document>' in kml_text:
        return kml_text.replace('</Document>', comment + '</Document>', 1)
    return kml_text + comment


def add_trace_to_report(report: dict[str, Any], context: str = '') -> dict[str, Any]:
    marker = create_output_trace(context)
    if marker:
        report = dict(report)
        report['jt_trace'] = marker
    return report
