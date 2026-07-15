# Source Generated with Decompyle++
# File: sanzi_rules.pyc (Python 3.11)

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Sequence

USE_STATUS_LABELS: 'Dict[int, str]' = {
    0: '对外发包',
    1: '不规范使用',
    2: '征收征占',
    3: '闲置',
    4: '外部（内部）飞地',
    5: '村民自留地（菜地）',
    6: '抵顶地',
    7: '村集体自用-经营性',
    8: '村集体自用-公共性',
    9: '争议待确权地',
    10: '田间硬化路面',
    11: '村民自用',
    12: '无争议未确权承包地',
    13: '延包后村集体再分地',
    14: '已确权承包地',
}
LAND_ACTUALITY_LABELS: 'Dict[int, str]' = {
    0: '耕地',
    1: '林地',
    2: '园地',
    3: '工矿仓储用地',
    4: '商业服务业设施用地',
    5: '养殖水面（坑塘水面）',
    6: '四荒地',
    7: '滩涂',
    8: '设施农用地',
    9: '田埂地边地',
    10: '宅基地',
    11: '交通运输用地',
    12: '公共管理与公共服务用地',
    13: '水域及水利设施用地',
    14: '城镇住宅用地',
}
LAND_STATUS_LABELS = {
    0: '未完成',
    1: '进行中',
    2: '已完成',
}

ACCESSORY_TYPE_LABELS: 'Dict[int, str]' = {
    0: '合同',
    1: '对外发包会议纪要',
    2: '对外发包现场照片',
    3: '入账凭证',
    4: '收据照片',
    5: '现场照片',
    6: '要件会议记录',
    7: '要件公示照片',
    8: '征收征占批文',
    11: '会议纪要',
    13: '村级会议记录',
    14: '现场公示照片',
    15: '飞地证明文件',
    16: '证明文件',
    17: '分地台账照片',
    18: '营业执照',
    19: '村委会证明',
    20: '原始分地会议记录',
}

USE_STATUS_REQUIREMENT_TYPES: 'Dict[int, Sequence[int]]' = {
    0: (0, 1, 2, 3, 16),
    1: (),
    2: (0, 8),
    3: (5, 16),
    4: (15,),
    5: (5, 11, 16),
    6: (17, 16),
    7: (11, 16, 18, 5),
    8: (5,),
    9: (0, 19),
    10: (5,),
    11: (11, 16, 5),
    12: (17, 20, 13, 16, 0),
    13: (5, 11, 16),
    14: (16,),
}

USE_STATUS_REQUIREMENT_GROUPS: Dict[int, Dict[str, tuple[int, ...]]] = {
    0: {'all': (0, 1, 2, 3), 'conditional': (16,), 'any': ()},
    1: {'all': (), 'conditional': (), 'any': ()},
    2: {'all': (), 'conditional': (), 'any': (0, 8)},
    3: {'all': (5,), 'conditional': (), 'any': (16,)},
    4: {'all': (15,), 'conditional': (), 'any': ()},
    5: {'all': (5,), 'conditional': (), 'any': (11, 16)},
    6: {'all': (), 'conditional': (), 'any': (17, 16)},
    7: {'all': (18, 5), 'conditional': (), 'any': (11, 16)},
    8: {'all': (5,), 'conditional': (), 'any': ()},
    9: {'all': (), 'conditional': (), 'any': (0, 19)},
    10: {'all': (5,), 'conditional': (), 'any': ()},
    11: {'all': (5,), 'conditional': (), 'any': (11, 16)},
    12: {'all': (), 'conditional': (), 'any': (17, 20, 13, 16, 0)},
    13: {'all': (5,), 'conditional': (), 'any': (11, 16)},
    14: {'all': (16,), 'conditional': (), 'any': ()},
}

PROOF_ACCESSORY_BY_STATUS: 'Dict[int, int]' = {
    0: 16,
    3: 16,
    4: 15,
    5: 16,
    6: 16,
    7: 16,
    9: 19,
    11: 16,
    12: 16,
    13: 16,
    14: 16,
}

SCENE_PHOTO_ACCESSORY_BY_STATUS: 'Dict[int, int]' = {
    0: 2,
}

GENERATABLE_TYPES_BY_STATUS: 'Dict[int, Sequence[int]]' = {
    status: (accessory_type,) for status, accessory_type in PROOF_ACCESSORY_BY_STATUS.items()
}

CAN_GENERATE_WORD_TYPES = frozenset({0, 2, 3, 4, 5, 8, 18})


@dataclass
class MaterialRequirement:
    accessory_type: int = 0
    label: str = ''
    rule: str = ''
    can_generate_word: bool = False


def normalize_int(value, default=None):
    if value is None or value == '':
        return default
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def use_status_label(value):
    code = normalize_int(value)
    return USE_STATUS_LABELS.get(code, '未填写' if code < 0 else f'未知状态({code})')


def land_actuality_label(value):
    code = normalize_int(value)
    return LAND_ACTUALITY_LABELS.get(code, '未填写' if code < 0 else f'未知地类({code})')


def land_status_label(value):
    code = normalize_int(value)
    return LAND_STATUS_LABELS.get(code, '未知')


def accessory_label(accessory_type):
    return ACCESSORY_TYPE_LABELS.get(normalize_int(accessory_type), f'附件类别{accessory_type}')


def is_villager_homestead(use_status, land_actuality):
    """村民自用且地类为宅基地：现场照片不再作为必填材料。"""
    return normalize_int(use_status) == 11 and normalize_int(land_actuality) == 10


def effective_requirement_groups(use_status, land_actuality) -> Dict[str, tuple[int, ...]] | None:
    status = normalize_int(use_status)
    groups = USE_STATUS_REQUIREMENT_GROUPS.get(status)
    if groups is None:
        return None
    result = {key: tuple(groups.get(key, ())) for key in ('all', 'any', 'conditional')}
    if is_villager_homestead(status, land_actuality):
        result['all'] = tuple(x for x in result['all'] if x != 5)
        result['any'] = tuple(x for x in result['any'] if x != 5)
        result['conditional'] = tuple(x for x in result['conditional'] if x != 5)
    return result


def scene_photo_required(use_status, land_actuality):
    groups = effective_requirement_groups(use_status, land_actuality)
    if groups is None:
        return False
    scene_type = scene_photo_accessory_type(use_status)
    return scene_type in set(groups.get('all', ()))


def requirements_for_status(use_status, land_actuality) -> List[MaterialRequirement]:
    status = normalize_int(use_status)
    groups = effective_requirement_groups(status, land_actuality) or {'all': (), 'any': (), 'conditional': ()}
    result = []
    generated = set(GENERATABLE_TYPES_BY_STATUS.get(status, ()))
    for kind, rule_text in (('all', '必需'), ('any', '任选一'), ('conditional', '条件需要')):
        for accessory_type in groups.get(kind, ()):
            result.append(
                MaterialRequirement(
                    accessory_type=accessory_type,
                    label=accessory_label(accessory_type),
                    rule=rule_text,
                    can_generate_word=accessory_type in generated,
                )
            )
    return result


def generatable_types_for_status(use_status) -> List[int]:
    return list(GENERATABLE_TYPES_BY_STATUS.get(normalize_int(use_status), ()))


def proof_accessory_type(use_status):
    return PROOF_ACCESSORY_BY_STATUS.get(normalize_int(use_status), -1)


def proof_material_name(use_status):
    status = normalize_int(use_status)
    if status not in PROOF_ACCESSORY_BY_STATUS:
        return ''
    names = {
        3: '闲置情况证明',
        4: '外部（内部）飞地证明',
        5: '村民自留地（菜地）权属证明',
        6: '抵顶地证明',
        7: '村集体自用-经营性证明',
        9: '争议待确权地证明',
        11: '村民自用宅基地证明',
        12: '无争议未确权承包地证明',
        13: '延包后村集体再分地证明',
        14: '已确权承包地证明',
    }
    return names.get(status, '情况证明')


def scene_photo_accessory_type(use_status):
    return SCENE_PHOTO_ACCESSORY_BY_STATUS.get(normalize_int(use_status), 5)


def expected_filename(landcode, accessory_type, material_name, extension='.pdf'):
    ext = extension if extension.startswith('.') else '.' + extension
    safe_name = ''.join(
        '_' if ch in '<>:"/\\|?*' else ch for ch in str(material_name)
    ).strip(' ._')
    return f'{landcode}_{safe_name}{ext.lower()}'
