# -*- coding: utf-8 -*-
"""ذاكرة بيناري — الذاكرة الإجرائية للوكيل المستقل.

كل شيء محفوظ في ملفات نصية داخل هذا المستودع: أهداف، أحداث، دروس،
طلبات موافقة، حالة تشغيل، ومحادثات حديثة. المكتبة القياسية فقط.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.getenv("BINARY_TIMEZONE", "Africa/Algiers"))
except Exception:  # pragma: no cover
    TZ = timezone.utc

# قاعدة بيانات الذاكرة: إضافة فوق الملفات، وأي فشل فيها لا يعطل الذاكرة أبدًا
try:
    import memory_db as _db
except Exception:  # pragma: no cover
    _db = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILES = {
    "goals": "goals.json",
    "approvals": "approvals.json",
    "state": "state.json",
}
JSONL_FILES = {
    "episodic": "episodic.jsonl",
    "insights": "insights.jsonl",
}
CONVERSATIONS_DIR = os.path.join(BASE_DIR, "conversations")

_lock = threading.Lock()


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _path(kind: str) -> str:
    if kind in FILES:
        return os.path.join(BASE_DIR, FILES[kind])
    if kind in JSONL_FILES:
        return os.path.join(BASE_DIR, JSONL_FILES[kind])
    raise KeyError(kind)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- الحالة العامة

def load_state() -> dict[str, Any]:
    with _lock:
        state = _read_json(_path("state"), {})
        state.setdefault("owner", "Murad")
        state.setdefault("timezone", "Africa/Algiers")
        state.setdefault("budgets", {"llm_calls_per_day": 50})
        state.setdefault("locks", {})
        state.setdefault("counters", {"episodes": 0, "insights": 0})
        return state


def save_state(state: dict[str, Any]) -> None:
    with _lock:
        _write_json(_path("state"), state)


def acquire_lock(name: str) -> bool:
    state = load_state()
    locks: dict[str, str] = state.setdefault("locks", {})
    if name in locks and locks[name] != "expired":
        return False
    locks[name] = now()
    save_state(state)
    return True


def release_lock(name: str) -> None:
    state = load_state()
    state.setdefault("locks", {}).pop(name, None)
    save_state(state)


# ---------------------------------------------------------------- الأهداف

def load_goals() -> dict[str, Any]:
    with _lock:
        return _read_json(_path("goals"), {"goals": []})


def save_goals(data: dict[str, Any]) -> None:
    with _lock:
        _write_json(_path("goals"), data)


def add_goal(title: str, *, priority: int = 2, note: str = "") -> dict[str, Any]:
    goals = load_goals()
    gid = f"g{len(goals['goals']) + 1:03d}"
    goal = {
        "id": gid,
        "title": title.strip(),
        "priority": int(priority),
        "status": "open",
        "note": note.strip(),
        "created": now(),
        "updated": now(),
    }
    goals["goals"].append(goal)
    save_goals(goals)
    if _db is not None:
        try:
            _db.sync_goals(goals["goals"])
        except Exception:  # noqa: BLE001
            pass
    return goal


def update_goal_status(gid: str, status: str) -> dict[str, Any] | None:
    goals = load_goals()
    for g in goals["goals"]:
        if g["id"] == gid:
            g["status"] = status
            g["updated"] = now()
            save_goals(goals)
            if _db is not None:
                try:
                    _db.sync_goals(goals["goals"])
                except Exception:  # noqa: BLE001
                    pass
            return g
    return None


def open_goals() -> list[dict[str, Any]]:
    return [g for g in load_goals()["goals"] if g.get("status") == "open"]


# ---------------------------------------------------------------- السجل الزمني

def log_event(kind: str, summary: str, **details: Any) -> dict[str, Any]:
    episode = {"ts": now(), "kind": kind, "summary": summary}
    if details:
        episode["details"] = details
    with _lock:
        path = _path("episodic")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")
    if _db is not None:
        try:
            _db.log_event(kind, summary, details or {}, ts=episode["ts"])
        except Exception:  # noqa: BLE001
            pass
    state = load_state()
    state["counters"]["episodes"] = state["counters"].get("episodes", 0) + 1
    save_state(state)
    return episode


def recent_episodes(limit: int = 20) -> list[dict[str, Any]]:
    path = _path("episodic")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ---------------------------------------------------------------- الدروس

def add_insight(lesson: str, *, context: str = "") -> dict[str, Any]:
    with _lock:
        existing: list[dict[str, Any]] = []
        path = _path("insights")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            existing.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        for item in existing:
            if item.get("lesson", "").strip() == lesson.strip():
                return item
        insight = {"ts": now(), "lesson": lesson.strip(), "context": context.strip()}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(insight, ensure_ascii=False) + "\n")
    if _db is not None:
        try:
            _db.add_insight(insight["lesson"], insight["context"], ts=insight["ts"])
        except Exception:  # noqa: BLE001
            pass
    state = load_state()
    state["counters"]["insights"] = state["counters"].get("insights", 0) + 1
    save_state(state)
    return insight


def insights(limit: int = 50) -> list[dict[str, Any]]:
    path = _path("insights")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------- الموافقات

def load_approvals() -> dict[str, Any]:
    with _lock:
        return _read_json(_path("approvals"), {"pending": [], "decided": []})


def save_approvals(data: dict[str, Any]) -> None:
    with _lock:
        _write_json(_path("approvals"), data)


def request_approval(tool: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
    approvals = load_approvals()
    aid = f"a{len(approvals['pending']) + len(approvals['decided']) + 1:03d}"
    req = {"id": aid, "tool": tool, "args": args, "reason": reason,
           "requested": now(), "status": "pending"}
    approvals["pending"].append(req)
    save_approvals(approvals)
    return req


def decide_approval(aid: str, decision: str) -> dict[str, Any] | None:
    approvals = load_approvals()
    for req in approvals["pending"]:
        if req["id"] == aid:
            approvals["pending"].remove(req)
            req["status"] = decision
            req["decided"] = now()
            approvals["decided"].append(req)
            save_approvals(approvals)
            return req
    return None


def find_approval(aid: str) -> dict[str, Any] | None:
    for req in load_approvals()["pending"]:
        if req["id"] == aid:
            return req
    return None


# ---------------------------------------------------------------- المحادثات

def _conversations_path(channel: str = "web") -> str:
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    safe = "".join(c for c in channel if c.isalnum() or c in "-_") or "web"
    return os.path.join(CONVERSATIONS_DIR, f"{safe}.jsonl")


def log_message(role: str, text: str, *, channel: str = "web") -> None:
    entry = {"ts": now(), "role": role, "channel": channel, "text": text}
    with _lock:
        with open(_conversations_path(channel), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if _db is not None:
        try:
            _db.log_message(channel, role, text, ts=entry["ts"])
        except Exception:  # noqa: BLE001
            pass


def recent_messages(limit: int = 40, *, channel: str = "web") -> list[dict[str, Any]]:
    path = _conversations_path(channel)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
