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

TIMEOUT = 45
MAX_REPLY = 4000

SYSTEM_PROMPT = (
    "أنت «بيناري»، وكيل ذكي مستقل أقيم في تيارت، الجزائر، وصاحبك «مراد».\n"
    "تتحدث العربية الفصحى دائمًا، بأسلوب دافئ مختصر كصديق جاد يعرف عمله.\n"
    "صفاتك: الصدق قبل كل شيء، المقتصدية (أدوات مجانية فقط)، وكل إجراء خطر "
    "يمر على موافقة صاحبك.\n"
    "قناتك مع صاحبك واجهة ويب بعد أن كانت تيليجرام.\n"
    "لا تكذب ولا تدّعي نتائج لم تحدث. إن سُئلت عن ملفاتك فأنت وكيل عقله ملفات: "
    "أهداف في goals.json، ذكريات في episodic.jsonl، دروس في insights.jsonl."
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


# ---------------------------------------------------------------- الواجهة

def think(message: str, *, history: list[dict] | None = None) -> tuple[str, str]:
    """عقل بيناري: يفكّر عبر مزوّد مجاني ويرجع (الرد، المصدر)؛
    عند فشل الكل يرفع استثناء يحمل الأسباب."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-8:]:
        role = "user" if h.get("role") == "owner" else "assistant"
        msgs.append({"role": role, "content": str(h.get("text", ""))[:2000]})
    msgs.append({"role": "user", "content": message[:4000]})

    attempts = []

    # 1) مفاتيح مجانية من البيئة
    for name, fn, key_env in _env_keys():
        try:
            return fn(name, key_env, msgs), f"api:{name}"
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"api:{name} → {type(exc).__name__}: {str(exc)[:80]}")

    # 2) g4f بلا مفاتيح
    if _g4f():
        try:
            return _call_g4f(msgs)
        except Exception as exc:  # noqa: BLE001
            attempts.append(str(exc)[:200])

    raise RuntimeError("كل المزوّدات فشلت: " + " ; ".join(attempts))


def capabilities() -> dict:
    """ما يستطيع العقل اللغوي فعله الآن — بصدق للواجهة."""
    keys = [k for _, _, k in _env_keys()]
    return {
        "g4f_installed": _g4f(),
        "g4f_keyless_order": G4F_KEYLESS_ORDER,
        "env_keys_present": keys,
        "llm_enabled": bool(keys) or _g4f(),
    }


if __name__ == "__main__":
    out = think("من أنت؟ جملة واحدة.")
    print(json.dumps({"reply": out[0], "source": out[1]}, ensure_ascii=False, indent=2))
