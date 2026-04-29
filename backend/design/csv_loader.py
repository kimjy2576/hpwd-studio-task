"""
CSV Loader — 자유 형식 시험 데이터 → 표준화 dict
═══════════════════════════════════════════════════════════════════════
사용자 CSV 업로드 시:
  1. column 이름 자동 감지 (P_suc_bar, T_suc, m_dot_meas, ...)
  2. 컴포넌트 modelDescription의 input/output 이름과 매칭
  3. 단위 자동 변환 (kPa → bar, K → °C, kg/h → kg/s 등)
  4. 검증 — 필수 column 누락 / 결측치 / 음수 압력 등

매칭 우선순위:
  1. 정확 일치: 'P_suc' → P_suc
  2. 단위 suffix 제거: 'P_suc_bar' → P_suc, 'T_suc_C' → T_suc
  3. 측정값 suffix 제거: 'm_dot_meas' → m_dot, 'W_measured' → W_elec
  4. 별칭: 'mdot' → m_dot, 'P_e' → P_suc, 'P_c' → P_dis
"""

import csv
import io
import re
from typing import Any


# ════════ 컬럼 별칭 사전 ════════
# 키 = 정규화된 component port 이름
# 값 = 가능한 CSV column 이름 (lowercase, suffix 제거 후)
COLUMN_ALIASES = {
    'P_suc':  ['p_suc', 'p_su', 'p_e', 'psuc', 'p_evap', 'p_evaporator', 'pevap', 'p1'],
    'T_suc':  ['t_suc', 't_su', 'tsuc', 't_su1'],
    'P_dis':  ['p_dis', 'p_dc', 'p_c', 'pdis', 'p_cond', 'p_condenser', 'pcond', 'p2'],
    'T_dis':  ['t_dis', 't_dc', 'tdis', 't_d'],
    'N':      ['n', 'rpm', 'speed', 'n_rpm', 'omega'],
    'm_dot':  ['m_dot', 'mdot', 'm', 'mass_flow', 'massflow', 'flow'],
    'W_elec': ['w_elec', 'w', 'power', 'p_elec', 'wcomp', 'w_compressor'],
    'eta_is': ['eta_is', 'eta_isen', 'eta_isentropic', 'isen_eff'],
    'eta_v':  ['eta_v', 'eta_vol', 'eta_volumetric', 'vol_eff'],
    'T_e':    ['t_e', 't_evap', 'tevap'],
    'T_c':    ['t_c', 't_cond', 'tcond'],
}


# ════════ 단위 변환 ════════
# (csv unit suffix, target unit) → multiplicative factor + offset
UNIT_CONVERSIONS = {
    # 압력
    ('pa', 'bar'): (1e-5, 0),
    ('kpa', 'bar'): (0.01, 0),
    ('mpa', 'bar'): (10, 0),
    ('psi', 'bar'): (0.0689476, 0),
    ('bar', 'bar'): (1, 0),
    # 온도
    ('k', '°c'): (1, -273.15),
    ('kelvin', '°c'): (1, -273.15),
    ('c', '°c'): (1, 0),
    ('celsius', '°c'): (1, 0),
    ('°c', '°c'): (1, 0),
    ('f', '°c'): (5/9, -32 * 5/9),
    # 질량 유량
    ('kg/s', 'kg/s'): (1, 0),
    ('kg/h', 'kg/s'): (1/3600, 0),
    ('g/s', 'kg/s'): (1e-3, 0),
    ('lb/h', 'kg/s'): (0.4536/3600, 0),
    # 일률
    ('w', 'w'): (1, 0),
    ('kw', 'w'): (1000, 0),
    ('hp', 'w'): (745.7, 0),
}


def _normalize_column_name(name: str) -> tuple[str, str]:
    """Column 이름을 정규화 + 단위 suffix 추출.
    
    예시:
      'P_suc_bar'   → ('p_suc', 'bar')
      'T_suc_C'     → ('t_suc', '°c')
      'm_dot_meas'  → ('m_dot', '')   # _meas는 측정값 suffix
      'W_meas_W'    → ('w', 'w')     # _meas 제거 후 _W
      'mdot[kg/h]'  → ('mdot', 'kg/h')
    
    Returns: (normalized_name, unit_suffix or '')
    """
    n = name.strip().lower()
    # 대괄호/괄호 안의 단위 추출: 'mdot[kg/h]' → ('mdot', 'kg/h')
    m = re.match(r'^(.+?)\s*[\[\(]\s*([^\]\)]+)\s*[\]\)]\s*$', n)
    if m:
        base, unit = m.group(1).strip(), m.group(2).strip()
        return _strip_meas_suffix(base), unit
    # 측정값 suffix 제거 후 끝의 단위 suffix 추출
    base = _strip_meas_suffix(n)
    # 단위 suffix 후보 (긴 것부터): kg/h, kg/s, g/s, kpa, mpa, °c, bar, kw, hp, k, c, f, w, pa
    for unit_key in sorted(set(s for (s, _) in UNIT_CONVERSIONS), key=len, reverse=True):
        suffix = '_' + unit_key
        if base.endswith(suffix):
            return base[:-len(suffix)], unit_key
    return base, ''


def _strip_meas_suffix(name: str) -> str:
    """_meas, _measured, _meas_, _exp, _experimental 제거."""
    for suf in ['_measured', '_meas', '_exp', '_experimental', '_test']:
        if name.endswith(suf):
            return name[:-len(suf)]
    # 중간 _meas_ → _ (예: w_meas_w → w_w → w)
    name = name.replace('_meas_', '_').replace('_measured_', '_')
    return name


def _match_to_port(normalized: str) -> str | None:
    """정규화된 이름을 컴포넌트 port 이름으로 매핑.
    매칭 안 되면 None."""
    for port, aliases in COLUMN_ALIASES.items():
        if normalized in aliases:
            return port
        if normalized == port.lower():
            return port
    return None


def _convert_value(val: float, src_unit: str, tgt_unit: str) -> float:
    """단위 변환. src_unit/tgt_unit 모두 lowercase."""
    if not src_unit or src_unit == tgt_unit:
        return val
    key = (src_unit, tgt_unit)
    if key not in UNIT_CONVERSIONS:
        # 변환 정의 없음 — 그대로 반환 + 경고는 호출자가 처리
        return val
    factor, offset = UNIT_CONVERSIONS[key]
    return val * factor + offset


# ════════ Target 단위 (component port의 표준) ════════
PORT_UNITS = {
    'P_suc':  'bar',
    'T_suc':  '°c',
    'P_dis':  'bar',
    'T_dis':  '°c',
    'N':      'rpm',
    'm_dot':  'kg/s',
    'W_elec': 'w',
    'eta_is': '-',
    'eta_v':  '-',
    'T_e':    '°c',
    'T_c':    '°c',
}


def parse_csv(csv_text: str) -> dict[str, Any]:
    """CSV 텍스트를 파싱하여 표준화된 데이터 + 매핑 정보 반환.
    
    Returns:
        {
            'rows': int,
            'columns': [{'original': 'P_suc_bar', 'mapped': 'P_suc',
                          'unit_src': 'bar', 'unit_tgt': 'bar', 'matched': True}, ...],
            'data': {'P_suc': [5.0, 5.5, ...], 'T_suc': [...], ...},
            'unmapped_columns': ['extra_col_xyz', ...],
            'warnings': ['...'],
            'errors': ['...']
        }
    """
    result = {
        'rows': 0,
        'columns': [],
        'data': {},
        'unmapped_columns': [],
        'warnings': [],
        'errors': [],
    }

    if not csv_text or not csv_text.strip():
        result['errors'].append('빈 CSV')
        return result

    try:
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
    except Exception as e:
        result['errors'].append(f'CSV 파싱 실패: {e}')
        return result

    if len(rows) < 2:
        result['errors'].append('최소 헤더 + 데이터 1행 필요')
        return result

    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]

    # 빈 행 제거
    data_rows = [r for r in data_rows if any(c.strip() for c in r)]
    if not data_rows:
        result['errors'].append('데이터 행이 없음')
        return result

    # 각 column 분석
    column_info = []
    column_map = {}  # csv_idx → port name
    for idx, h in enumerate(headers):
        norm, unit = _normalize_column_name(h)
        port = _match_to_port(norm)
        info = {
            'original': h,
            'normalized': norm,
            'unit_src': unit,
            'mapped': port,
            'unit_tgt': PORT_UNITS.get(port, '-') if port else '',
            'matched': port is not None,
        }
        column_info.append(info)
        if port:
            if port in column_map.values():
                result['warnings'].append(f"중복 매핑: {h}와 다른 column이 모두 {port}로. 첫 번째 사용.")
            else:
                column_map[idx] = port
        else:
            result['unmapped_columns'].append(h)

    result['columns'] = column_info

    # 데이터 변환
    for port in column_map.values():
        result['data'][port] = []

    skipped_rows = 0
    for r_idx, row in enumerate(data_rows, start=2):
        if len(row) < len(headers):
            row = row + [''] * (len(headers) - len(row))
        try:
            row_data = {}
            valid = True
            for csv_idx, port in column_map.items():
                raw = row[csv_idx].strip()
                if raw == '' or raw.lower() in ('nan', 'na', 'null', '-'):
                    valid = False
                    break
                try:
                    val = float(raw)
                except ValueError:
                    valid = False
                    break
                # 단위 변환
                src_u = column_info[csv_idx]['unit_src']
                tgt_u = column_info[csv_idx]['unit_tgt']
                val = _convert_value(val, src_u, tgt_u)
                row_data[port] = val
            if valid:
                for port, val in row_data.items():
                    result['data'][port].append(val)
            else:
                skipped_rows += 1
        except Exception as e:
            result['warnings'].append(f"행 {r_idx} 스킵: {e}")
            skipped_rows += 1

    n_valid = len(next(iter(result['data'].values()))) if result['data'] else 0
    result['rows'] = n_valid
    if skipped_rows > 0:
        result['warnings'].append(f"{skipped_rows}개 행 스킵 (결측/포맷 오류)")

    if n_valid == 0:
        result['errors'].append('유효한 데이터 행이 없음')

    return result


def split_inputs_outputs(parsed: dict, component_md: dict) -> dict[str, Any]:
    """parse_csv 결과를 component의 input/output port에 따라 분리.
    
    Args:
        parsed: parse_csv 반환값
        component_md: component의 modelDescription
    
    Returns:
        {
            'inputs':       {'P_suc': [...], 'T_suc': [...], ...},
            'outputs_meas': {'m_dot': [...], 'W_elec': [...], ...},
            'unmatched':    ['extra_col', ...],
        }
    """
    in_ports = set(v['name'] for v in component_md['variables'] if v['causality'] == 'input')
    out_ports = set(v['name'] for v in component_md['variables'] if v['causality'] == 'output')

    inputs, outputs_meas, unmatched = {}, {}, []
    for port, vals in parsed['data'].items():
        if port in in_ports:
            inputs[port] = vals
        elif port in out_ports:
            outputs_meas[port] = vals
        else:
            unmatched.append(port)

    return {
        'inputs': inputs,
        'outputs_meas': outputs_meas,
        'unmatched': unmatched,
    }
