"""Roadmap widget state: task checks, stage unlocks, daily quest and streaks.

Stored as plain JSON in ``data/plan.json`` so the tracker survives restarts and
can be backed up by copying one file.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR

PLAN_FILE = DATA_DIR / "plan.json"
BACKUP_FILE = DATA_DIR / "plan.backup.json"

MAX_CUSTOM = 200
MAX_LOG = 300

_lock = threading.RLock()

_STRINGS = ("dailyNote", "sessionNote", "gameTitle", "gameIdea")


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "done": {},
        "counters": {},
        "notes": {},
        "picks": {},
        "custom": [],
        "opened": [],
        "daily": {},
        "streak": 0,
        "bestStreak": 0,
        "lastDay": "",
        "surpriseTask": None,
        "log": [],
        "updated": 0.0,
    }


def _coerce(value: Any) -> dict[str, Any]:
    state = default_state()
    if not isinstance(value, dict):
        return state
    for key in ("done", "counters", "notes", "picks", "daily", "opened"):
        raw = value.get(key)
        if isinstance(raw, dict):
            state[key] = {str(k): v for k, v in raw.items()}
        elif key == "opened" and isinstance(raw, list):
            state[key] = [str(v) for v in raw]
    if isinstance(value.get("custom"), list):
        state["custom"] = [c for c in value["custom"] if isinstance(c, dict) and c.get("id")][
            :MAX_CUSTOM
        ]
    if isinstance(value.get("log"), list):
        state["log"] = [e for e in value["log"] if isinstance(e, dict)][-MAX_LOG:]
    for key in ("streak", "bestStreak"):
        if isinstance(value.get(key), (int, float)):
            state[key] = max(0, int(value[key]))
    for key in ("lastDay", "surpriseTask", *_STRINGS):
        if isinstance(value.get(key), str):
            state[key] = value[key]
    return state


def load() -> dict[str, Any]:
    with _lock:
        for candidate in (PLAN_FILE, BACKUP_FILE):
            try:
                raw = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                return _coerce(json.loads(raw))
            except (ValueError, TypeError):
                continue
        return default_state()


def save(state: dict[str, Any]) -> dict[str, Any]:
    clean = _coerce(state)
    clean["updated"] = time.time()
    with _lock:
        if PLAN_FILE.exists():
            try:
                BACKUP_FILE.write_text(PLAN_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
        PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
        PLAN_FILE.write_text(
            json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return clean


def update(changes: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial client payload into the stored state."""
    state = load()
    for key, value in changes.items():
        if key in ("updated",):
            continue
        if key in ("done", "counters", "notes", "picks", "daily"):
            merged = dict(state.get(key) or {})
            if isinstance(value, dict):
                merged.update({str(k): v for k, v in value.items()})
            state[key] = merged
        elif key in ("opened",):
            merged = list(dict.fromkeys([*state.get("opened", []), *[str(v) for v in value or []]]))
            state[key] = merged
        elif key in ("streak", "bestStreak"):
            if isinstance(value, (int, float)):
                state[key] = max(0, int(value))
        elif key in (*_STRINGS, "lastDay", "surpriseTask"):
            if isinstance(value, str):
                state[key] = value
        elif key == "custom":
            state["custom"] = _merge_custom(state.get("custom") or [], value or [])
        elif key == "customDelete":
            drop = {str(v) for v in (value or [])}
            state["custom"] = [c for c in state["custom"] if c.get("id") not in drop]
        elif key == "log":
            entries = [e for e in (value or []) if isinstance(e, dict)]
            state["log"] = (state["log"] + entries)[-MAX_LOG:]
    return save(state)


def _merge_custom(current: list[dict], incoming: Any) -> list[dict]:
    by_id = {c["id"]: c for c in current if isinstance(c, dict) and c.get("id")}
    order = [c["id"] for c in current if isinstance(c, dict) and c.get("id")]
    for item in incoming:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        key = str(item["id"])
        if key not in by_id:
            order.append(key)
        by_id[key] = {**by_id.get(key, {}), **item}
    return [by_id[k] for k in order][:MAX_CUSTOM]


def reset() -> dict[str, Any]:
    return save(default_state())


def replace(state: dict[str, Any]) -> dict[str, Any]:
    """Full overwrite — used by JSON import from the frontend."""
    return save(state)


def path() -> Path:
    return PLAN_FILE
