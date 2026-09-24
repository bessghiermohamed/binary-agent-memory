# -*- coding: utf-8 -*-
"""اختبار دخان لخادم بيناري — بلا اعتماديات.

التشغيل مع خادم حي على 8000:
    python3 test_web.py
"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def post(path: str, body: dict):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    mark = "✓" if cond else "✗"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"{mark} {name}" + (f" — {extra}" if extra and not cond else ""))


# 1) الواجهة
with urllib.request.urlopen(BASE + "/", timeout=10) as r:
    html = r.read().decode("utf-8")
    check("GET / تعيد الواجهة", r.status == 200 and "بيناري" in html)

# 2) الصحة
s, j = get("/api/health")
check("GET /api/health", s == 200 and j.get("ok") is True)

# 3) الحالة
s, j = get("/api/state")
check("GET /api/state (أهداف)", s == 200 and "goals" in j)
check("GET /api/state (عدادات)", "counters" in j and "episodes" in j["counters"])

# 4) العقل
s, j = get("/api/brain")
check("GET /api/brain", s == 200 and j.get("llm_enabled") is True)
check("أدوات العقل معلنة", "SEARCH" in (j.get("tools") or []))

# 5) أمر محلي
s, j = post("/api/messages", {"text": "حالة"})
check("POST حالة (محلي)", s == 200 and "أهداف" in j.get("reply", ""))

# 6) أمر موافقات
s, j = post("/api/messages", {"text": "موافقات"})
check("POST موافقات (محلي)", s == 200 and "reply" in j)

# 7) هدف جديد
s, j = post("/api/messages", {"text": "هدف: اختبار آلي عابر"})
check("POST هدف جديد", s == 200 and "سجّلتُ" in j.get("reply", ""))

# 8) الرسائل المحفوظة
s, j = get("/api/messages?channel=web")
check("GET /api/messages", s == 200 and len(j.get("messages", [])) > 2)

# 9) 404
try:
    get("/api/nothing")
    check("404 للمسار المجهول", False)
except urllib.error.HTTPError as e:
    check("404 للمسار المجهول", e.code == 404)

# 10) رسالة فارغة
try:
    post("/api/messages", {"text": ""})
    check("400 للرسالة الفارغة", False)
except urllib.error.HTTPError as e:
    check("400 للرسالة الفارغة", e.code == 400)

print(f"\nالنتيجة: {PASS} ناجح، {FAIL} فاشل")
raise SystemExit(1 if FAIL else 0)
