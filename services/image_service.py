import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from PIL import Image
from services.output_trace_service import add_trace_to_report
from config import CACHE_FILE
from models.image_info import ImageInfo


def dms2decimal(dms, ref):

    try:
        deg = float(dms[0])
        minu = float(dms[1])
        sec = float(dms[2])
        dec = deg + minu / 60 + sec / 3600
        return -dec if ref in ('S', 'W') else dec
    except Exception:
        return 0.0


def get_image_capture_time(img_path: str) -> Optional[str]:

    try:
        with Image.open(img_path) as img:
            exif_data = img._getexif()
            if exif_data and 36867 in exif_data:
                return datetime.strptime(exif_data[36867], '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    return None


def _read_xmp_gps(img: Image.Image):

    import xml.etree.ElementTree as _etree
    ET = _etree.ElementTree
    img.seek(0)
    data = img.read()
    start = data.find(b'<?xpacket begin=')
    if start == -1:
        return None
    end = data.find(b'<?xpacket end=')
    if end == -1:
        return None
    root = ET.fromstring(data[start:end + 16])
    ns = {
        'exif': 'http://ns.adobe.com/exif/1.0/'
    }
    lat_str = root.find('.//exif:GPSLatitude', namespaces=ns)
    lon_str = root.find('.//exif:GPSLongitude', namespaces=ns)
    lat_ref_str = root.find('.//exif:GPSLatitudeRef', namespaces=ns)
    lon_ref_str = root.find('.//exif:GPSLongitudeRef', namespaces=ns)
    if lat_str is None or lon_str is None:
        return None

    def parse_dms(value):
        parts = value.text.split(',')
        d = float(parts[0].split('/')[0]) / float(parts[0].split('/')[1])
        m = float(parts[1].split('/')[0]) / float(parts[1].split('/')[1])
        s = float(parts[2].split('/')[0]) / float(parts[2].split('/')[1]) if len(parts) > 2 else 0
        return (d, m, s)

    lat = dms2decimal(parse_dms(lat_str), lat_ref_str.text if lat_ref_str is not None else 'N')
    lon = dms2decimal(parse_dms(lon_str), lon_ref_str.text if lon_ref_str is not None else 'E')
    return (lat, lon)


def read_img_gps(img_path: str) -> ImageInfo:
    filename = os.path.basename(img_path)
    capture_time = get_image_capture_time(img_path)

    try:
        with Image.open(img_path) as img:
            exif_data = img._getexif()
            lat = None
            lon = None
            alt = 0.0
            has_gps = False
            if exif_data and 34853 in exif_data:
                gps = exif_data[34853]
                lat_dms = gps.get(2)
                lon_dms = gps.get(4)
                if lat_dms and lon_dms:
                    lat = dms2decimal(lat_dms, gps.get(1, 'N'))
                    lon = dms2decimal(lon_dms, gps.get(3, 'E'))
                    alt = float(gps.get(6, 0.0))
                    has_gps = True
            if not has_gps:
                try:
                    xmp = _read_xmp_gps(img)
                    if xmp:
                        lat, lon = xmp
                        has_gps = True
                except Exception:
                    pass
            if has_gps:
                return ImageInfo(filename, filename, img_path, lat, lon, alt, True, capture_time=capture_time)
    except Exception:
        pass
    return ImageInfo(filename, filename, img_path, capture_time=capture_time)


def _file_signature(filepath: str) -> str:
    '''照片缓存签名：同一路径照片被替换时，自动重新读取 GPS，避免地图沿用旧坐标。'''

    try:
        st = os.stat(filepath)
        return f'{int(st.st_size)}:{int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1000000000)))}'
    except Exception:
        return ''


class ImageCache:

    def __init__(self):
        self.cache = {}
        self.load_cache()

    def load_cache(self):

        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for k, v in raw.items():
                    if isinstance(v, dict) and 'info' in v:
                        info_data = v.get('info') or {}
                        sig = str(v.get('signature', ''))
                    else:
                        info_data = v if isinstance(v, dict) else {}
                        sig = ''
                    try:
                        self.cache[k] = {
                            'info': ImageInfo(**info_data),
                            'signature': sig
                        }
                    except Exception:
                        continue
        except Exception:
            pass

    def save_cache(self):

        try:
            os.makedirs(os.path.dirname(os.path.abspath(CACHE_FILE)) or '.', exist_ok=True)
            payload = {
                k: {
                    'signature': v.get('signature', ''),
                    'info': v['info'].to_dict()
                }
                for k, v in self.cache.items()
                if isinstance(v, dict) and isinstance(v.get('info'), ImageInfo)
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, filepath: str) -> Optional[ImageInfo]:
        item = self.cache.get(filepath)
        if not item:
            return None
        current_sig = _file_signature(filepath)
        cached_sig = str(item.get('signature', ''))
        if current_sig and cached_sig and current_sig != cached_sig:
            self.cache.pop(filepath, None)
            return None
        return item.get('info')

    def set(self, filepath: str, info: ImageInfo):
        self.cache[filepath] = {
            'info': info,
            'signature': _file_signature(filepath)
        }

    def clear(self):
        self.cache.clear()


def _ratio_pair(value) -> tuple[int, int]:
    '''把 exifread 的 Ratio/数值转换为 piexif 可写入的有理数。'''

    try:
        num = int(getattr(value, 'num'))
        den = int(getattr(value, 'den')) or 1
        return (num, den)
    except Exception:
        try:
            number = float(value)
        except Exception:
            return (0, 1)
        scale = 1000000
        return (int(round(number * scale)), scale)


def _copy_dng_metadata_to_jpeg(dng_path: str, jpg_path: str) -> None:
    '''尽量保留 DJI DNG 中的拍摄时间、相机信息和 GPS。'''

    try:
        import exifread
        import piexif
        with open(dng_path, 'rb') as stream:
            tags = exifread.process_file(stream, details=False, strict=False)

        zeroth = {}
        exif = {}
        gps = {}
        make = tags.get('Image Make')
        model = tags.get('Image Model')
        software = tags.get('Image Software')
        if make:
            zeroth[piexif.ImageIFD.Make] = str(make).encode('utf-8', errors='ignore')
        if model:
            zeroth[piexif.ImageIFD.Model] = str(model).encode('utf-8', errors='ignore')
        if software:
            zeroth[piexif.ImageIFD.Software] = str(software).encode('utf-8', errors='ignore')
        dt = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime')
        if dt:
            value = str(dt).encode('ascii', errors='ignore')
            exif[piexif.ExifIFD.DateTimeOriginal] = value
            exif[piexif.ExifIFD.DateTimeDigitized] = value
            zeroth[piexif.ImageIFD.DateTime] = value
        lat = tags.get('GPS GPSLatitude')
        lat_ref = tags.get('GPS GPSLatitudeRef')
        lon = tags.get('GPS GPSLongitude')
        lon_ref = tags.get('GPS GPSLongitudeRef')
        if lat and lon:
            lat_values = list(getattr(lat, 'values', []) or [])
            lon_values = list(getattr(lon, 'values', []) or [])
            if len(lat_values) >= 3 and len(lon_values) >= 3:
                gps[piexif.GPSIFD.GPSLatitude] = tuple(_ratio_pair(v) for v in lat_values[:3])
                gps[piexif.GPSIFD.GPSLongitude] = tuple(_ratio_pair(v) for v in lon_values[:3])
                gps[piexif.GPSIFD.GPSLatitudeRef] = str(lat_ref or 'N').strip().encode('ascii', errors='ignore')[:1] or b'N'
                gps[piexif.GPSIFD.GPSLongitudeRef] = str(lon_ref or 'E').strip().encode('ascii', errors='ignore')[:1] or b'E'
        alt = tags.get('GPS GPSAltitude')
        alt_ref = tags.get('GPS GPSAltitudeRef')
        if alt:
            vals = list(getattr(alt, 'values', []) or [])
            value = vals[0] if vals else alt
            gps[piexif.GPSIFD.GPSAltitude] = _ratio_pair(value)
            try:
                gps[piexif.GPSIFD.GPSAltitudeRef] = int(str(alt_ref or '0').strip() or 0)
            except Exception:
                gps[piexif.GPSIFD.GPSAltitudeRef] = 0
        if not zeroth and not exif and not gps:
            return None
        exif_bytes = piexif.dump({
            '0th': zeroth,
            'Exif': exif,
            'GPS': gps,
            '1st': {},
            'thumbnail': None
        })
        piexif.insert(exif_bytes, jpg_path)
        return None
    except Exception:
        return None


def convert_dng_folder_to_jpg(
    input_dir: str,
    output_dir: str,
    *,
    include_subdirs: bool = True,
    quality: int = 95,
    overwrite: bool = False,
    progress=None
) -> dict:
    '''批量把 DNG 转为 JPG，并尽量保留拍摄时间、相机信息和 GPS。'''

    try:
        import rawpy
    except Exception as exc:
        raise RuntimeError('缺少 rawpy，请先安装依赖：python -m pip install rawpy exifread piexif') from exc

    source = Path(input_dir).resolve()
    target = Path(output_dir).resolve()
    if not source.is_dir():
        raise RuntimeError('DNG源目录不存在。')
    target.mkdir(parents=True, exist_ok=True)
    iterator = source.rglob('*') if include_subdirs else source.glob('*')
    files = sorted(
        [path for path in iterator if path.is_file() and path.suffix.lower() == '.dng'],
        key=lambda path: str(path).lower()
    )
    if not files:
        raise RuntimeError('所选目录中没有读取到 DNG 文件。')
    quality = max(70, min(100, int(quality or 95)))
    converted = []
    skipped = []
    failed = []
    total = len(files)
    for index, dng_path in enumerate(files, 1):
        relative = dng_path.relative_to(source)
        jpg_path = (target / relative).with_suffix('.jpg')
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if jpg_path.exists() and not overwrite:
                skipped.append(str(jpg_path))
            else:
                with rawpy.imread(str(dng_path)) as raw:
                    rgb = raw.postprocess(
                        use_camera_wb=True,
                        use_auto_wb=False,
                        no_auto_bright=False,
                        output_bps=8,
                        output_color=rawpy.ColorSpace.sRGB
                    )
                Image.fromarray(rgb).save(
                    str(jpg_path),
                    format='JPEG',
                    quality=quality,
                    subsampling=0,
                    optimize=True
                )
                _copy_dng_metadata_to_jpeg(str(dng_path), str(jpg_path))
                converted.append(str(jpg_path))
        except Exception as exc:
            failed.append({'dng': str(dng_path), 'error': str(exc)})
        if progress:
            progress(index, total)
    report = {
        'source': str(source),
        'output': str(target),
        'converted': converted,
        'skipped': skipped,
        'failed': failed
    }
    report = add_trace_to_report(report, 'dng_to_jpg')
    (target / 'DNG转JPG结果.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return report
