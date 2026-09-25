# -*- coding: utf-8 -*-
"""بيناري — قاعدة بيانات ذاكرته (SQLite، المكتبة القياسية فقط).

إضافة لا بديل: ملفات JSONL تبقى المصدر الأصلي (ذاكرة الملفات)، وهذه
قاعدة فوقها للبحث النصي الكامل (FTS5) والإحصاء السريع.

  - episodes : كل حدث يصل من memory.log_event
  - messages : كل رسالة تصل من memory.log_message (كل القنوات)
  - insights : كل درس يصل من memory.add_insight
  - notes    : ذكريات يحفظها العقل بنفسه ([[REMEMBER: ...]])
  - goals    : نسخة قراءة من لوح الأهداف
  + جدول افتراضي memory_fts للبحث النصي الكامل العربي والإنجليزي.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime

import memory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("BINARY_DB", os.path.join(BASE_DIR, "binaary.db"))

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts   TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    channel TEXT NOT NULL,
    role    TEXT NOT NULL,
    text    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    lesson  TEXT NOT NULL,
    context TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    kind     TEXT NOT NULL DEFAULT 'note',
    text     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    gid     TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    status  TEXT NOT NULL,
    updated TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    text, kind UNINDEXED, ref_id UNINDEXED, ts UNINDEXED, tokenize='unicode61'
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_episodes_kind ON episodes(kind);
"""


def _get() -> sqlite3.Connection:
    """اتصال واحد لكل عملية مع WAL و foreign_keys — آمن مع الخيط."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA synchronous=NORMAL")
            _conn.executescript(_SCHEMA)
            _conn.commit()
        return _conn


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:2000]


def _fts_add(conn: sqlite3.Connection, text: str, kind: str, ref_id: int, ts: str) -> None:
    conn.execute("INSERT INTO memory_fts (text, kind, ref_id, ts) VALUES (?,?,?,?)",
                 (_clean(text), kind, ref_id, ts))


# ---------------------------------------------------------------- استيراد أولي

_imported = False


def _import_all() -> None:
    """استيراد لمرة واحدة: يملأ القاعدة من ملفات JSONL القديمة إن كانت فارغة."""
    global _imported
    if _imported:
        return
    _imported = True
    conn = _get()
    with _lock:
        row = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
        if row[0] == 0 and os.path.exists(memory._path("episodic")):
            with open(memory._path("episodic"), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ep = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    conn.execute(
                        "INSERT INTO episodes (ts, kind, summary, details) VALUES (?,?,?,?)",
                        (ep.get("ts", ""), ep.get("kind", ""), _clean(ep.get("summary", "")),
                         json.dumps(ep.get("details", {}), ensure_ascii=False)))
                    _fts_add(conn, ep.get("summary", ""), "episode", conn.execute("SELECT last_insert_rowid()").fetchone()[0], ep.get("ts", ""))
        row = conn.execute("SELECT COUNT(*) FROM insights").fetchone()
        if row[0] == 0 and os.path.exists(memory._path("insights")):
            with open(memory._path("insights"), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ins = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cur = conn.execute("INSERT INTO insights (ts, lesson, context) VALUES (?,?,?)",
                                       (ins.get("ts", ""), _clean(ins.get("lesson", "")), _clean(ins.get("context", ""))))
                    _fts_add(conn, ins.get("lesson", ""), "insight", cur.lastrowid, ins.get("ts", ""))
        # محادثات كل القنوات (قديمة وحديثة)
        row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        if row[0] == 0 and os.path.isdir(memory.CONVERSATIONS_DIR):
            for fname in os.listdir(memory.CONVERSATIONS_DIR):
                if not fname.endswith(".jsonl"):
                    continue
                channel = fname[:-6]
                with open(os.path.join(memory.CONVERSATIONS_DIR, fname), "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        cur = conn.execute(
                            "INSERT INTO messages (ts, channel, role, text) VALUES (?,?,?,?)",
                            (msg.get("ts", ""), channel, msg.get("role", ""), _clean(msg.get("text", ""))))
                        _fts_add(conn, msg.get("text", ""), "message", cur.lastrowid, msg.get("ts", ""))
        # الأهداف
        for g in memory.load_goals().get("goals", []):
            conn.execute("INSERT OR REPLACE INTO goals (gid, title, status, updated) VALUES (?,?,?,?)",
                         (g.get("id", ""), _clean(g.get("title", "")), g.get("status", ""), g.get("updated", "")))
        conn.commit()


# ---------------------------------------------------------------- استدعاء من memory.py

def log_event(kind: str, summary: str, details: dict | None = None, ts: str = "") -> None:
    conn = _get()
    with _lock:
        cur = conn.execute("INSERT INTO episodes (ts, kind, summary, details) VALUES (?,?,?,?)",
                           (ts or memory.now(), kind, _clean(summary),
                            json.dumps(details or {}, ensure_ascii=False)))
        _fts_add(conn, summary, "episode", cur.lastrowid, ts or memory.now())
        conn.commit()


def log_message(channel: str, role: str, text: str, ts: str = "") -> None:
    conn = _get()
    with _lock:
        cur = conn.execute("INSERT INTO messages (ts, channel, role, text) VALUES (?,?,?,?)",
                           (ts or memory.now(), channel, role, _clean(text)))
        _fts_add(conn, text, "message", cur.lastrowid, ts or memory.now())
        conn.commit()


def add_insight(lesson: str, context: str = "", ts: str = "") -> None:
    conn = _get()
    with _lock:
        cur = conn.execute("INSERT INTO insights (ts, lesson, context) VALUES (?,?,?)",
                           (ts or memory.now(), _clean(lesson), _clean(context)))
        _fts_add(conn, lesson, "insight", cur.lastrowid, ts or memory.now())
        conn.commit()


def sync_goals(goals: list[dict]) -> None:
    conn = _get()
    with _lock:
        for g in goals:
            conn.execute("INSERT OR REPLACE INTO goals (gid, title, status, updated) VALUES (?,?,?,?)",
                         (g.get("id", ""), _clean(g.get("title", "")), g.get("status", ""), g.get("updated", "")))
        conn.commit()


# ---------------------------------------------------------------- ذكريات العقل

def remember(text: str, *, kind: str = "note") -> int:
    conn = _get()
    with _lock:
        cur = conn.execute("INSERT INTO notes (ts, kind, text) VALUES (?,?,?)",
                           (memory.now(), kind, _clean(text)))
        _fts_add(conn, text, "note", cur.lastrowid, memory.now())
        conn.commit()
        return cur.lastrowid


def notes(limit: int = 20) -> list[dict]:
    conn = _get()
    with _lock:
        rows = conn.execute("SELECT id, ts, kind, text FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- بحث واستعلام

def recall(query: str, *, limit: int = 5) -> list[dict]:
    """بحث نصي كامل في كل الذاكرة (FTS5). يستقبل كلمات مفصولة بمسافات."""
    query = (query or "").strip()
    if not query:
        return []
    _import_all()
    conn = _get()
    fts_query = " ".join(re.findall(r"[\w\u0600-\u06FF]+", query)[:8])
    if not fts_query:
        return []
    try:
        rows = conn.execute(
            "SELECT text, kind, ref_id, ts FROM memory_fts WHERE memory_fts MATCH ? "
            "ORDER BY rank LIMIT ?", (fts_query, limit)).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT text, kind, ref_id, ts FROM memory_fts WHERE text LIKE ? LIMIT ?",
            (f"%{fts_query}%", limit)).fetchall()
    return [{"text": r["text"], "kind": r["kind"], "ref_id": r["ref_id"], "ts": r["ts"]} for r in rows]


def stats() -> dict:
    _import_all()
    conn = _get()
    with _lock:
        counts = {}
        for table in ("episodes", "messages", "insights", "notes", "goals"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    size_kb = os.path.getsize(DB_PATH) / 1024 if os.path.exists(DB_PATH) else 0.0
    return {
        "episodes": counts["episodes"],
        "messages": counts["messages"],
        "insights": counts["insights"],
        "notes": counts["notes"],
        "goals": counts["goals"],
        "size_kb": round(size_kb, 1),
        "path": os.path.basename(DB_PATH),
    }


def days_report(days: int = 7) -> dict:
    """ملخص النشاط عبر الأيام الأخيرة (للعرض في الواجهة)."""
    _import_all()
    conn = _get()
    with _lock:
        rows = conn.execute(
            "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n FROM episodes "
            "WHERE day >= date('now', ?) GROUP BY day ORDER BY day", (f"-{days} days",)).fetchall()
    return {r["day"]: r["n"] for r in rows}


if __name__ == "__main__":
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    print(json.dumps(days_report(), ensure_ascii=False, indent=2))
