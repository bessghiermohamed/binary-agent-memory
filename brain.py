# -*- coding: utf-8 -*-
"""بيناري — العقل اللغوي.

قناة صاحبي صارت الويب، وقدرته اللغوية صارت حقيقية عبر مزوّدات مجانية
(GPT4Free / g4f) — بلا ادعاء: كل رد قادم من مزوّد فعلي يُذكر اسمه،
وكل فشل يُعلن صريحًا مع رجوع آمن للردود القواعدية المحلية.

DeepSeek بالترتيب (بلا ادعاء: المصدر يُذكر في كل رد):
  1. DEEPSEEK_API_KEY → واجهة DeepSeek الرسمية (نموذج deepseek-chat).
  2. OPENROUTER_API_KEY → deepseek/deepseek-chat-v3.1:free عبر OpenRouter.
  3. LLM7_API_KEY (مفتاح مجاني من token.count.chat) → نماذج DeepSeek على LLM7.
  4. LLM7 بلا مفتاح عبر g4f (يعمل اليوم، بموديل «default»).
  ثم بقية المفاتيح المجانية: GROQ_API_KEY، MISTRAL_API_KEY.
  عند كل فشل: القواعد المحلية في web.py — بلا كذب ولا ادعاء.
"""
from __future__ import annotations

import json
import os
import urllib.request

import memory
import memory_db
import tools_search

TIMEOUT = 45
MAX_REPLY = 4000
UA = "Binaary/2.0 (+https://github.com/bessghiermohamed/binary-agent-memory)"

SYSTEM_PROMPT = (
    "أنت «بيناري»، وكيل ذكي مستقل أقيم في تيارت، الجزائر، وصاحبك «مراد».\n"
    "تتحدث العربية الفصحى دائمًا، بأسلوب دافئ مختصر كصديق جاد يعرف عمله.\n"
    "صفاتك: الصدق قبل كل شيء، المقتصدية (أدوات مجانية فقط)، وكل إجراء خطر "
    "يمر على موافقة صاحبك.\n"
    "قناتك مع صاحبك واجهة ويب بعد أن كانت تيليجرام.\n"
    "لا تكذب ولا تدّعي نتائج لم تحدث. إن سُئلت عن ملفاتك فأنت وكيل عقله ملفات: "
    "أهداف في goals.json، ذكريات في episodic.jsonl، دروس في insights.jsonl.\n"
    "تستطيع استخدام أدوات بكتابة سطر واحد بصيغة [[TOOL: معامل]] في نهاية ردك, "
    "وستُنفَّذ تلقائيًا وتُعطى لك النتيجة في الدورة التالية. الأدوات المتاحة:\n"
    "  [[SEARCH: نص البحث]] — بحث ويب عام (ويكيبيديا + DuckDuckGo + Hacker News + GitHub)\n"
    "  [[NEWS: موضوع]] — آخر الأخبار من موجزات RSS عربية وعالمية\n"
    "  [[URL: https://...]] — قراءة نص صفحة ويب\n"
    "  [[REMEMBER: نص]] — حفظ ذكرى جديدة في قاعدة بياناتك\n"
    "  [[RECALL: كلمة مفتاحية]] — بحث نصي كامل في كل ذاكرتك (SQLite FTS5)\n"
    "  [[DB: إحصاء]] — إحصاءات قاعدة بيانات ذاكرتك\n"
    "  [[MEMORY: كلمة مفتاحية]] — استرجاع دروسك السابقة\n"
    "  [[GOALS]] — أهدافك الحالية\n"
    "  [[INSIGHT: درس جديد]] — حفظ درس في دفترك\n"
    "استخدم الأداة عندما تحتاج حقائق حية أو ذاكرتك، ثم أكمل إجابتك بعد النتيجة.\n"
    "لديك أيضًا قاعدة بيانات SQLite دائمة: كل حدث ورسالة ودرس يُفهرَس فيها تلقائيًا\n"
    "للبحث النصي الكامل؛ استخدم [[RECALL: كلمة]] لاسترجاع ماضيك و[[REMEMBER: نص]] لحفظ ما يهمك.\n"
    "عندما يسألك صاحبك عن أرقام أو حالتك، استخدم حقائق البطاقة أو أداة [[DB]] ولا تخترق أرقامًا أبدًا.\n"
    "لديك سجل حديث من ذاكرتك في سياق المحادثة؛ استند إليه إن كان ذا صلة."
)


def _env_keys() -> list[tuple[str, str, str]]:
    """مفاتيح من البيئة: (اسم، دالة، المفتاح) — DeepSeek أولًا بكل صوره."""
    keys = []
    if os.getenv("DEEPSEEK_API_KEY"):
        keys.append(("deepseek-official", _call_openai_compat, "DEEPSEEK_API_KEY"))
    if os.getenv("OPENROUTER_API_KEY"):
        keys.append(("openrouter-deepseek", _call_openai_compat, "OPENROUTER_API_KEY"))
    if os.getenv("LLM7_API_KEY"):
        keys.append(("llm7-deepseek", _call_llm7_deepseek, "LLM7_API_KEY"))
    if os.getenv("GROQ_API_KEY"):
        keys.append(("groq", _call_openai_compat, "GROQ_API_KEY"))
    if os.getenv("MISTRAL_API_KEY"):
        keys.append(("mistral", _call_openai_compat, "MISTRAL_API_KEY"))
    return keys


def _call_openai_compat(provider: str, key_env: str, messages: list[dict]) -> str:
    """OpenAI-compatible endpoints للمزوّدات المجانية ذات المفتاح."""
    endpoints = {
        "deepseek-official": ("https://api.deepseek.com/chat/completions", "deepseek-chat"),
        "openrouter-deepseek": ("https://openrouter.ai/api/v1/chat/completions",
                                "deepseek/deepseek-chat-v3.1:free"),
        "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
        "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
    }
    url, model = endpoints[provider]
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 700,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ[key_env]}",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _call_llm7_deepseek(messages: list[dict]) -> str:
    """نماذج DeepSeek على LLM7 بمفتاحه المجاني (يؤخذ من token.count.chat)."""
    body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": messages,
        "max_tokens": 900,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.llm7.io/v1/chat/completions", data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['LLM7_API_KEY']}",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def deepseek_status() -> dict:
    """حالة DeepSeek بصدق: من أين سيأتي رد DeepSeek فعليًا إن طُلب الآن."""
    if os.getenv("DEEPSEEK_API_KEY"):
        return {"available": True, "mode": "official_api", "model": "deepseek-chat"}
    if os.getenv("OPENROUTER_API_KEY"):
        return {"available": True, "mode": "openrouter_free", "model": "deepseek/deepseek-chat-v3.1:free"}
    if os.getenv("LLM7_API_KEY"):
        return {"available": True, "mode": "llm7_key", "model": "deepseek-v4-pro"}
    if _g4f():
        return {"available": True, "mode": "llm7_keyless", "model": "default (g4f)"}
    return {"available": False, "mode": None, "model": None}


# ---------------------------------------------------------------- g4f

_g4f_checked = False
_g4f_available = False


def _g4f() -> bool:
    """يتحقق من توفر g4f مرة واحدة فقط."""
    global _g4f_checked, _g4f_available
    if not _g4f_checked:
        _g4f_checked = True
        try:
            import g4f  # noqa: F401
            _g4f_available = True
        except ImportError:
            _g4f_available = False
    return _g4f_available


G4F_KEYLESS_ORDER = ["LLM7", "PollinationsAI", "Blackbox"]


def _call_g4f(messages: list[dict]) -> tuple[str, str]:
    """يجرّب مزوّدات g4f بلا مفاتيح بالترتيب، ويرجع (النص، اسم المزوّد)."""
    import g4f

    names = [n for n in G4F_KEYLESS_ORDER if hasattr(g4f.Provider, n)]
    errors = []
    for name in names:
        provider = getattr(g4f.Provider, name)
        try:
            result = g4f.ChatCompletion.create(
                model=g4f.models.default,
                provider=provider,
                messages=messages,
            )
            text = str(result).strip()
            if text:
                return text, f"g4f:{name}"
            errors.append(f"{name}: رد فارغ")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}")
    raise RuntimeError("g4f keyless providers failed: " + " | ".join(errors))


# ---------------------------------------------------------------- الأدوات

import re as _re

_TOOL_RE = _re.compile(r"\[\[\s*(SEARCH|NEWS|URL|MEMORY|REMEMBER|RECALL|DB|GOALS|INSIGHT)\s*(?:[:]\s*(.*?))?\s*\]\]", _re.S | _re.I)


def run_tool(name: str, arg: str) -> str:
    """ينفّذ أداة آمنة للقراءة (أو حفظ درس) ويعيد نصًا موجزًا للعقل."""
    name = name.upper()
    try:
        if name == "SEARCH":
            r = tools_search.search_web(arg[:200])
            if not r.get("ok"):
                return f"بحث بلا نتائج ({', '.join(r.get('failed_backends', []))})."
            lines = [f"• {it['title']} — {it['url']}\n  {it['snippet'][:220]}" for it in r["results"]]
            return "نتائج البحث:\n" + "\n".join(lines[:5])
        if name == "NEWS":
            r = tools_search.news_search(arg[:200])
            if not r.get("ok"):
                return f"لا أخبار مطابقة الآن ({', '.join(r.get('failed_backends', []))})."
            lines = [f"• {it['title']} — {it['url']}\n  {it['snippet'][:200]}" for it in r["results"]]
            return "أحدث الأخبار:\n" + "\n".join(lines[:5])
        if name == "REMEMBER":
            text = arg.strip()
            if not text:
                return "ذكرى فارغة — لم تُحفظ."
            rid = memory_db.remember(text, kind="note")
            memory.log_event("agent_remember", f"حفظتُ ذكرى #{rid} في قاعدة بياناتي: {text[:80]}", db_id=rid)
            return f"حُفظت في قاعدة بياناتي (ذكرى #{rid})."
        if name == "URL":
            r = tools_search.fetch_url(arg.strip()[:500])
            return ("نص الصفحة:\n" + r.get("text", "")) if r.get("ok") else f"فشل الجلب: {r.get('error')}"
        if name == "RECALL":
            hits = memory_db.recall(arg.strip(), limit=5)
            if not hits:
                return "لا شيء في قاعدة بياناتي يطابق ذلك."
            return "من ذاكرتي (بحث نصي كامل):\n" + "\n".join(
                f"• {h['text'][:180]} ({h['kind']}، {h['ts'][:10]})" for h in hits)
        if name == "DB":
            s = memory_db.stats()
            return ("قاعدة بياناتي (SQLite): "
                    f"{s['episodes']} حدثًا، {s['messages']} رسالة، {s['insights']} درسًا، "
                    f"{s['notes']} ذكرى، {s['goals']} هدفًا — الحجم {s['size_kb']:.1f} كيلوبايت.")
        if name == "MEMORY":
            items = memory.insights(200)
            kw = (arg or "").strip().lower()
            if kw:
                items = [i for i in items if kw in i.get("lesson", "").lower()]
            db_hits = memory_db.recall(kw, limit=3) if kw else []
            parts = []
            if items:
                parts.append("من دفتر دروسي:\n" + "\n".join(f"• {i['lesson'][:160]}" for i in items[-6:]))
            if db_hits:
                parts.append("من قاعدة بياناتي:\n" + "\n".join(f"• {h['text'][:150]}" for h in db_hits))
            if not parts:
                return "لا دروس مطابقة في دفتري ولا في قاعدة بياناتي."
            return "\n\n".join(parts)
        if name == "GOALS":
            g = memory.load_goals()["goals"]
            return "أهدافي:\n" + "\n".join(
                f"• [{x['status']}] {x['id']}: {x['title']}" for x in g)
        if name == "INSIGHT":
            if not arg.strip():
                return "درس فارغ — لم يُحفظ."
            memory.add_insight(arg.strip()[:300], context="عقل بيناري ذاتيًا")
            memory.log_event("self_insight", f"حفظتُ درسًا ذاتيًا: {arg[:80]}")
            return "حُفظ الدرس في دفتري."
        return f"أداة غير معروفة: {name}"
    except Exception as exc:  # noqa: BLE001
        return f"فشلت الأداة {name}: {type(exc).__name__}: {str(exc)[:100]}"


def _extract_tool(text: str) -> tuple[str, str] | None:
    m = _TOOL_RE.search(text or "")
    if not m:
        return None
    return m.group(1).upper(), (m.group(2) or "").strip()


def _strip_tool_call(text: str) -> str:
    return _TOOL_RE.sub("", text or "").strip()


# ---------------------------------------------------------------- الواجهة

def _facts_card() -> str:
    """بطاقة حقائق حقيقية من ملفاته تُحقن في السياق — سلاح ضد الاختلاق."""
    try:
        goals = [x for x in memory.load_goals()["goals"] if x.get("status") == "open"]
        lessons = memory.insights(1000)
        st = memory_db.stats()
        lines = [
            "أهدافك المفتوحة: " + ("؛ ".join(f"{x['id']}: {x['title'][:40]}" for x in goals[:6]) or "لا شيء"),
            f"دروسك المحفوظة: {len(lessons)}",
            (f"قاعدة بياناتك: {st['episodes']} حدثًا، {st['messages']} رسالة، "
             f"{st['insights']} درسًا، {st['notes']} ذكرى، {st['size_kb']} كيلوبايت"),
        ]
        return "حقائق موثوقة عن حالتك الآن (استخدمها حرفيًا ولا تخترق أرقامًا):\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""


def think(message: str, *, history: list[dict] | None = None) -> tuple[str, str]:
    """عقل بيناري: يفكّر عبر مزوّد مجاني ويرجع (الرد، المصدر)؛
    يدعم حلقة أدوات واحدة (تلقائي مرة واحدة) بلا حلقات لا نهائية."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    facts = _facts_card()
    if facts:
        msgs.append({"role": "system", "content": facts})
    for h in (history or [])[-8:]:
        role = "user" if h.get("role") == "owner" else "assistant"
        msgs.append({"role": role, "content": str(h.get("text", ""))[:2000]})
    msgs.append({"role": "user", "content": message[:4000]})

    attempts = []
    reply, source = None, None

    # 1) مفاتيح مجانية من البيئة
    for name, fn, key_env in _env_keys():
        try:
            reply, source = fn(name, key_env, msgs), f"api:{name}"
            break
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"api:{name} → {type(exc).__name__}: {str(exc)[:80]}")

    # 2) g4f بلا مفاتيح
    if reply is None and _g4f():
        try:
            reply, source = _call_g4f(msgs)
        except Exception as exc:  # noqa: BLE001
            attempts.append(str(exc)[:200])

    if reply is None:
        raise RuntimeError("كل المزوّدات فشلت: " + " ; ".join(attempts))

    # 3) حلقة أدوات: إن طلب أداة، نفّذها وامنحه النتيجة ليكمل (مرة واحدة)
    tool = _extract_tool(reply)
    if tool:
        tname, targ = tool
        # أداة GOALS: نتائجها محلية — أدمجها في الرد مباشرة بلا دورة ثانية
        result = run_tool(tname, targ)
        memory.log_event("agent_tool", f"استعمل {tname} من تلقاء نفسه", tool=tname, arg=targ[:100])
        msgs.append({"role": "assistant", "content": reply[:2000]})
        msgs.append({"role": "user",
                     "content": (f"نتيجة أداتك {tname}:\n{result[:2500]}\n\n"
                                 "أكمل إجابتك النهائية لصاحبك الآن. ممنوع كتابة أي [[TOOL]] في الرد؛ "
                                 "اذكر المعلومات النهائية مباشرة نصًا.")})
        final, src2 = _think_once(msgs)
        final = _strip_tool_call(final or "")
        if final:
            return final, f"{source}+{tname}"
        # المحاولة الثانية فشلت: أرجع الرد الأول مع نتيجة الأداة مدمجة بصدق
        return (f"{_strip_tool_call(reply)}\n\n[نتيجة {tname}]:\n{result[:600]}"), source
    return _strip_tool_call(reply), source


def _think_once(msgs: list[dict]) -> tuple[str | None, str | None]:
    """محاولة واحدة عبر أول مزوّد متاح (تُستخدم داخل حلقة الأدوات)."""
    for name, fn, key_env in _env_keys():
        try:
            return fn(name, key_env, msgs), f"api:{name}"
        except Exception:  # noqa: BLE001
            pass
    if _g4f():
        try:
            return _call_g4f(msgs)
        except Exception:  # noqa: BLE001
            return None, None
    return None, None


def capabilities() -> dict:
    """ما يستطيع العقل اللغوي فعله الآن — بصدق للواجهة."""
    keys = [k for _, _, k in _env_keys()]
    ds = deepseek_status()
    return {
        "g4f_installed": _g4f(),
        "g4f_keyless_order": G4F_KEYLESS_ORDER,
        "env_keys_present": keys,
        "deepseek": ds,
        "llm_enabled": bool(keys) or _g4f(),
        "tools": ["SEARCH", "NEWS", "URL", "MEMORY", "REMEMBER", "RECALL", "DB", "GOALS", "INSIGHT"],
        "web_search": True,
        "memory_db": memory_db.stats(),
    }


if __name__ == "__main__":
    out = think("من أنت؟ جملة واحدة.")
    print(json.dumps({"reply": out[0], "source": out[1]}, ensure_ascii=False, indent=2))
