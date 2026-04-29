"""
Session Manager — Design Studio 작업 세션 저장/로드
═══════════════════════════════════════════════════════════════════════
파일 시스템에 JSON으로 저장. Railway에선 ephemeral filesystem이라
재배포 시 사라짐 — 진짜 영구 저장은 추후 DB로 확장.

저장 위치: backend/sessions/<session_id>.json
ID 형식: <component>_<timestamp>_<short_hash>
"""

import json
import os
import time
import hashlib
from typing import Any

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sessions')
os.makedirs(SESSIONS_DIR, exist_ok=True)


def _make_id(component: str) -> str:
    """Unique session ID."""
    ts = int(time.time())
    h = hashlib.md5(f"{component}{ts}{os.urandom(4)}".encode()).hexdigest()[:6]
    return f"{component}_{ts}_{h}"


def save_session(session_data: dict, session_id: str = None) -> str:
    """Session 저장. session_id 없으면 새로 생성.
    
    Returns: session_id
    """
    if not session_id:
        session_id = _make_id(session_data.get('component', 'unknown'))

    session_data['id'] = session_id
    session_data['updated_at'] = int(time.time())
    if 'created_at' not in session_data:
        session_data['created_at'] = session_data['updated_at']

    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    return session_id


def load_session(session_id: str) -> dict:
    """Session 로드. 없으면 None."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def list_sessions() -> list[dict]:
    """모든 session 메타 정보 list (간략)."""
    items = []
    if not os.path.isdir(SESSIONS_DIR):
        return items
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            items.append({
                'id': d.get('id', fname[:-5]),
                'name': d.get('name', '(unnamed)'),
                'component': d.get('component', '?'),
                'created_at': d.get('created_at', 0),
                'updated_at': d.get('updated_at', 0),
                'n_data': d.get('n_data', 0),
                'has_calibration': bool(d.get('fitting_optimized')),
                'has_validation': bool(d.get('validation_metrics')),
            })
        except Exception:
            continue
    return items


def delete_session(session_id: str) -> bool:
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except Exception:
        return False
