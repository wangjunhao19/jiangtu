# Source Generated with Decompyle++
# File: resources/mission_planner_payload.pyc (Python 3.11)

import os
from pathlib import Path


def get_mission_planner_html() -> str:
    """返回航线规划器 WebView 的 HTML 内容。"""
    html_path = Path(__file__).parent / 'mission_planner.html'
    if html_path.is_file():
        return html_path.read_text(encoding='utf-8')
    return '<html><body><h1>航线规划器资源文件缺失</h1></body></html>'
