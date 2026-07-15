# Source Generated with Decompyle++
# File: terrain_profile_service.pyc (Python 3.11)

from __future__ import annotations
import html
import json
import math
import os
import time
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo
from services.output_trace_service import create_output_trace


def _font(size: int = None, bold: bool = False):
    candidates = []
    windir = os.environ.get('WINDIR', 'C:/Windows')
    if bold:
        candidates.extend([
            Path(windir) / 'Fonts' / 'msyhbd.ttc',
            Path(windir) / 'Fonts' / 'simhei.ttf',
        ])
    else:
        candidates.extend([
            Path(windir) / 'Fonts' / 'msyh.ttc',
            Path(windir) / 'Fonts' / 'simsun.ttc',
        ])
    for path in candidates:
        try:
            if path.is_file():
                return ImageFont.truetype(str(path), size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _distance_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1 = math.radians(float(a['lat']))
    lat2 = math.radians(float(b['lat']))
    dlat = lat2 - lat1
    dlon = math.radians(float(b['lng']) - float(a['lng']))
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 1.2742e+07 * math.asin(min(1, math.sqrt(h)))


def _profile_rows(points: list[dict[str, Any]]) -> list[dict[str, float]]:
    if not points:
        raise ValueError('没有可输出的航点')
    rows = []
    distance = 0
    reference_ground = float(
        points[0].get('terrainReferenceElevation', points[0].get('groundElevation', 0)) or 0
    )
    for index, point in enumerate(points):
        if index:
            distance += _distance_m(points[index - 1], point)
        ground = float(point.get('groundElevation', 0) or 0)
        relative = float(point.get('height', 0) or 0)
        flight_abs = reference_ground + relative
        clearance = flight_abs - ground
        rows.append({
            'index': index + 1,
            'distance': distance,
            'ground': ground,
            'flight': flight_abs,
            'relative': relative,
            'clearance': clearance,
            'lat': float(point['lat']),
            'lng': float(point['lng']),
        })
    return rows


def _scale(
    value: float,
    low: float,
    high: float,
    out_low: float,
    out_high: float,
) -> float:
    if high <= low:
        return (out_low + out_high) / 2
    return out_low + (value - low) / (high - low) * (out_high - out_low)


def create_profile_png(
    points: list[dict[str, Any]],
    output_path: str,
    title: str = '航线地形剖面图',
    export_id: str = '',
    watermark: str = '',
) -> dict[str, Any]:
    rows = _profile_rows(points)
    width, height = (1500, 820)
    left, right, top, bottom = (110, 70, 120, 130)
    plot_w = width - left - right
    plot_h = height - top - bottom

    image = Image.new('RGB', (width, height), '#f6f9fc')
    draw = ImageDraw.Draw(image)
    title_font = _font(32, True)
    label_font = _font(20)
    small_font = _font(16)

    distances = [r['distance'] for r in rows]
    grounds = [r['ground'] for r in rows]
    flights = [r['flight'] for r in rows]

    y_min = math.floor(min(grounds + flights) - 10) // 10 * 10
    y_max = math.ceil(max(grounds + flights) + 10) // 10 * 10
    x_max = max(distances[-1], 1)

    # Title
    draw.text((left, 34), title, font=title_font, fill='#17324d')

    # Subtitle
    subtitle = f'航点 {len(rows)} 个  ·  航程 {x_max / 1000:.2f} km  ·  生成时间 {time.strftime("%Y-%m-%d %H:%M:%S")}'
    if export_id:
        subtitle += f'  ·  编号 {export_id}'
    draw.text((left, 80), subtitle, font=small_font, fill='#52697f')

    # Plot background
    draw.rounded_rectangle(
        (left - 22, top - 18, width - right + 22, height - bottom + 26),
        18, fill='#ffffff', outline='#d7e2ec', width=2,
    )

    # Y grid lines
    for i in range(6):
        y_value = y_min + (y_max - y_min) * i / 5
        y = top + plot_h - i * plot_h / 5
        draw.line((left, y, left + plot_w, y), fill='#dfe8f0', width=1)
        draw.text((18, y - 10), f'{y_value:.0f} m', font=small_font, fill='#6a7d90')

    # X grid lines
    for i in range(7):
        x_value = x_max * i / 6
        x = left + i * plot_w / 6
        draw.line((x, top, x, top + plot_h), fill='#edf2f6', width=1)
        draw.text((x - 25, top + plot_h + 16), f'{x_value / 1000:.1f}', font=small_font, fill='#6a7d90')

    # X axis label
    draw.text(
        (left + plot_w / 2 - 55, height - 72),
        '累计航程（km）', font=label_font, fill='#344b60',
    )

    # Coordinate mapping
    ground_xy = [
        (
            _scale(r['distance'], 0, x_max, left, left + plot_w),
            _scale(r['ground'], y_min, y_max, top + plot_h, top),
        )
        for r in rows
    ]
    flight_xy = [
        (
            _scale(r['distance'], 0, x_max, left, left + plot_w),
            _scale(r['flight'], y_min, y_max, top + plot_h, top),
        )
        for r in rows
    ]

    # Ground polygon
    polygon = [(left, top + plot_h)] + ground_xy + [(left + plot_w, top + plot_h)]
    draw.polygon(polygon, fill='#d8e6cf')

    # Lines
    if len(ground_xy) >= 2:
        draw.line(ground_xy, fill='#4d7c45', width=4, joint='curve')
        draw.line(flight_xy, fill='#e65d3f', width=5, joint='curve')

    # Flight points
    for x, y in flight_xy:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill='#ffffff', outline='#e65d3f', width=2)

    # Legend
    legend_y = height - 42
    draw.line((left, legend_y, left + 42, legend_y), fill='#4d7c45', width=5)
    draw.text((left + 52, legend_y - 12), '地面海拔', font=small_font, fill='#344b60')
    draw.line((left + 190, legend_y, left + 232, legend_y), fill='#e65d3f', width=5)
    draw.text((left + 242, legend_y - 12), '航线绝对高度', font=small_font, fill='#344b60')

    min_clearance = min(r['clearance'] for r in rows)
    max_clearance = max(r['clearance'] for r in rows)
    draw.text(
        (left + 470, legend_y - 12),
        f'离地高度范围：{min_clearance:.1f} - {max_clearance:.1f} m',
        font=small_font, fill='#344b60',
    )

    # Watermark
    if watermark:
        watermark_font = _font(64, True)
        text = str(watermark)[:40]
        box = draw.textbbox((0, 0), text, font=watermark_font)
        tx = (width - (box[2] - box[0])) / 2
        ty = (height - (box[3] - box[1])) / 2
        draw.text((tx + 2, ty + 2), text, font=watermark_font, fill='#ffffff')
        draw.text((tx, ty), text, font=watermark_font, fill='#b6c1cb')

    # PNG metadata
    pnginfo = PngInfo()
    marker = create_output_trace('terrain_profile_png')
    if marker:
        pnginfo.add_text('JTTrace', marker)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format='PNG', optimize=True, pnginfo=pnginfo)

    return {
        'path': str(output_path),
        'rows': rows,
        'distance_m': x_max,
        'min_clearance': min_clearance,
        'max_clearance': max_clearance,
    }


def create_profile_html(
    points: list[dict[str, Any]],
    output_path: str,
    title: str = '航线地形剖面图',
    export_id: str = '',
    watermark: str = '',
) -> dict[str, Any]:
    rows = _profile_rows(points)
    data = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    safe_title = html.escape(title)
    safe_id = html.escape(export_id)
    safe_watermark = html.escape(str(watermark or '')[:40])

    marker = create_output_trace('terrain_profile_html')
    trace_comment = f'<!--{marker}-->' if marker else ''
    watermark_html = f'<div class="watermark">{safe_watermark}</div>' if safe_watermark else ''

    id_part = f' · 编号 {safe_id}' if safe_id else ''

    content = (
        f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{safe_title}</title>\n'
        f'<style>body{{margin:0;background:#eef3f8;color:#17324d;font-family:"Microsoft YaHei",Arial,sans-serif}}'
        f'.wrap{{max-width:1280px;margin:24px auto;padding:0 20px}}'
        f'.card{{background:#fff;border:1px solid #d6e1eb;border-radius:18px;box-shadow:0 12px 34px rgba(20,45,70,.10);padding:24px}}'
        f'h1{{margin:0 0 8px}}.meta{{color:#60778b;margin-bottom:18px}}'
        f'svg{{width:100%;height:560px;background:linear-gradient(#fbfdff,#f7fafc);border-radius:12px}}'
        f'.tip{{position:fixed;display:none;background:#17324d;color:#fff;padding:9px 12px;border-radius:8px;font-size:13px;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.25)}}'
        f'.legend{{display:flex;gap:24px;margin-top:14px;color:#52697f}}'
        f'.line{{display:inline-block;width:34px;height:4px;vertical-align:middle;margin-right:8px;border-radius:4px}}'
        f'.watermark{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;font-size:72px;font-weight:700;color:rgba(100,120,140,.20);pointer-events:none;transform:rotate(-18deg);z-index:20}}'
        f'</style></head><body>'
        f'{watermark_html}'
        f'<div class="wrap"><div class="card"><h1>{safe_title}</h1>'
        f'<div class="meta">航点 <span id="count"></span> 个 · 航程 <span id="distance"></span> km{id_part}</div>'
        f'<svg id="chart" viewBox="0 0 1200 560" preserveAspectRatio="none"></svg>'
        f'<div class="legend"><span><i class="line" style="background:#4d7c45"></i>地面海拔</span>'
        f'<span><i class="line" style="background:#e65d3f"></i>航线绝对高度</span>'
        f'<span id="clearance"></span></div></div></div>'
        f'<div class="tip" id="tip"></div>\n'
        f'<script>const rows={data};'
        f"const svg=document.getElementById('chart'),tip=document.getElementById('tip');"
        f"document.getElementById('count').textContent=rows.length;"
        f"const xmax=Math.max(rows.at(-1)?.distance||1,1),all=rows.flatMap(r=>[r.ground,r.flight]),"
        f"ymin=Math.floor((Math.min(...all)-10)/10)*10,ymax=Math.ceil((Math.max(...all)+10)/10)*10;"
        f"document.getElementById('distance').textContent=(xmax/1000).toFixed(2);"
        f"const clears=rows.map(r=>r.clearance);"
        f"document.getElementById('clearance').textContent="
        f"`离地高度范围：${{Math.min(...clears).toFixed(1)}} - ${{Math.max(...clears).toFixed(1)}} m`;"
        f"const L=72,R=24,T=28,B=58,W=1200-L-R,H=560-T-B;"
        f"const sx=x=>L+x/xmax*W,sy=y=>T+H-(y-ymin)/(ymax-ymin||1)*H;"
        f"let s='';"
        f"for(let i=0;i<6;i++){{const y=ymin+(ymax-ymin)*i/5,py=sy(y);"
        f's+=`<line x1="${{L}}" y1="${{py}}" x2="${{L+W}}" y2="${{py}}" stroke="#dfe8f0"/>'
        f'<text x="8" y="${{py+5}}" fill="#6a7d90" font-size="14">${{y.toFixed(0)}}m</text>`}}'
        f"for(let i=0;i<7;i++){{const x=xmax*i/6,px=sx(x);"
        f's+=`<line x1="${{px}}" y1="${{T}}" x2="${{px}}" y2="${{T+H}}" stroke="#edf2f6"/>'
        f'<text x="${{px-18}}" y="${{T+H+28}}" fill="#6a7d90" font-size="14">${{(x/1000).toFixed(1)}}</text>`}}'
        f"const gp=rows.map(r=>`${{sx(r.distance)}},${{sy(r.ground)}}`).join(' '),"
        f"fp=rows.map(r=>`${{sx(r.distance)}},${{sy(r.flight)}}`).join(' ');"
        f's+=`<polygon points="${{L}},${{T+H}} ${{gp}} ${{L+W}},${{T+H}}" fill="#d8e6cf" opacity=".9"/>'
        f'<polyline points="${{gp}}" fill="none" stroke="#4d7c45" stroke-width="4"/>'
        f'<polyline points="${{fp}}" fill="none" stroke="#e65d3f" stroke-width="5"/>`;'
        f"rows.forEach((r,i)=>{{"
        f's+=`<circle data-i="${{i}}" cx="${{sx(r.distance)}}" cy="${{sy(r.flight)}}" r="5" fill="#fff" stroke="#e65d3f" stroke-width="3"/>`'
        f"}});svg.innerHTML=s;"
        f"svg.querySelectorAll('circle').forEach(c=>{{"
        f"c.addEventListener('mousemove',e=>{{"
        f"const r=rows[+c.dataset.i];tip.style.display='block';"
        f"tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px';"
        f'tip.innerHTML=`航点 ${{r.index}}<br>累计 ${{(r.distance/1000).toFixed(3)}} km<br>'
        f'地面 ${{r.ground.toFixed(1)}} m<br>航线 ${{r.flight.toFixed(1)}} m<br>'
        f"离地 ${{r.clearance.toFixed(1)}} m`;}});"
        f"c.addEventListener('mouseleave',()=>tip.style.display='none')"
        f' }});</script>'
        f'{trace_comment}'
        f'</body></html>'
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding='utf-8')

    return {
        'path': str(output_path),
        'rows': rows,
        'distance_m': rows[-1]['distance'],
    }
