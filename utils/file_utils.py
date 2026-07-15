# Source Generated with Decompyle++
# File: file_utils.pyc (Python 3.11)

import os
import platform
import subprocess

def open_file(path = None):
    '''跨平台打开文件。'''
    system = platform.system()
    if system == 'Windows':
        os.startfile(path)
        return None
    if system == 'Darwin':
        subprocess.run([
            'open',
            path], check = False)
        return None
    subprocess.run([
        'xdg-open',
        path], check = False)

