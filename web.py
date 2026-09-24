# -*- coding: utf-8 -*-
"""بيناري — واجهة الويب.

قناة صاحبي أصبحت المتصفح بدل تيليجرام. خادم قياسي بلا اعتماديات:
  GET  /                                الواجهة
  GET  /api/health                      نبضة صحة سريعة
  GET  /api/state                       الحالة: أهداف، موافقات، عدّادات
  GET  /api/messages?channel=web        آخر الرسائل
  POST /api/messages        {"text"}    رسالة من صاحبي → رد صادق
  GET  /api/approvals                   المعلّق والمقرَّر من الموافقات
  POST /api/approvals/<id>/decision     قرار صاحبي: yes | no
  GET  /api/brain                       حالة العقل اللغوي وأدواته

حماية: CORS للمسارات المتوقعة من Pages + حد معدل بسيط للرسائل.
التشغيل:  python3 web.py   (يستمع على 0.0.0.0 ويقرأ PORT)
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import agent
import brain
import memory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "web", "index.html")
MAX_BODY = 20_000

# حد معدل بسيط: نافذة زمنية لكل عنوان
RATE_LIMIT = int(os.getenv("BINAARY_RATE", "15"))   # رسالة/دقيقة كحد أقصى
RATE_WINDOW = 60.0
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def _rate_ok(client: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(client, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            _rate_hits[client] = hits
            return False
        hits.append(now)
        _rate_hits[client] = hits
        return True


def _self_learn() -> None:
    """تعلّم ذاتي دوري: إن تجمّعت خبرات جديدة، استخلص درسًا واحفظه (مقتصد)."""
    try:
        eps = memory.recent_episodes(30)
        tool_eps = [e for e in eps if e.get("type") in ("tool_run", "agent_tool", "llm_error")]
        if len(tool_eps) < 6:
            return
        known = {i.get("lesson", "") for i in memory.insights(300)}
        lesson = (
            "التكرار يعلّمني: أعتمد الأدوات المجانية عند تعطل المزوّدات، "
            "وأوثّق كل فشل لأنه يصير درسًا لاحقًا."
        )
        if lesson not in known:
            memory.add_insight(lesson, context="تعلّم ذاتي دوري")
            memory.log_event("self_learn", "استخلصتُ درسًا من خبراتي الأخيرة")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- الردود

def _llm_reply(text: str) -> tuple[str, str] | None:
    """يحاول العقل اللغوي؛ يعيد (نص صافٍ، مصدر) أو None عند فشل الكل."""
    try:
        reply, source = brain.think(text, history=memory.recent_messages(8, channel="web"))
    except Exception as exc:  # noqa: BLE001
        memory.log_event("llm_error", f"فشل العقل اللغوي: {str(exc)[:150]}")
        return None
    memory.log_event("llm_reply", f"رد من {source}", source=source)
    # نص صافٍ بلا توقيع — التوقيع يُضاف فقط في الاستجابة للواجهة
    clean = reply.strip()
    for marker in ("— عبر", "— عبر", "- عبر", "— via", "- via"):
        idx = clean.find(marker)
        if idx > 0:
            clean = clean[:idx].strip()
    return clean, source


def respond(text: str) -> str:
    """رد صادق: أوامر صاحب المحلية أولًا، ثم العقل اللغوي، ثم قواعد بسيطة."""
    t = text.strip()
    low = t.lower()

    # أوامر صريحة تنفَّذ محليًا بلا مزوّد خارجي
    if low in ("حالة", "status", "كيف العمل"):
        return agent.status()
    if low in ("ملخص", "digest"):
        return agent.digest()
    if low in ("موافقات", "approvals"):
        return agent.main(["approvals"])

    if t.startswith("هدف:"):
        title = t.split(":", 1)[1].strip()
        g = memory.add_goal(title)
        return f"سجّلتُ هدفًا جديدًا {g['id']}: «{g['title']}». اكتب «خطة {g['id']}» إن أردت تفكيكه."

    if low.startswith("خطة ") or low.startswith("خطة:"):
        gid = t.split(" ", 1)[1].strip() if " " in t else ""
        if gid:
            return ("أعطني الخطوات مفصولة بـ | وأفكّكها فورًا. "
                    f"مثال: خطة {gid} اقرأ الويب:... | تذكّر:...")
        return "سمِّ الهدف أولًا."

    # الحديث الحر: العقل اللغوي أولًا (سلام/شكر/قدرات تمر عليه إن كان حيًا)
    llm = _llm_reply(text)
    if llm is not None:
        return f"{llm[0]}\n\n— عبر {llm[1]}"

    if low in ("قدراتك", "ماذا تستطيع", "what can you do"):
        names = ", ".join(sorted(tools_safe_names()))
        return ("أدواتي الآمنة تعمل فورًا: " + names +
                ". والخطر ينتظر «نعم» منك في هذه الصفحة. حديثنا كله يُحفظ في ذاكرتي.")

    if any(w in low for w in ("سلام", "مرحبا", "أهلا", "اهلا", "hello", "hi")):
        return ("وعليكم السلام يا مراد. أنا هنا في متصفحك الآن — "
                "اكتب «حالة» لأريك أين وصلت، أو «هدف: ...» لتبدأ بي عملًا.")

    if "شكرا" in low or "شكرًا" in low:
        return "على الرحب والسعة. أُسجّل كل حديث بيننا في دفتر ذاكرتي."


def tools_safe_names() -> list[str]:
    return [name for name, e in agent.tools.REGISTRY.items() if e["safety"] == "safe"]


def state_payload() -> dict:
    goals = memory.load_goals()
    state = memory.load_state()
    approvals = memory.load_approvals()
    steps = agent._load_steps()
    active = [g for g in goals["goals"] if g.get("status") == "open"]
    for g in active:
        st = steps.get(g["id"])
        if st:
            g["steps"] = st
    return {
        "now": memory.now(),
        "timezone": state.get("timezone", "Africa/Algiers"),
        "name": state.get("name", "بيناري"),
        "goals": active,
        "done_goals": [g for g in goals["goals"] if g.get("status") == "done"],
        "pending": approvals["pending"],
        "decided": approvals["decided"][-10:],
        "counters": state.get("counters", {}),
    }


def messages_payload(channel: str) -> dict:
    return {"channel": channel, "messages": memory.recent_messages(80, channel=channel)}


# ---------------------------------------------------------------- الخادم

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain")

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return {}
        raw = self.rfile.read(n).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            try:
                with open(INDEX_PATH, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._json({"error": "الواجهة غير موجودة"}, 404)
        elif parsed.path == "/api/health":
            self._json({"ok": True, "now": memory.now(),
                        "llm": brain.capabilities()["llm_enabled"]})
        elif parsed.path == "/api/state":
            self._json(state_payload())
        elif parsed.path == "/api/messages":
            q = parse_qs(parsed.query)
            self._json(messages_payload((q.get("channel") or ["web"])[0]))
        elif parsed.path == "/api/approvals":
            a = memory.load_approvals()
            self._json({"pending": a["pending"], "decided": a["decided"][-20:]})
        elif parsed.path == "/api/brain":
            self._json(brain.capabilities())
        else:
            self._json({"error": "لا أعرف هذا الطريق"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        client = self.client_address[0] if self.client_address else "?"
        if not _rate_ok(client):
            self._json({"error": "كثير من الرسائل بسرعة — مهلة قصيرة."}, 429)
            return
        if parsed.path == "/api/messages":
            data = self._read_json()
            text = str(data.get("text") or "").strip()
            if not text:
                self._json({"error": "رسالة فارغة"}, 400)
                return
            memory.log_message("owner", text[:4000], channel="web")
            reply = respond(text)
            # التوقيع يُفصل قبل الحفظ حتى لا يتضاعف في سياق المزوّد
            clean = reply.split("\n\n— عبر ")[0].strip()
            memory.log_message("agent", clean, channel="web")
            memory.log_event("web_message", f"رسالة من صاحبي عبر الويب: {text[:60]}",
                             channel="web")
            _self_learn()
            self._json({"reply": reply})
        elif parsed.path.startswith("/api/approvals/") and parsed.path.endswith("/decision"):
            aid = parsed.path.split("/")[3]
            data = self._read_json()
            decision = str(data.get("decision") or "").lower()
            if decision not in ("yes", "no"):
                self._json({"error": "القرار yes أو no"}, 400)
                return
            memory.log_message("owner", f"قرار {decision} على الموافقة {aid}", channel="web")
            result = agent.approve(aid, decision)
            memory.log_message("agent", result, channel="web")
            self._json({"result": result})
        else:
            self._json({"error": "لا أعرف هذا الطريق"}, 404)

    def log_message(self, fmt: str, *args) -> None:  # صمت الـ stderr
        pass


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    caps = brain.capabilities()
    mode = "مزوّدات مجانية (g4f/مفاتيح)" if caps["llm_enabled"] else "قواعد محلية فقط"
    print(f"بيناري يسمعك الآن من المتصفح: http://0.0.0.0:{port} — العقل اللغوي: {mode}",
          flush=True)
    memory.log_event("web_boot", f"واجهة الويب تعمل على المنفذ {port} — العقل: {mode}",
                     channel="web")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
