# Source Generated with Decompyle++
# File: geocode_service.pyc (Python 3.11)

import requests
from config import AMAP_API_KEY
_address_cache: dict[(tuple[(float, float)], str)] = { }

def get_address_from_latlng(lat = None, lng = None):
    if not AMAP_API_KEY or AMAP_API_KEY == '你的高德地图API Key':
        return '未配置高德API Key'
    key = (round(lat, 6), round(lng, 6))
    if key in _address_cache:
        return _address_cache[key]
    
    try:
        response = requests.get('https://restapi.amap.com/v3/geocode/regeo', params = {
            'location': f'''{lng},{lat}''',
            'key': AMAP_API_KEY,
            'extensions': 'base',
            'batch': 'false',
            'roadlevel': 0 }, timeout = 10)
        result = response.json()
        if result.get('status') == '1' and result.get('regeocode'):
            address = result['regeocode'].get('formatted_address', '未知地址')
        else:
            address = '未知地址'
    except Exception as e:
        address = f'地址获取失败：{e}'

    _address_cache[key] = address
    return address

