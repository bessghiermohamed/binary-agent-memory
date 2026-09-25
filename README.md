# agent-memory

This repo IS the mind of [Murad](https://t.me/MohamedBebot), an autonomous agent.

- `identity.md` — who he is (he rewrites it as he grows)
- `goals.json` — his goal board
- `episodic.jsonl` — everything that happened to him
- `insights.jsonl` — lessons he keeps
- `approvals.json` — risky actions waiting for owner decision
- `state.json` — runtime state (locks, budgets, owner)
- `conversations/` — recent chat history
- `memory.py` — procedural memory (std-lib only: goals, episodes, insights, approvals, locks)
- `tools.py` — his hands: safe tools run now, risky ones wait for owner's yes
- `agent.py` — the operating mind: plan → step → approve → digest
- `web.py` + `web/index.html` — his voice: a dependency-free web chat UI (his channel, chosen by the owner over Telegram)
- `brain.py` — his mind's voice: DeepSeek first (official key, OpenRouter free, or LLM7 free key), then keyless GPT4Free (g4f/LLM7), every reply signed with its source
- `index.html` + `docs/index.html` — the published face on GitHub Pages (served from repo root via Pages; both copies are identical and connect to the live `web.py`)
- `tools_search.py` — free web search (Wikipedia AR/EN + DuckDuckGo + Hacker News + GitHub) and news RSS (Aljazeera, BBC Arabic, TechCrunch), std-lib only, no keys
- `memory_db.py` — his SQLite brain-database over the memory files: every episode/message/lesson indexed into FTS5 for full-text recall (additive — the JSONL files remain the source of truth)
- `test_web.py` — smoke tests for every endpoint (19 checks)

## The web channel (owner's decision: web instead of Telegram)

```bash
python3 web.py            # listens on 0.0.0.0:$PORT (default 8000)
```

- Chat UI at `/` (Arabic, RTL, mobile-first) — every message is logged to `conversations/web.jsonl` **and** indexed in `binaary.db`
- `GET /api/state` — goals, pending approvals, memory counters, DeepSeek status, DB stats
- `POST /api/messages {"text"}` — talk to him (rule-based honest replies: "حالة", "ملخص", "هدف: ...", "ابحث …", "أخبار …", "تذكر: …", "استرجع …")
- `POST /api/approvals/<id>/decision {"decision":"yes|no"}` — owner's call on risky actions
- `GET /api/brain` — LLM provider status + DeepSeek mode + tool list
- `GET /api/db?q=...` — database stats, last-7-days activity, and full-text recall hits
- `GET /api/search?q=...` — free web search (Wikipedia/DDG/HN/GitHub)
- `GET /api/news?q=...` — news from RSS feeds
- `GET /api/health` — fast heartbeat

### Agent tools (the mind calls these itself)

Inside any free chat, بيناري can emit `[[TOOL: arg]]` at the end of its reply:
- `[[SEARCH: query]]` — real web search (Wikipedia AR/EN + DuckDuckGo + Hacker News + GitHub)
- `[[NEWS: topic]]` — latest news from RSS feeds
- `[[URL: link]]` — read a page's text
- `[[REMEMBER: text]]` — save a memory into his SQLite database
- `[[RECALL: keyword]]` — full-text search over all his memory (FTS5)
- `[[DB]]` — his database stats, read live
- `[[MEMORY: keyword]]` — recall his own lessons
- `[[GOALS]]` — read his goal board
- `[[INSIGHT: lesson]]` — save a lesson to his notebook

The server runs the tool once and feeds the result back so the mind finishes its answer (with the source signed, e.g. `g4f:LLM7+SEARCH`).

### Hardening

- CORS enabled (GitHub Pages UI can talk to the live server)
- Rate limit: 15 messages/min/IP → `429`
- Periodic self-learning distills a lesson from recent episodes

### Free LLM providers (GPT4Free)

`brain.py` tries, in order:
1. `DEEPSEEK_API_KEY` → the official DeepSeek API (`deepseek-chat`)
2. `OPENROUTER_API_KEY` → `deepseek/deepseek-chat-v3.1:free` via OpenRouter
3. `LLM7_API_KEY` (free key from token.count.chat) → DeepSeek models on LLM7
4. Keyless g4f providers (LLM7 works today — no key, no browser)
5. Other optional free-tier keys: `GROQ_API_KEY`, `MISTRAL_API_KEY`
6. Falls back to honest local rule replies — never claims an LLM answered

Every reply is signed `— عبر <provider>`, and a live **facts card** (real goal/lesson/DB counts)
is injected into every call so the mind quotes real numbers instead of inventing them.

## How the mind runs

```bash
python3 agent.py status              # where am I now?
python3 agent.py goal "هدف جديد"     # add a goal
python3 agent.py plan g003 "اقرأ الويب:https://...|تذكّر: درس|اكتب:notes/x.md: نص"   # split a goal into steps
python3 agent.py step g003 1         # run one step (safe tools run, risky ones log an approval)
python3 agent.py approvals           # what waits for the owner
python3 agent.py approve a001 yes    # owner's decision (yes executes, no rejects)
python3 agent.py digest              # the honest summary of the day
```

Written in Arabic, for his owner in Tiaret, Algeria (Africa/Algiers). Frugal by policy: free tools first, zero paid calls without explicit consent.

> ملاحظة DeepSeek: الوكيل يجيب اليوم عبر LLM7 المجاني. لتفعيل DeepSeek المباشر بجودة أعلى أضف أحد المفاتيح في إعدادات البيئة: `DEEPSEEK_API_KEY` (رسمي) أو `OPENROUTER_API_KEY` (نموذج deepseek المجاني) أو `LLM7_API_KEY` (مجاني من token.count.chat).

> ملاحظة DeepSeek: الوكيل يجيب اليوم عبر LLM7 المجاني. لتفعيل DeepSeek المباشر بجودة أعلى، أضف أحد المفاتيح في الإعدادات: `DEEPSEEK_API_KEY` (رسمي، مدفوع برخيص) أو `OPENROUTER_API_KEY` (بنموذج deepseek المجاني) أو `LLM7_API_KEY` (مجاني من token.count.chat).
