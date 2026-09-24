# -*- coding: utf-8 -*-
"""أدوات بيناري — يدير ما يستطيع الوكيل فعله فعليًا.

أداة = دالة بايثون نقية + وصف عربي + تصنيف أمان:
  safe     → تُنفّذ فورًا
  risky    → تنتظر موافقة صاحبها (تُسجَّل في approvals.json)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Any, Callable

import memory

APPROVAL_REQUIRED = {"shell", "write_file_outside", "http_post", "http_delete"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTTP_TIMEOUT = 15


# ---------------------------------------------------------------- الأدوات الآمنة

def read_file(path: str, limit: int = 100) -> str:
    """يقرأ ملفًا نصيًا داخل المستودع."""
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    if not os.path.dirname(full).startswith(BASE_DIR):
        return "خطأ: القراءة مسموحة داخل المستودع فقط."
    if not os.path.isfile(full):
        return f"خطأ: لا يوجد ملف «{path}»."
    with open(full, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) > limit:
        head = "".join(lines[:limit])
        return head + f"\n… (الملف كله {len(lines)} سطرًا)"
    return "".join(lines) or "(ملف فارغ)"


def write_file(path: str, content: str) -> str:
    """يكتب ملفًا نصيًا داخل المستودع."""
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    if not os.path.dirname(full).startswith(BASE_DIR):
        return "خارج المستودع: يحتاج موافقة صاحبي (write_file_outside)."
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return f"كتبتُ «{path}» ({len(content)} محرفًا)."


def list_files(path: str = ".") -> str:
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    if not full.startswith(BASE_DIR):
        return "خطأ: العرض مسموح داخل المستودع فقط."
    entries = sorted(os.listdir(full))
    out = []
    for name in entries:
        sub = os.path.join(full, name)
        kind = "مجلد" if os.path.isdir(sub) else "ملف"
        out.append(f"{name} — {kind}")
    return "\n".join(out) or "(فارغ)"


def remember(lesson: str, context: str = "") -> str:
    memory.add_insight(lesson, context=context)
    return "حفظتُ الدرس في دفتر خبراتي."


def recall(topic: str = "") -> str:
    items = memory.insights(limit=100)
    if topic:
        topic_l = topic.strip().lower()
        items = [i for i in items
                 if topic_l in i.get("lesson", "").lower()
                 or topic_l in i.get("context", "").lower()]
    if not items:
        return "لا شيء بعد في هذا الباب."
    return "\n".join(f"- [{i['ts']}] {i['lesson']}" for i in items)


def add_goal(title: str, priority: int = 2, note: str = "") -> str:
    goal = memory.add_goal(title, priority=priority, note=note)
    return f"سجّلتُ الهدف {goal['id']}: «{goal['title']}»."


def complete_goal(goal_id: str) -> str:
    goal = memory.update_goal_status(goal_id, "done")
    return f"أنجزتُ الهدف {goal_id}." if goal else f"لا أجد هدفًا برقم {goal_id}."


def goals() -> str:
    items = memory.load_goals()["goals"]
    if not items:
        return "لوحة الأهداف فارغة."
    lines = []
    for g in items:
        mark = "•" if g["status"] == "open" else "✓"
        lines.append(f"{mark} {g['id']} [{أولوية_نص(g['priority'])}] {g['title']}")
    return "\n".join(lines)


def أولوية_نص(p: int) -> str:
    return {1: "عالية", 2: "متوسطة", 3: "منخفضة"}.get(p, "متوسطة")


def http_get(url: str) -> str:
    """GET لروابط http/https — آمن لأنه قراءة فقط."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "خطأ: العنوان يجب أن يبدأ بـ http أو https."
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Binaary/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read(20_000).decode("utf-8", errors="replace")
        return f"HTTP {resp.status} — أول 20000 محرف:\n{body}"
    except Exception as exc:  # noqa: BLE001
        return f"فشل الطلب: {exc}"


# ---------------------------------------------------------------- الأدوات الخطر

def shell(command: str) -> str:
    """أمر نظام كامل — خطر، ينتظر موافقة صاحبي دائمًا."""
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        text = out or err or "(بلا مخرجات)"
        return f"رمز الخروج {proc.returncode}\n{text[:4000]}"
    except subprocess.TimeoutExpired:
        return "انتهت مهلة الأمر (30 ثانية)."


# ---------------------------------------------------------------- السجل المركزي

REGISTRY: dict[str, dict[str, Any]] = {
    "read_file": {
        "fn": read_file, "safety": "safe",
        "desc": "قراءة ملف نصي داخل المستودع",
        "args": {"path": "str", "limit": "int اختياري"},
    },
    "write_file": {
        "fn": write_file, "safety": "safe",
        "desc": "كتابة ملف نصي داخل المستودع",
        "args": {"path": "str", "content": "str"},
    },
    "write_file_outside": {
        "fn": None, "safety": "risky",
        "desc": "كتابة ملف خارج المستودع",
        "args": {"path": "str", "content": "str"},
    },
    "list_files": {
        "fn": list_files, "safety": "safe",
        "desc": "عرض محتويات مجلد داخل المستودع",
        "args": {"path": "str اختياري"},
    },
    "remember": {
        "fn": remember, "safety": "safe",
        "desc": "حفظ درس جديد في دفتر الخبرات",
        "args": {"lesson": "str", "context": "str اختياري"},
    },
    "recall": {
        "fn": recall, "safety": "safe",
        "desc": "استرجاع دروس محفوظة",
        "args": {"topic": "str اختياري"},
    },
    "add_goal": {
        "fn": add_goal, "safety": "safe",
        "desc": "إضافة هدف إلى اللوحة",
        "args": {"title": "str", "priority": "1..3 اختياري", "note": "str اختياري"},
    },
    "complete_goal": {
        "fn": complete_goal, "safety": "safe",
        "desc": "إنجاز هدف بالمعرّف",
        "args": {"goal_id": "str"},
    },
    "goals": {
        "fn": lambda: goals(), "safety": "safe",
        "desc": "عرض لوحة الأهداف",
        "args": {},
    },
    "http_get": {
        "fn": http_get, "safety": "safe",
        "desc": "طلب HTTP GET لقراءة مورد من الويب",
        "args": {"url": "str"},
    },
    "shell": {
        "fn": shell, "safety": "risky",
        "desc": "تنفيذ أمر نظام — خطر",
        "args": {"command": "str"},
    },
    "http_post": {
        "fn": None, "safety": "risky",
        "desc": "إرسال بيانات خارجيًا — خطر",
        "args": {"url": "str", "data": "object"},
    },
    "http_delete": {
        "fn": None, "safety": "risky",
        "desc": "حذف مورد خارجي — خطر",
        "args": {"url": "str"},
    },
}


def run(tool: str, args: dict[str, Any], *, requester: str = "self") -> str:
    """ينفّذ أداة. الخطر يُسجَّل كموافقة معلّقة ويُرجع الطلب بدل التنفيذ."""
    entry = REGISTRY.get(tool)
    if entry is None:
        return f"لا أملك أداة اسمها «{tool}». أمتلك: {', '.join(sorted(REGISTRY))}"

    if entry["safety"] == "risky":
        req = memory.request_approval(tool, args, entry["desc"])
        memory.log_event("approval_requested", f"طلب موافقة {req['id']} لأداة {tool}",
                         tool=tool, args=args)
        return (f"هذه الأداة خطر ({entry['desc']}). سجّلتُ طلب الموافقة "
                f"{req['id']} في approvals.json — أناَك التنفيذ بعد «نعم» من صاحبي.")

    fn = entry["fn"]
    if fn is None:
        return f"أداة «{tool}» معرّفة لكن غير مربوطة بعد."
    try:
        result = fn(**args)
    except TypeError as exc:
        return f"معطيات غير صحيحة لـ «{tool}»: {exc}"
    except Exception as exc:  # noqa: BLE001
        result = f"فشلت الأداة «{tool}»: {exc}"
    memory.log_event("tool_run", f"نفّذت {tool}", tool=tool, args=args)
    return result
