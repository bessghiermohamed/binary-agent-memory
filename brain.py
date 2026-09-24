# -*- coding: utf-8 -*-
"""بيناري — العقل اللغوي.

قناة صاحبي صارت الويب، وقدرته اللغوية صارت حقيقية عبر مزوّدات مجانية
(GPT4Free / g4f) — بلا ادعاء: كل رد قادم من مزوّد فعلي يُذكر اسمه،
وكل فشل يُعلن صريحًا مع رجوع آمن للردود القواعدية المحلية.

المزوّدات بالترتيب:
  1. أي مفتاح في البيئة (مجاني التسجيل): GROQ_API_KEY → Groq،
     OPENROUTER_API_KEY → OpenRouter، MISTRAL_API_KEY → Mistral.
  2. مزوّدات g4f بلا مفاتيح (LLM7 أولًا — مجرّب ويعمل).
  3. عند كل فشل: القواعد المحلية في web.py (بلا كذب ولا تجيؤف).
"""
from __future__ import annotations

import json
import os
import urllib.request

import memory
import tools_search

TIMEOUT = 45
MAX_REPLY = 4000

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
    "  [[SEARCH: نص البحث]] — بحث ويب مجاني (ويكيبيديا + DuckDuckGo)\n"
    "  [[URL: https://...]] — قراءة نص صفحة ويب\n"
    "  [[MEMORY: كلمة مفتاحية]] — استرجاع دروسك السابقة\n"
    "  [[GOALS]] — أهدافك الحالية\n"
    "  [[INSIGHT: درس جديد]] — حفظ درس في دفترك\n"
    "استخدم الأداة عندما تحتاج حقائق حية أو ذاكرتك، ثم أكمل إجابتك بعد النتيجة.\n"
    "لديك سجل حديث من ذاكرتك في سياق المحادثة؛ استند إليه إن كان ذا صلة."
)


def _env_keys() -> list[tuple[str, str, str]]:
    """مفاتيح مجانية اختيارية من البيئة: (اسم، دالة، المفتاح)."""
    keys = []
    if os.getenv("GROQ_API_KEY"):
        keys.append(("groq", _call_openai_compat, "GROQ_API_KEY"))
    if os.getenv("OPENROUTER_API_KEY"):
        keys.append(("openrouter", _call_openai_compat, "OPENROUTER_API_KEY"))
    if os.getenv("MISTRAL_API_KEY"):
        keys.append(("mistral", _call_openai_compat, "MISTRAL_API_KEY"))
    return keys


def _call_openai_compat(provider: str, key_env: str, messages: list[dict]) -> str:
    """OpenAI-compatible endpoints للمزوّدات المجانية ذات المفتاح."""
    endpoints = {
        "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
        "openrouter": ("https://openrouter.ai/api/v1/chat/completions",
                        "meta-llama/llama-3.3-70b-instruct:free"),
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


G4F_KEYLESS_ORDER = ["LLM7", "Lambda", "OIVSCode", "PollinationsAI", "Blackbox"]


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

_TOOL_RE = _re.compile(r"\[\[\s*(SEARCH|URL|MEMORY|GOALS|INSIGHT)\s*(?:[:]\s*(.*?))?\s*\]\]", _re.S | _re.I)


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
        if name == "URL":
            r = tools_search.fetch_url(arg.strip()[:500])
            return ("نص الصفحة:\n" + r.get("text", "")) if r.get("ok") else f"فشل الجلب: {r.get('error')}"
        if name == "MEMORY":
            items = memory.insights(200)
            kw = (arg or "").strip().lower()
            if kw:
                items = [i for i in items if kw in i.get("lesson", "").lower()]
            if not items:
                return "لا دروس مطابقة في دفتري."
            return "من دفتر دروسي:\n" + "\n".join(f"• {i['lesson'][:160]}" for i in items[-6:])
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

def think(message: str, *, history: list[dict] | None = None) -> tuple[str, str]:
    """عقل بيناري: يفكّر عبر مزوّد مجاني ويرجع (الرد، المصدر)؛
    يدعم حلقة أدوات واحدة (تلقائي مرة واحدة) بلا حلقات لا نهائية."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
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
    return {
        "g4f_installed": _g4f(),
        "g4f_keyless_order": G4F_KEYLESS_ORDER,
        "env_keys_present": keys,
        "llm_enabled": bool(keys) or _g4f(),
        "tools": ["SEARCH", "URL", "MEMORY", "GOALS", "INSIGHT"],
        "web_search": True,
    }


if __name__ == "__main__":
    out = think("من أنت؟ جملة واحدة.")
    print(json.dumps({"reply": out[0], "source": out[1]}, ensure_ascii=False, indent=2))
