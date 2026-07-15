# Source Generated with Decompyle++
# File: config.pyc (Python 3.11)

'''应用配置。生产环境建议用环境变量覆盖敏感配置。'''
import os
from pathlib import Path
APP_NAME = '疆途·智能巡查管理平台 V1.0'
CLIENT_BUILD_ID = 'JT-1.0-20260709'
COMPANY_NAME = '疆途科技'
COMPANY_MAIL = 'alielie9711@163.com'
COMPANY_TEL = '17326266638'
AUTH_SECRET_KEY = os.getenv('GPS_TOOL_AUTH_SECRET', '')
LICENSE_FILE = os.getenv('GPS_TOOL_LICENSE_FILE', 'license.lic')
MISSION_LICENSE_FILE = os.getenv('GPS_TOOL_MISSION_LICENSE_FILE', 'license.lic')
ONLINE_LICENSE_SERVER = os.getenv('JT_LICENSE_SERVER', 'http://106.15.4.125')

def _user_data_file(filename = None):
    '''用户级数据目录，避免安装目录无权限、重启后授权/缓存丢失。'''
    if not os.getenv('APPDATA'):
        pass
    base = os.path.join(str(Path.home()), '.jiangtu')
    data_dir = os.path.join(base, 'JiangTu')
    
    try:
        os.makedirs(data_dir, exist_ok = True)
    except Exception:
        data_dir = os.path.join(os.getcwd(), 'jt_user_data')
        os.makedirs(data_dir, exist_ok = True)

    return os.path.join(data_dir, filename)

ONLINE_ACTIVATION_FILE = os.getenv('JT_ONLINE_ACTIVATION_FILE', _user_data_file('online_activation.json'))
NTP_SERVERS = [
    'http://www.baidu.com',
    'http://www.taobao.com',
    'https://www.ntppool.org']
AMAP_API_KEY = os.getenv('AMAP_API_KEY', '43925f5fbfa59a7e2f4fc1a0e8ce4773')
DEFAULT_CENTER_TEXT = '现场拍照'
DEFAULT_CENTER_FONT_RATIO = 0.1
DEFAULT_CENTER_OPACITY = 0.7
DEFAULT_LEFT_FONT_SIZE = 80
STATUS_CFG = {
    '%270%27': ('未完成地块.kml', 0),
    '%271%27': ('进行中地块.kml', 1),
    '%272%27': ('已完成地块.kml', 2) }
CACHE_FILE = os.getenv('JT_IMAGE_CACHE_FILE', _user_data_file('image_cache.json'))
MAP_HTML_FILE = 'gps_map.html'
TIANDITU_KEY = os.getenv('TIANDITU_KEY', '788a5385938d9d30fff4bc9fe091dfa7')
