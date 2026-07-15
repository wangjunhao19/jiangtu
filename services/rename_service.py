# Source Generated with Decompyle++
# File: rename_service.pyc (Python 3.11)

import os
import re


def _iter_jpeg_files(folder_path: str, include_subdirs: bool = False) -> list[str]:
    if include_subdirs:
        out = []
        for root, _, names in os.walk(folder_path):
            for name in names:
                if name.lower().endswith(('.jpg', '.jpeg')):
                    out.append(os.path.join(root, name))
        return sorted(out, key=lambda x: (os.path.dirname(x).lower(), os.path.basename(x).lower()))
    return sorted(
        [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg'))],
        key=lambda x: os.path.basename(x).lower(),
    )


def batch_rename(folder_path: str, start_str: str, include_subdirs: bool = False) -> int:
    if not os.path.isdir(folder_path):
        raise Exception('文件夹不存在')
    files = _iter_jpeg_files(folder_path, include_subdirs=include_subdirs)
    if not files:
        return 0
    match = re.match('^(?P<prefix>[a-zA-Z]*)(?P<num>\\d+)$', start_str.strip())
    if not match:
        raise ValueError('格式错误，示例：A1、0001')
    prefix = match.group('prefix')
    start = int(match.group('num'))
    digit_len = len(match.group('num'))
    count = 0
    for old_full in files:
        ext = os.path.splitext(old_full)[1]
        folder = os.path.dirname(old_full)
        new_name = f'{prefix}{str(start).zfill(digit_len)}{ext}'
        new_full = os.path.join(folder, new_name)
        start += 1
        if old_full == new_full or os.path.exists(new_full):
            continue
        if old_full != new_full:
            os.rename(old_full, new_full)
            count += 1
    return count
