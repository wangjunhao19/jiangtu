# Source Generated with Decompyle++
# File: ai_image_classifier_service.pyc (Python 3.11)

from __future__ import annotations
import csv
import json
import math
import os
import re
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional
import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from pyproj import Transformer
from shapely.geometry import Point
from services.image_service import read_img_gps
from services.land_photo_service import read_land_kml_files
from services.watermark_service import resolve_font_path
IMAGE_EXTENSIONS = {
    '.bmp',
    '.png',
    '.tif',
    '.tiff',
    '.webp',
    '.jpg',
    '.jpeg'}
MODEL_VERSION = 1
@dataclass
class TrainOptions:
    algorithm: str = 'hybrid'
    augment: bool = True
    image_size: int = 128
    k_neighbors: int = 5


@dataclass
class BatchOptions:
    image_dir: str = ''
    output_dir: str = ''
    model_path: str = ''
    land_path: str = ''
    land_id_field: str = ''
    include_subdirs: bool = True
    match_tolerance_m: float = 5.0
    confidence_threshold: float = 50.0
    unknown_category: str = '待人工确认'
    no_gps_land_name: str = '无GPS'
    unmatched_land_name: str = '未匹配图斑'
    filename_template: str = '{图斑号}_{类别}_{序号}.jpg'
    folder_template: str = '{图斑号}/{类别}'
    watermark_enabled: bool = True
    watermark_template: str = '图斑编号：{图斑号}\nAI类别：{类别}\n经度：{经度}\n纬度：{纬度}\n拍摄时间：{拍摄时间}'
    watermark_position: str = '左下角'
    watermark_font_size: int = 42
    watermark_opacity: int = 82
    watermark_background: bool = True
    jpeg_quality: int = 95
    fallback_file_time: bool = True


@dataclass
class Prediction:
    category: str = ''
    confidence: float = 0.0
    top3: list = None


@dataclass
class TrainedModel:
    classes: list = None
    features: np.ndarray = None
    labels: np.ndarray = None
    means: np.ndarray = None
    stds: np.ndarray = None
    centroids: np.ndarray = None
    algorithm: str = 'hybrid'
    k_neighbors: int = 5
    image_size: int = 128
    metadata: dict = None

def list_image_files(folder = None, include_subdirs = False):
    base = Path(folder)
    if not base.is_dir():
        return []
    iterator = base.rglob('*') if include_subdirs else base.glob('*')
    return sorted(
        [str(p) for p in iterator if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key = lambda value: value.lower())


def summarize_training_folder(folder = None):
    base = Path(folder)
    if not base.is_dir():
        raise ValueError('训练数据目录不存在。')
    result = { }
    for child in sorted(base.iterdir(), key = (lambda p: p.name.lower())):
        if child.is_dir() or child.name.startswith('.'):
            continue
        count = len(list_image_files(str(child), include_subdirs = True))
        if count:
            result[child.name] = count
    if len(result) < 2:
        raise ValueError('训练目录至少需要两个类别文件夹，每个文件夹内放对应类别照片。')
    return result


def _normalize_hist(values = None, bins = None, value_range = None):
    (hist, _) = np.histogram(values, bins = bins, range = value_range)
    hist = hist.astype(np.float32)
    total = float(hist.sum())
    return hist / total if total > 0 else hist


def _extract_features_from_image(image = None, image_size = None):
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((image_size, image_size), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (image_size, image_size), (127, 127, 127))
    offset = ((image_size - image.width) // 2, (image_size - image.height) // 2)
    canvas.paste(image, offset)
    rgb = np.asarray(canvas, dtype = np.float32) / 255
    features = []
    for channel in range(3):
        features.append(_normalize_hist(rgb[:, :, channel], 16, (0, 1)))
    hsv = np.asarray(canvas.convert('HSV'), dtype = np.float32) / 255
    for channel in range(3):
        features.append(_normalize_hist(hsv[:, :, channel], 12, (0, 1)))
    gray = np.asarray(canvas.convert('L'), dtype = np.float32) / 255
    features.append(_normalize_hist(gray, 16, (0, 1)))
    spatial = []
    step = image_size // 4
    for gy in range(4):
        for gx in range(4):
            patch = rgb[gy * step:(gy + 1) * step, gx * step:(gx + 1) * step]
            spatial.extend(patch.mean(axis = (0, 1)).tolist())
            spatial.extend(patch.std(axis = (0, 1)).tolist())
    features.append(np.asarray(spatial, dtype = np.float32))
    small_gray = np.asarray(canvas.convert('L').resize((8, 8), Image.Resampling.BILINEAR), dtype = np.float32) / 255
    features.append(small_gray.reshape(-1))
    gx_arr = np.zeros_like(gray)
    gy_arr = np.zeros_like(gray)
    gx_arr[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy_arr[1:-1, :] = gray[2:, :] - gray[:-2, :]
    magnitude = np.sqrt(gx_arr * gx_arr + gy_arr * gy_arr)
    orientation = (np.arctan2(gy_arr, gx_arr) + math.pi) % math.pi
    orient_hist = np.zeros(8, dtype = np.float32)
    bin_index = np.minimum(((orientation / math.pi) * 8).astype(np.int32), 7)
    for idx in range(8):
        orient_hist[idx] = float(magnitude[bin_index == idx].sum())
    orient_hist /= float(orient_hist.sum()) + 1e-08
    features.append(orient_hist)
    moments = []
    for channel in range(3):
        values = rgb[:, :, channel]
        moments.extend([float(values.mean()), float(values.std())])
    moments.extend([
        float(gray.mean()), float(gray.std()),
        float(np.quantile(gray, 0.25)), float(np.quantile(gray, 0.75)),
        float(magnitude.mean()), float((magnitude > 0.12).mean()),
        float(hsv[:, :, 1].mean()), float(hsv[:, :, 1].std())])
    features.append(np.asarray(moments, dtype = np.float32))
    return np.concatenate(features).astype(np.float32)


def extract_visual_features(path = None, image_size = 128):
    image = Image.open(path)
    try:
        return _extract_features_from_image(image, image_size)
    except Exception:
        return None


def _training_variants(path = None, image_size = 128, augment = False):
    features = extract_visual_features(path, image_size)
    if features is None:
        return []
    results = [features]
    if augment:
        image = Image.open(path)
        for fn in [
            lambda img: ImageEnhance.Brightness(img).enhance(1.3),
            lambda img: ImageEnhance.Contrast(img).enhance(1.3),
            lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
        ]:
            try:
                aug_img = fn(image)
                v = _extract_features_from_image(aug_img, image_size)
                results.append(v)
            except Exception:
                pass
    return results


def _softmax(scores = None):
    values = scores - float(np.max(scores))
    exp = np.exp(np.clip(values, -50, 50))
    return exp / (float(exp.sum()) + 1e-12)


def _predict_vector(model = None, vector = None):
    standardized = ((vector - model.means) / model.stds).astype(np.float32)
    if model.algorithm == 'knn':
        distances = np.linalg.norm(model.features - standardized, axis = 1)
        k = model.k_neighbors
        nearest_idx = np.argsort(distances)[:k]
        nearest_labels = model.labels[nearest_idx]
        counts = Counter(nearest_labels.tolist())
        best_idx = counts.most_common(1)[0][0]
        category = model.classes[best_idx]
        confidence = counts[best_idx] / k * 100
        top3 = [(model.classes[idx], cnt / k * 100) for idx, cnt in counts.most_common(3)]
    else:
        distances = np.linalg.norm(model.centroids - standardized, axis = 1)
        scores = _softmax(-distances)
        sorted_idx = np.argsort(-scores)
        best_idx = int(sorted_idx[0])
        category = model.classes[best_idx]
        confidence = float(scores[best_idx] * 100)
        top3 = [(model.classes[int(i)], float(scores[i] * 100)) for i in sorted_idx[:3]]
    return Prediction(category = category, confidence = round(confidence, 2), top3 = top3)


def _build_model(classes, raw_features = None, labels = None, options = None, metadata = None):
    means = raw_features.mean(axis = 0).astype(np.float32)
    stds = raw_features.std(axis = 0).astype(np.float32)
    stds[stds < 1e-05] = 1
    standardized = ((raw_features - means) / stds).astype(np.float32)
    centroids = []
    for index in range(len(classes)):
        rows = standardized[labels == index]
        centroids.append(rows.mean(axis = 0) if len(rows) else np.zeros(standardized.shape[1], dtype = np.float32))
    return TrainedModel(classes = classes, features = standardized, labels = labels.astype(np.int32),
                        means = means, stds = stds,
                        centroids = np.asarray(centroids, dtype = np.float32),
                        algorithm = options.algorithm,
                        k_neighbors = max(1, int(options.k_neighbors)),
                        image_size = int(options.image_size),
                        metadata = metadata)


def train_folder_model(training_dir = None, model_path = None, options = None, progress = None):
    if not options:
        options = TrainOptions()
    summary = summarize_training_folder(training_dir)
    classes = list(summary.keys())
    samples = []
    for class_index, class_name in enumerate(classes):
        for path in list_image_files(str(Path(training_dir) / class_name), include_subdirs = True):
            samples.append((path, class_index))
    total = len(samples)
    if total < 4:
        raise ValueError('训练照片过少，请至少准备4张照片，并尽量保证每个类别不少于3张。')
    raw_rows = []
    label_rows = []
    failures = []
    base_features_by_class = defaultdict(list)
    for index, (path, class_index) in enumerate(samples, start = 1):
        try:
            variants = _training_variants(path, options.image_size, options.augment)
            if not variants:
                continue
            base_features_by_class[class_index].append(variants[0])
            raw_rows.extend(variants)
            label_rows.extend([class_index] * len(variants))
        except Exception as exc:
            failures.append(f'{path}: {exc}')
        if progress:
            progress(index, total, f'提取训练特征：{Path(path).name}')
    if not raw_rows:
        raise RuntimeError('没有成功读取任何训练照片。')
    present_labels = set(label_rows)
    if len(present_labels) < 2:
        raise RuntimeError('成功读取的训练数据不足两个类别。')
    raw_features = np.asarray(raw_rows, dtype = np.float32)
    labels = np.asarray(label_rows, dtype = np.int32)
    metadata = {
        'model_version': MODEL_VERSION,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'training_dir_name': Path(training_dir).name,
        'class_counts': summary,
        'source_image_count': total,
        'feature_sample_count': int(len(raw_features)),
        'failed_count': len(failures),
        'algorithm': options.algorithm,
        'augment': bool(options.augment)}
    model = _build_model(classes, raw_features, labels, options, metadata)
    correct = 0
    checked = 0
    base_vectors = []
    base_labels = []
    for class_index, vectors in base_features_by_class.items():
        base_vectors.extend(vectors)
        base_labels.extend([class_index] * len(vectors))
    if len(base_vectors) >= 3:
        base_raw = np.asarray(base_vectors, dtype = np.float32)
        base_standard = (base_raw - model.means) / model.stds
        for i in range(len(base_standard)):
            distances = np.linalg.norm(base_standard - base_standard[i], axis = 1)
            distances[i] = np.inf
            nearest = int(np.argmin(distances))
            correct += int(base_labels[nearest] == base_labels[i])
            checked += 1
    self_check_accuracy = round(correct * 100 / checked, 2) if checked else 0
    model.metadata['self_check_accuracy'] = self_check_accuracy
    save_model(model, model_path)
    return {
        'model_path': model_path,
        'classes': classes,
        'class_counts': summary,
        'source_image_count': total,
        'feature_sample_count': len(raw_features),
        'failed': failures,
        'self_check_accuracy': self_check_accuracy}


def save_model(model = None, path = None):
    target = Path(path)
    target.parent.mkdir(parents = True, exist_ok = True)
    metadata = dict(model.metadata)
    metadata.update({
        'classes': model.classes,
        'algorithm': model.algorithm,
        'k_neighbors': model.k_neighbors,
        'image_size': model.image_size})
    with target.open('wb') as handle:
        np.savez_compressed(handle,
                            features = model.features.astype(np.float32),
                            labels = model.labels.astype(np.int32),
                            means = model.means.astype(np.float32),
                            stds = model.stds.astype(np.float32),
                            centroids = model.centroids.astype(np.float32),
                            metadata = np.asarray(json.dumps(metadata, ensure_ascii = False)))


def load_model(path = None):
    payload = np.load(path, allow_pickle = False)
    metadata_raw = payload['metadata'].item()
    metadata = json.loads(str(metadata_raw))
    classes = [str(value) for value in metadata.get('classes', [])]
    if not classes:
        raise ValueError('模型文件中没有类别信息。')
    return TrainedModel(
        classes = classes,
        features = np.asarray(payload['features'], dtype = np.float32),
        labels = np.asarray(payload['labels'], dtype = np.int32),
        means = np.asarray(payload['means'], dtype = np.float32),
        stds = np.asarray(payload['stds'], dtype = np.float32),
        centroids = np.asarray(payload['centroids'], dtype = np.float32),
        algorithm = str(metadata.get('algorithm', 'hybrid')),
        k_neighbors = int(metadata.get('k_neighbors', 5)),
        image_size = int(metadata.get('image_size', 128)),
        metadata = metadata)


def classify_image(path=None, model=None):
    if not model or not path:
        return Prediction()
    vector = extract_visual_features(path, model.image_size)
    if vector is None:
        return Prediction()
    return _predict_vector(model, vector)


def _read_vector_file(path=None):
    try:
        gdf = gpd.read_file(path)
        return gdf
    except Exception:
        return None


def get_land_fields(path=None):
    gdf = _read_vector_file(path)
    if gdf is None or gdf.empty:
        return []
    result = []
    for _, row in gdf.iterrows():
        fields = {}
        for col in gdf.columns:
            if col == 'geometry':
                continue
            fields[col] = str(row.get(col, '')).strip()
        fields['geometry'] = row.geometry
        result.append(fields)
    return result


def _utm_epsg(lon=0, lat=0):
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


class LandMatcher:
    """将照片GPS匹配到图斑。"""

    def __init__(self, lands=None, tolerance_m=5.0):
        self.lands = lands or []
        self.tolerance_m = tolerance_m

    def match(self, lon=0, lat=0):
        if not self.lands:
            return None
        from shapely.geometry import Point
        pt = Point(lon, lat)
        best = None
        best_dist = float('inf')
        for land in self.lands:
            geom = land.get('geometry')
            if geom is None:
                continue
            dist = pt.distance(geom)
            if dist < best_dist:
                best_dist = dist
                best = land
        return best


def safe_component(value=None, fallback=''):
    text = str(value or '').strip()
    for ch in '<>:"/\\|?*':
        text = text.replace(ch, '_')
    return text or fallback


def render_template(template='', values=None, keep_slashes=False):
    text = str(template or '')
    for key, value in (values or {}).items():
        placeholder = '{' + str(key) + '}'
        replacement = safe_component(value)
        text = text.replace(placeholder, replacement)
    return text


def render_template_multiline(template='', values=None):
    lines = str(template or '').split('\n')
    return '\n'.join(render_template(line, values) for line in lines)


def _font(font_size=16):
    from PIL import ImageFont
    try:
        return ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', font_size)
    except Exception:
        try:
            return ImageFont.truetype('arial.ttf', font_size)
        except Exception:
            return ImageFont.load_default()


def apply_custom_watermark(source_path=None, output_path=None, text='', position='左下角', font_size=42, opacity=82, background=True, quality=95):
    from PIL import Image, ImageDraw
    img = Image.open(source_path).convert('RGBA')
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(font_size)
    alpha = int(255 * opacity / 100)
    bg_color = (0, 0, 0, alpha) if background else (0, 0, 0, 0)
    text_color = (255, 255, 255, alpha)
    bbox = draw.multiline_textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = 10
    x, y = margin, img.height - th - margin
    if '右' in position:
        x = img.width - tw - margin
    if '上' in position or '顶' in position:
        y = margin
    if background:
        draw.rectangle([x - 4, y - 4, x + tw + 4, y + th + 4], fill=bg_color)
    draw.multiline_text((x, y), text, font=font, fill=text_color)
    result = Image.alpha_composite(img, overlay).convert('RGB')
    result.save(str(output_path), quality=quality)


def _copy_or_convert_to_jpeg(source_path=None, output_path=None, quality=95):
    from PIL import Image
    img = Image.open(source_path).convert('RGB')
    img.save(str(output_path), 'JPEG', quality=quality)


def _unique_output_path(path=None):
    from pathlib import Path
    p = Path(path or 'output.jpg')
    if not p.exists():
        return str(p)
    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    counter = 1
    while True:
        candidate = parent / f'{stem}_{counter}{suffix}'
        if not candidate.exists():
            return str(candidate)
        counter += 1


def _format_capture_parts(capture_time=None):
    if not capture_time:
        return {}
    parts = str(capture_time).replace(':', '-').split()
    date_part = parts[0] if parts else ''
    time_part = parts[1] if len(parts) > 1 else ''
    return {'date': date_part, 'time': time_part, 'datetime': str(capture_time)}


def process_image_folder(options=None, progress=None):
    """批量处理图片文件夹。"""
    opts = options or BatchOptions()
    results = []
    return results
