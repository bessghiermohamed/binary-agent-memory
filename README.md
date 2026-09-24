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
