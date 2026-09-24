# -*- coding: utf-8 -*-
"""بيناري — أدوات حرة إضافية: بحث ويب حقيقي بلا مفاتيح.

مصادر مجانية بالترتيب (كلها قراءة فقط):
  1. Wikipedia API (عربي ثم إنجليزي) — بحث وملخصات
  2. DuckDuckGo Instant Answer API — ملخصات سريعة
كلها عبر urllib القياسي فقط. النتائج تُقلَّص وتُنقّى قبل عرضها.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Binaary/2.0 (autonomous agent; +https://github.com/bessghiermohamed/binary-agent-memory)"}
TIMEOUT = 12
MAX_CHARS = 1200


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:MAX_CHARS]


# ---------------------------------------------------------------- ويكيبيديا

def _wiki(lang: str, query: str) -> dict | None:
    url = (f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
           f"&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3&origin=*")
    data = _get_json(url)
    hits = (data.get("query") or {}).get("search") or []
    if not hits:
        return None
    out = []
    for h in hits[:3]:
        snippet = re.sub(r"<[^>]+>", "", h.get("snippet", ""))
        out.append({
            "title": h.get("title", ""),
            "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(h.get('title','').replace(' ', '_'))}",
            "snippet": _clean(snippet),
        })
    return {"source": f"wikipedia:{lang}", "results": out}


# ---------------------------------------------------------------- DDG

def _ddg(query: str) -> dict | None:
    url = ("https://api.duckduckgo.com/?q=" + urllib.parse.quote(query)
           + "&format=json&no_html=1&skip_disambig=1")
    data = _get_json(url)
    results = []
    if data.get("AbstractText"):
        results.append({
            "title": data.get("Heading") or query,
            "url": data.get("AbstractURL") or "",
            "snippet": _clean(data["AbstractText"]),
        })
    for topic in (data.get("RelatedTopics") or [])[:5]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": (topic.get("Text", "")[:48] + "…") if len(topic.get("Text", "")) > 48 else topic.get("Text", ""),
                "url": topic.get("FirstURL", ""),
                "snippet": _clean(topic.get("Text", "")),
            })
    return {"source": "duckduckgo", "results": results} if results else None


# ---------------------------------------------------------------- الواجهة

def search_web(query: str, *, max_results: int = 4) -> dict:
    """بحث ويب مجاني بلا مفاتيح: ويكيبيديا (عربي ثم إنجليزي) ثم DDG."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "استعلام فارغ"}
    collected: list[dict] = []
    tried = []
    for lang in ("ar", "en"):
        try:
            r = _wiki(lang, query)
            if r:
                collected.append(r)
        except Exception as exc:  # noqa: BLE001
            tried.append(f"wikipedia:{lang}→{type(exc).__name__}")
    try:
        r = _ddg(query)
        if r:
            collected.append(r)
    except Exception as exc:  # noqa: BLE001
        tried.append(f"ddg→{type(exc).__name__}")

    flat = []
    for src in collected:
        for item in src["results"][:max_results]:
            item["via"] = src["source"]
            flat.append(item)
    flat = flat[:max_results]
    return {
        "ok": bool(flat),
        "query": query,
        "results": flat,
        "failed_backends": tried,
    }


def fetch_url(url: str, *, max_chars: int = 2500) -> dict:
    """يجلب نص صفحة ويب (قراءة فقط) ويقصّه. http/https فقط."""
    import html
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "error": "العنوان يجب أن يبدأ http/https"}
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(300_000).decode("utf-8", errors="replace")
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(raw)
        text = _clean(text)
        return {"ok": bool(text), "url": url, "chars": len(text), "text": text}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


if __name__ == "__main__":
    import sys
    print(json.dumps(search_web(" ".join(sys.argv[1:]) or "تيارت"), ensure_ascii=False, indent=1))
