# Source Generated with Decompyle++
# File: sanzi_project_check_service.pyc (Python 3.11)

from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from services.sanzi_document_service import normalize_land_record
from services.output_trace_service import add_trace_to_report
from services.sanzi_photo_service import (
    export_missing_material_kml,
    export_missing_photo_kml,
    geometry_from_record,
)
from services.sanzi_rules import (
    ACCESSORY_TYPE_LABELS,
    USE_STATUS_REQUIREMENT_GROUPS,
    effective_requirement_groups,
    scene_photo_required,
    accessory_label,
    scene_photo_accessory_type,
)
from services.sanzi_upload_service import scan_archive_materials


def _platform_doc_type(doc: Dict = None) -> int:
    value = doc.get('accessorytype', doc.get('accessoryType', doc.get('type', -1)))
    try:
        return int(float(str(value).strip()))
    except Exception:
        return -1


def _platform_types(record: Dict = None) -> Set[int]:
    return {t for t in (_platform_doc_type(x) for x in (record.get('docs') or [])) if t in ACCESSORY_TYPE_LABELS}


def _local_type_map(project_dir: Path, records: Iterable[Dict], progress=None):
    materials, problems = scan_archive_materials(
        str(project_dir / '02_材料输出'),
        records,
        True,
        True,
        progress=(lambda done, total: progress(done, total, '扫描本地材料')) if progress else None,
    )
    result = defaultdict(set)
    for item in materials:
        result[item.landcode].add(int(item.accessory_type))
    return result, materials, problems


def _labels(types: Iterable[int]) -> str:
    return '、'.join(accessory_label(t) for t in sorted(set(types)))


def _excel_column_name(index: int) -> str:
    result = ''
    value = int(index)
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _write_xlsx_report(path: Path, fields: List[str], rows: List[Dict]) -> None:
    """Write a dependency-free .xlsx report with every value stored as text.

    Storing the land code as an inline string prevents Excel/WPS from rounding
    long identifiers or displaying them in scientific notation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data_rows = [fields] + [[str(row.get(field) or '') for field in fields] for row in rows]

    max_lengths = []
    for field in fields:
        values = [str(field)] + [str(row.get(field) or '') for row in rows[:5000]]
        visual = [sum(2 if ord(ch) > 127 else 1 for ch in value.replace('\n', ' ')) for value in values]
        max_lengths.append(min(46, (max(visual) if visual else 10) + 2))

    sheet_rows = []
    for row_idx, values in enumerate(data_rows, 1):
        cells = []
        style_id = 1 if row_idx == 1 else 2
        for col_idx, value in enumerate(values, 1):
            ref = f'{_excel_column_name(col_idx)}{row_idx}'
            safe = xml_escape(value)
            cells.append(f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{safe}</t></is></c>')
        height = ' ht="28" customHeight="1"' if row_idx == 1 else ''
        sheet_rows.append(f'<row r="{row_idx}"{height}>' + ''.join(cells) + '</row>')

    cols_xml = ''.join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(max_lengths, 1)
    )
    end_ref = f'{_excel_column_name(max(1, len(fields)))}{max(1, len(data_rows))}'

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="20"/>'
        f'<cols>{cols_xml}</cols>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:{end_ref}"/>'
        '</worksheet>'
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="10"/><name val="Microsoft YaHei"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Microsoft YaHei"/></font>'
        '<font><sz val="10"/><name val="Microsoft YaHei"/></font>'
        '</fonts>'
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4F82"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left style="thin"><color rgb="FFB8C5D1"/></left>'
        '<right style="thin"><color rgb="FFB8C5D1"/></right>'
        '<top style="thin"><color rgb="FFB8C5D1"/></top>'
        '<bottom style="thin"><color rgb="FFB8C5D1"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="49" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyNumberFormat="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="49" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1" applyNumberFormat="1">'
        '<alignment vertical="top" wrapText="1"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="平台缺少材料" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>三资平台缺少材料检测报告</dc:title>'
        '<dc:creator>疆途·智能巡查管理平台</dc:creator>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        '</cp:coreProperties>'
    )

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>疆途·智能巡查管理平台</Application></Properties>'
    )

    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', root_rels)
        zf.writestr('docProps/core.xml', core_xml)
        zf.writestr('docProps/app.xml', app_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        zf.writestr('xl/styles.xml', styles_xml)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)


def check_project_materials(records: Iterable[Dict], project_dir: str | Path, *, progress=None) -> Dict:
    records_list = [x for x in records if isinstance(x, dict)]
    if not records_list:
        raise RuntimeError('没有同步图斑数据，请先同步三资平台数据。')

    project = Path(project_dir)
    output_root = project / '02_材料输出'
    log_root = project / '05_操作日志'
    output_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)

    local_map, materials, scan_problems = _local_type_map(project, records_list)

    rows = []
    missing_scene_lands = []
    missing_material_lands = []
    complete_count = 0
    missing_land_count = 0
    unknown_status_count = 0
    missing_scene_count = 0

    total = len(records_list) or 1

    for index, record in enumerate(records_list, 1):
        data = normalize_land_record(record)
        code = data['landcode']
        if not code:
            continue

        status = data['use_status']
        platform_types = _platform_types(record)
        local_types = set(local_map.get(code, set()))
        available = platform_types | local_types
        groups = effective_requirement_groups(status, data['land_actuality'])
        land_missing = False
        land_missing_items = []

        if status < 0 or groups is None:
            unknown_status_count += 1
            land_missing = True
            land_missing_items.append('使用状态未填写或未知')
            rows.append(dict(
                图斑编号=code,
                使用状态=data['use_status_label'],
                地类现状=data['land_actuality_label'],
                检测结果='无法判定',
                缺少或待确认材料='使用状态未填写或未知，请先在官方平台填写后重新同步',
                平台已有附件=_labels(platform_types),
                本地已有附件=_labels(local_types),
                材料规则='未配置',
                备注=record.get('sync_error') or '',
            ))
        else:
            for required_type in groups.get('all', ()):
                if required_type not in available:
                    land_missing = True
                    land_missing_items.append(accessory_label(required_type))
                    rows.append(dict(
                        图斑编号=code,
                        使用状态=data['use_status_label'],
                        地类现状=data['land_actuality_label'],
                        检测结果='缺少',
                        缺少或待确认材料=accessory_label(required_type),
                        平台已有附件=_labels(platform_types),
                        本地已有附件=_labels(local_types),
                        材料规则='必需',
                        备注='',
                    ))

            any_types = tuple(groups.get('any', ()))
            if any_types and not (set(any_types) & available):
                land_missing = True
                land_missing_items.append(f'任选一：{_labels(any_types)}')
                rows.append(dict(
                    图斑编号=code,
                    使用状态=data['use_status_label'],
                    地类现状=data['land_actuality_label'],
                    检测结果='缺少',
                    缺少或待确认材料=f'任选一：{_labels(any_types)}',
                    平台已有附件=_labels(platform_types),
                    本地已有附件=_labels(local_types),
                    材料规则='任选一',
                    备注='',
                ))

            conditional = tuple(groups.get('conditional', ()))
            if conditional and not (set(conditional) & available):
                land_missing = True
                land_missing_items.append(f'条件需要：{_labels(conditional)}')
                rows.append(dict(
                    图斑编号=code,
                    使用状态=data['use_status_label'],
                    地类现状=data['land_actuality_label'],
                    检测结果='待人工确认',
                    缺少或待确认材料=f'条件需要：{_labels(conditional)}',
                    平台已有附件=_labels(platform_types),
                    本地已有附件=_labels(local_types),
                    材料规则='条件需要',
                    备注='软件无法判断是否触发条件，请按官方平台实际提示核实',
                ))

        scene_type = scene_photo_accessory_type(status)
        scene_required = status < 0 or (groups is not None and scene_type in set(groups.get('all', ())))

        if scene_required and scene_type not in available:
            missing_scene_count += 1
            geom = geometry_from_record(record)
            if geom is not None:
                missing_scene_lands.append(dict(data=data, wgs_geom=geom))

        if land_missing:
            geom = geometry_from_record(record)
            if geom is not None:
                missing_material_lands.append(dict(
                    data=data,
                    wgs_geom=geom,
                    missing_summary='；'.join(dict.fromkeys(land_missing_items)) or '缺少或待确认材料',
                ))
            missing_land_count += 1
        else:
            complete_count += 1
            rows.append(dict(
                图斑编号=code,
                使用状态=data['use_status_label'],
                地类现状=data['land_actuality_label'],
                检测结果='完整',
                缺少或待确认材料='',
                平台已有附件=_labels(platform_types),
                本地已有附件=_labels(local_types),
                材料规则='',
                备注='',
            ))

        if progress:
            progress(index, total, '检测项目附件')

    for problem in scan_problems:
        rows.append(dict(
            图斑编号=problem.landcode,
            使用状态='',
            地类现状='',
            检测结果=problem.status,
            缺少或待确认材料=problem.filename,
            平台已有附件='',
            本地已有附件='',
            材料规则='文件命名/归档问题',
            备注=problem.message,
        ))

    fields = list(('图斑编号', '使用状态', '地类现状', '检测结果', '缺少或待确认材料', '平台已有附件', '本地已有附件', '材料规则', '备注'))
    csv_path = log_root / '项目附件完整性检测报告.csv'
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    json_path = log_root / '项目附件完整性检测报告.json'
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    kml_path = log_root / '缺少现场照片.kml'
    export_missing_photo_kml(missing_scene_lands, kml_path)

    output_kml = output_root / '缺少现场照片.kml'
    output_kml.write_bytes(kml_path.read_bytes())

    all_missing_kml = output_root / '缺少材料图斑.kml'
    export_missing_material_kml(missing_material_lands, all_missing_kml)

    summary = dict(
        land_total=len(records_list),
        complete_land_total=complete_count,
        missing_land_total=missing_land_count,
        unknown_status_total=unknown_status_count,
        missing_scene_total=missing_scene_count,
        missing_scene_kml_geometry_total=len(missing_scene_lands),
        local_material_total=len(materials),
        problem_file_total=len(scan_problems),
        report_csv=str(csv_path),
        report_json=str(json_path),
        missing_scene_kml=str(output_kml),
        missing_material_kml=str(all_missing_kml),
        missing_material_kml_geometry_total=len(missing_material_lands),
    )
    summary = add_trace_to_report(summary, 'sanzi_project_check')

    (log_root / '项目附件完整性检测汇总.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return summary


def check_platform_materials(records: Iterable[Dict], project_dir: str | Path, *, progress=None) -> Dict:
    """只根据最近一次同步到的官方平台附件，检测平台当前缺少的材料。

    本函数不会把本地待上传文件计为"已有"，因此报告表示的是官方平台的
    实际附件状态。同步数据过旧时，调用方应先重新同步。
    """
    records_list = [x for x in records if isinstance(x, dict)]
    if not records_list:
        raise RuntimeError('没有同步图斑数据，请先同步三资平台数据。')

    project = Path(project_dir)
    report_root = project / '07_检测报告'
    report_root.mkdir(parents=True, exist_ok=True)

    rows = []
    missing_scene_lands = []
    missing_material_lands = []
    complete_count = 0
    missing_land_count = 0
    unknown_status_count = 0
    conditional_count = 0
    missing_scene_count = 0

    total = len(records_list) or 1

    for index, record in enumerate(records_list, 1):
        data = normalize_land_record(record)
        code = data['landcode']
        if not code:
            continue

        status = data['use_status']
        platform_types = _platform_types(record)
        groups = effective_requirement_groups(status, data['land_actuality'])
        land_missing = False
        land_missing_items = []
        docs_error = str(record.get('docs_error') or '').strip()

        if docs_error:
            unknown_status_count += 1
            land_missing = True
            land_missing_items.append('平台附件列表读取失败')
            rows.append(dict(
                图斑编号=code,
                使用状态=data['use_status_label'],
                地类现状=data['land_actuality_label'],
                检测结果='无法判定',
                平台缺少或待确认材料='平台附件列表读取失败，请重新同步后再检测',
                平台已有附件=_labels(platform_types),
                材料规则='附件状态未知',
                备注=docs_error,
            ))
        elif status < 0 or groups is None:
            unknown_status_count += 1
            land_missing = True
            land_missing_items.append('使用状态未填写或未知')
            rows.append(dict(
                图斑编号=code,
                使用状态=data['use_status_label'],
                地类现状=data['land_actuality_label'],
                检测结果='无法判定',
                平台缺少或待确认材料='使用状态未填写或未知，请先在官方平台填写并重新同步',
                平台已有附件=_labels(platform_types),
                材料规则='未配置',
                备注=record.get('sync_error') or '',
            ))
        else:
            for required_type in groups.get('all', ()):
                if required_type not in platform_types:
                    land_missing = True
                    land_missing_items.append(accessory_label(required_type))
                    rows.append(dict(
                        图斑编号=code,
                        使用状态=data['use_status_label'],
                        地类现状=data['land_actuality_label'],
                        检测结果='平台缺少',
                        平台缺少或待确认材料=accessory_label(required_type),
                        平台已有附件=_labels(platform_types),
                        材料规则='必需',
                        备注='',
                    ))

            any_types = tuple(groups.get('any', ()))
            if any_types and not (set(any_types) & platform_types):
                land_missing = True
                land_missing_items.append(f'任选一：{_labels(any_types)}')
                rows.append(dict(
                    图斑编号=code,
                    使用状态=data['use_status_label'],
                    地类现状=data['land_actuality_label'],
                    检测结果='平台缺少',
                    平台缺少或待确认材料=f'任选一：{_labels(any_types)}',
                    平台已有附件=_labels(platform_types),
                    材料规则='任选一',
                    备注='',
                ))

            conditional = tuple(groups.get('conditional', ()))
            if conditional and not (set(conditional) & platform_types):
                conditional_count += 1
                land_missing = True
                land_missing_items.append(f'条件需要：{_labels(conditional)}')
                rows.append(dict(
                    图斑编号=code,
                    使用状态=data['use_status_label'],
                    地类现状=data['land_actuality_label'],
                    检测结果='待人工确认',
                    平台缺少或待确认材料=f'条件需要：{_labels(conditional)}',
                    平台已有附件=_labels(platform_types),
                    材料规则='条件需要',
                    备注='软件无法判断是否触发条件，请按官方平台页面核实',
                ))

        scene_type = scene_photo_accessory_type(status)
        scene_required = (not docs_error) and scene_photo_required(status, data['land_actuality'])
        if scene_required and scene_type not in platform_types:
            missing_scene_count += 1
            geom = geometry_from_record(record)
            if geom is not None:
                missing_scene_lands.append(dict(data=data, wgs_geom=geom))

        if land_missing:
            geom = geometry_from_record(record)
            if geom is not None:
                missing_material_lands.append(dict(
                    data=data,
                    wgs_geom=geom,
                    missing_summary='；'.join(dict.fromkeys(land_missing_items)) or '缺少或待确认材料',
                ))
            missing_land_count += 1
        else:
            complete_count += 1
            rows.append(dict(
                图斑编号=code,
                使用状态=data['use_status_label'],
                地类现状=data['land_actuality_label'],
                检测结果='平台完整',
                平台缺少或待确认材料='',
                平台已有附件=_labels(platform_types),
                材料规则='',
                备注='',
            ))

        if progress:
            progress(index, total, '检测平台附件')

    fields = list(('图斑编号', '使用状态', '地类现状', '检测结果', '平台缺少或待确认材料', '平台已有附件', '材料规则', '备注'))

    xlsx_path = report_root / '三资平台缺少材料检测报告.xlsx'
    _write_xlsx_report(xlsx_path, fields, rows)

    json_path = report_root / '三资平台缺少材料检测报告.json'
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    kml_path = report_root / '三资平台缺少现场照片.kml'
    export_missing_photo_kml(missing_scene_lands, kml_path)

    all_missing_kml_path = report_root / '三资平台缺少材料图斑.kml'
    export_missing_material_kml(missing_material_lands, all_missing_kml_path)

    summary = dict(
        land_total=len(records_list),
        complete_land_total=complete_count,
        missing_land_total=missing_land_count,
        unknown_status_total=unknown_status_count,
        conditional_confirm_total=conditional_count,
        missing_scene_total=missing_scene_count,
        report_xlsx=str(xlsx_path),
        report_xls=str(xlsx_path),
        report_csv=str(xlsx_path),
        report_json=str(json_path),
        missing_scene_kml=str(kml_path),
        missing_material_kml=str(all_missing_kml_path),
        missing_material_kml_geometry_total=len(missing_material_lands),
        basis='只统计最近一次同步的官方平台已有附件，不计入本地待上传文件',
    )
    summary = add_trace_to_report(summary, 'sanzi_platform_check')

    summary_path = report_root / '三资平台缺少材料检测汇总.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    summary['summary_json'] = str(summary_path)

    return summary
