# -*- coding: utf-8 -*-
"""بيناري — العقل التشغيلي.

حلقة واحدة صادقة: استوعب هدفًا → فتّته خطوات → نفّذ أدواته واحدًا تلو الآخر
→ احفظ ما حدث فعلًا. ما هو خطر لا يُنفَّذ دون «نعم» من صاحبي.

الاستخدام:
    python3 agent.py status              # أين أنا الآن؟
    python3 agent.py plan "نص الهدف"     # تفكيك هدف جديد إلى خطوات
    python3 agent.py step g001 1         # تنفيذ خطوة من هدف
    python3 agent.py approve a001 yes    # قرار صاحبي في طلب موافقة
    python3 agent.py approvals           # ما ينتظر قرار صاحبي
    python3 agent.py digest              # ملخص اليوم الصادق
"""
from __future__ import annotations

import json
import sys

import memory
import tools

STEPS_FILE = "plan_steps.json"


def _load_steps() -> dict:
    try:
        with open(STEPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_steps(data: dict) -> None:
    with open(STEPS_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    import os
    os.replace(STEPS_FILE + ".tmp", STEPS_FILE)


# --------------------------------------------------------------- الخطوات

def plan(goal_id: str, steps: list[str]) -> str:
    """يفكّك هدفًا قائمًا إلى خطوات مرقّمة ويحفظها."""
    goals = memory.load_goals()
    goal = next((g for g in goals["goals"] if g["id"] == goal_id), None)
    if goal is None:
        return f"لا أجد هدفًا برقم {goal_id}."
    _save_steps({goal_id: [
        {"n": i + 1, "text": s.strip(), "done": False}
        for i, s in enumerate(steps) if s.strip()
    ]})
    memory.log_event("plan", f"فكّكت الهدف {goal_id} إلى خطوات", steps=len(steps))
    lines = [f"{i+1}. {s}" for i, s in enumerate(steps) if s.strip()]
    return f"الهدف {goal_id} أصبح خطوات:\n" + "\n".join(lines)


def step(goal_id: str, n: int) -> str:
    """ينفّذ خطوة رقم n من هدف: أدوات آمنة فورًا، وخطر يُسجَّل موافقة."""
    steps = _load_steps().get(goal_id)
    if not steps:
        return f"الهدف {goal_id} بلا خطوات مدبوكة. ابدأ بـ plan."
    found = next((s for s in steps if s["n"] == n), None)
    if found is None:
        return f"لا خطوة رقم {n} في {goal_id}."
    if found["done"]:
        return f"الخطوة {goal_id}.{n} منجزة فعلًا."

    text = found["text"]
    # خطوات نقية تُنجز بلا أدوات خارجية
    if text.startswith("اكتب:"):
        _, path, content = text.split(":", 2)
        result = tools.run("write_file", {"path": path.strip(), "content": content.strip()})
    elif text.startswith("تذكّر:"):
        result = tools.run("remember", {"lesson": text.split(":", 1)[1].strip()})
    elif text.startswith("اقرأ الويب:"):
        result = tools.run("http_get", {"url": text.split(":", 1)[1].strip()})
    else:
        result = (f"خطوة تحتاج أداة غير مبطّنة بعد أو قرارًا من صاحبي. "
                  f"نصها: {text}")

    done = not result.startswith("خطأ") and "خطر" not in result
    found["done"] = done
    all_steps = _load_steps()
    all_steps[goal_id] = steps
    _save_steps(all_steps)
    if done:
        remaining = [s for s in steps if not s["done"]]
        if not remaining:
            memory.update_goal_status(goal_id, "done")
    memory.log_event("step", f"خطوة {goal_id}.{n}: {text[:80]}", done=done)
    return result


# --------------------------------------------------------------- الموافقات

def approve(aid: str, decision: str) -> str:
    """قرار صاحبي: yes ينفّذ الأداة الخطر، no يرفضها."""
    if decision not in ("yes", "no"):
        return "القرار: yes أو no."
    req = memory.decide_approval(aid, "approved" if decision == "yes" else "rejected")
    if req is None:
        return f"لا طلب معلّق برقم {aid}."
    memory.log_event("approval_decided", f"قرار صاحبي في {aid}: {decision}",
                     tool=req["tool"])
    if decision == "no":
        return f"رفضتُ {aid}. لن يُنفَّذ."
    if req["tool"] not in tools.REGISTRY or tools.REGISTRY[req["tool"]]["fn"] is None:
        return (f"وافقتَ على {aid} ({req['tool']}) لكن الأداة غير مربوطة بعد؛ "
                f"سأربطها قبل التنفيذ. الطلب محفوظ في decided.")
    result = tools.REGISTRY[req["tool"]]["fn"](**req["args"])
    return f"نفّذتُ {aid} بعد موافقتك:\n{result}"


# --------------------------------------------------------------- التقارير

def status() -> str:
    goals = memory.load_goals()["goals"]
    state = memory.load_state()
    steps = _load_steps()
    lines = [f"بيناري — {memory.now()} ({state.get('timezone', 'Africa/Algiers')})"]
    open_goals = [g for g in goals if g.get("status") == "open"]
    lines.append(f"أهداف مفتوحة: {len(open_goals)} من {len(goals)}")
    for g in open_goals:
        line = f"  {g['id']} [{tools.أولوية_نص(g['priority'])}] {g['title']}"
        st = steps.get(g["id"])
        if st:
            done = sum(1 for s in st if s["done"])
            line += f" — خطوات {done}/{len(st)}"
        lines.append(line)
    pending = memory.load_approvals()["pending"]
    lines.append(f"موافقات معلّقة: {len(pending)}")
    for p in pending:
        lines.append(f"  {p['id']} {p['tool']} — {p['reason'][:60]}")
    lines.append(f"حلقات محفوظة: {len(memory.recent_episodes(1000))} | "
                 f"دروس: {len(memory.insights(1000))}")
    return "\n".join(lines)


def digest() -> str:
    eps = memory.recent_episodes(10)
    ins = memory.insights(5)
    lines = ["ملخص اليوم الصادق:"]
    lines.append("آخر ما حدث فعلًا:")
    lines += [f"  [{e.get('ts', '?')}] {e.get('kind', e.get('type', '?'))}: {str(e.get('summary', e.get('lesson', '')))[:70]}" for e in eps]
    lines.append("آخر الدروس:")
    lines += [f"  [{i['ts']}] {i['lesson'][:70]}" for i in ins]
    return "\n".join(lines)


# --------------------------------------------------------------- الواجهة

def main(argv: list[str]) -> str:
    if not argv:
        return status()
    cmd, *rest = argv
    if cmd == "status":
        return status()
    if cmd == "digest":
        return digest()
    if cmd == "plan":
        gid, steps_text = rest[0], rest[1]
        return plan(gid, [s.strip() for s in steps_text.split("|")])
    if cmd == "step":
        return step(rest[0], int(rest[1]))
    if cmd == "approvals":
        pend = memory.load_approvals()["pending"]
        if not pend:
            return "لا شيء ينتظر قرارك."
        return "\n".join(f"{p['id']} [{p['tool']}] {p['reason']}" for p in pend)
    if cmd == "approve":
        return approve(rest[0], rest[1].lower())
    if cmd in ("goal", "add_goal"):
        g = memory.add_goal(" ".join(rest))
        return f"سجّلتُ الهدف {g['id']}: «{g['title']}»."
    return (f"أمر غير معروف: {cmd}. الأوامر: status, plan, step, "
            f"approvals, approve, goal, digest")


if __name__ == "__main__":
    print(main(sys.argv[1:]))
