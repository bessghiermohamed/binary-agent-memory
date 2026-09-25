# -*- coding: utf-8 -*-
"""بيناري — أدوات حرة إضافية: بحث ويب حقيقي بلا مفاتيح.

مصادر مجانية بالترتيب (كلها قراءة فقط):
  1. Wikipedia API (عربي ثم إنجليزي) — بحث وملخصات
  2. DuckDuckGo Instant Answer API — ملخصات سريعة
  3. Hacker News (Algolia API) — نقاشات ومقالات تقنية
  4. GitHub Search API — مستودعات برمجية مطابقة
  5. موجزات RSS — عاجل الجزيرة، BBC عربي، العربي الجديد، TechCrunch
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

RSS_FEEDS = [
    ("الجزيرة عاجل", "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"),
    ("BBC عربي", "https://feeds.bbci.co.uk/arabic/rss.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Reuters عربي", "https://news.google.com/rss/search?q=when:1d+allinurl:reuters.com&hl=ar&gl=MA&ceid=MA:ar"),
]


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _get_text(url: str, max_bytes: int = 400_000) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(max_bytes).decode("utf-8", errors="replace")


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


# ---------------------------------------------------------------- Hacker News

def _hn(query: str) -> dict | None:
    import urllib.parse
    url = ("https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(query)
           + "&tags=story&hitsPerPage=3")
    data = _get_json(url)
    hits = data.get("hits") or []
    out = []
    for h in hits:
        if not h.get("title"):
            continue
        url_h = h.get("url") or ("https://news.ycombinator.com/item?id=" + str(h.get("objectID", "")))
        pts = h.get("points") or 0
        out.append({
            "title": h["title"][:90],
            "url": url_h,
            "snippet": _clean(f"[{pts} نقطة على Hacker News] {h.get('story_text') or h.get('title', '')}"),
        })
    return {"source": "hackernews", "results": out} if out else None


# ---------------------------------------------------------------- GitHub

def _github(query: str) -> dict | None:
    import urllib.parse
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(query)
           + "&sort=stars&per_page=3")
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    out = []
    for repo in (data.get("items") or [])[:3]:
        out.append({
            "title": f"{repo.get('full_name', '')} ★{repo.get('stargazers_count', 0)}",
            "url": repo.get("html_url", ""),
            "snippet": _clean(repo.get("description") or "مستودع برمجي"),
        })
    return {"source": "github", "results": out} if out else None


# ---------------------------------------------------------------- RSS

def _rss(feeds=None) -> dict | None:
    """آخر عناوين موجزات RSS (تُستخدم للخبر العام والبحث بالموضوع)."""
    import xml.etree.ElementTree as ET
    results = []
    for name, feed in (feeds or RSS_FEEDS)[:3]:
        try:
            root = ET.fromstring(_get_text(feed, 200_000))
            for item in list(root.iter("item"))[:4]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if title and link:
                    results.append({
                        "title": f"[{name}] {title[:100]}",
                        "url": link,
                        "snippet": _clean(item.findtext("description") or title),
                    })
        except Exception:  # noqa: BLE001
            continue
    return {"source": "rss", "results": results} if results else None


def _rss_search(query: str) -> dict | None:
    """يبحث عن الموضوع في عناوين آخر 10 عناصر من كل موجز."""
    import xml.etree.ElementTree as ET
    q = query.lower()
    results = []
    for name, feed in RSS_FEEDS:
        try:
            root = ET.fromstring(_get_text(feed, 200_000))
            for item in list(root.iter("item"))[:10]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if q in title.lower() or q in desc.lower():
                    results.append({
                        "title": f"[{name}] {title[:100]}",
                        "url": link,
                        "snippet": _clean(desc or title),
                    })
                if len(results) >= 5:
                    return {"source": "rss", "results": results}
        except Exception:  # noqa: BLE001
            continue
    return {"source": "rss", "results": results} if results else None


def news_search(query: str) -> dict:
    """أخبار: RSS عالمي + مطابقة موضوعية؛ عند فراغ الاستعلام تعيد أحدث العناوين."""
    query = (query or "").strip()
    tried = []
    if not query:
        try:
            r = _rss()
            if r:
                r.update({"ok": True, "query": "", "failed_backends": []})
                return r
        except Exception as exc:  # noqa: BLE001
            tried.append(f"rss→{type(exc).__name__}")
        return {"ok": False, "query": "", "results": [], "failed_backends": tried}
    collected = []
    try:
        r = _rss_search(query)
        if r and r["results"]:
            collected.append(r)
    except Exception as exc:  # noqa: BLE001
        tried.append(f"rss→{type(exc).__name__}")
    try:
        r = _ddg(query)
        if r:
            collected.append(r)
    except Exception as exc:  # noqa: BLE001
        tried.append(f"ddg→{type(exc).__name__}")
    flat = []
    for src in collected:
        for item in src["results"][:4]:
            item["via"] = src["source"]
            flat.append(item)
    flat = flat[:6]
    return {"ok": bool(flat), "query": query, "results": flat, "failed_backends": tried}


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
    try:
        r = _hn(query)
        if r:
            collected.append(r)
    except Exception as exc:  # noqa: BLE001
        tried.append(f"hackernews→{type(exc).__name__}")
    try:
        r = _github(query)
        if r:
            collected.append(r)
    except Exception as exc:  # noqa: BLE001
        tried.append(f"github→{type(exc).__name__}")

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
    args = sys.argv[1:]
    if args and args[0] == "news":
        print(json.dumps(news_search(" ".join(args[1:])), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(search_web(" ".join(args) or "تيارت"), ensure_ascii=False, indent=1))
