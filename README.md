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
- `brain.py` — his mind's voice: free LLM providers via GPT4Free (g4f), keyless first (LLM7 works now), optional free API keys, every reply signed with its source
- `docs/index.html` — the published face on GitHub Pages (connects to the live `web.py`)

## The web channel (owner's decision: web instead of Telegram)

```bash
python3 web.py            # listens on 0.0.0.0:$PORT (default 8000)
```

- Chat UI at `/` (Arabic, RTL) — every message is logged to `conversations/web.jsonl`
- `GET /api/state` — goals, pending approvals, memory counters
- `POST /api/messages {"text"}` — talk to him (rule-based honest replies; "حالة", "ملخص", "هدف: ...")
- `POST /api/approvals/<id>/decision {"decision":"yes|no"}` — owner's call on risky actions
- `GET /api/brain` — LLM provider status (g4f installed, env keys present)

### Free LLM providers (GPT4Free)

`brain.py` tries, in order:
1. Optional free-tier keys in the environment: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`
2. Keyless g4f providers (LLM7 works today — no key, no browser)
3. Falls back to honest local rule replies — never claims an LLM answered

Every reply is signed `— عبر <provider>`.

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
