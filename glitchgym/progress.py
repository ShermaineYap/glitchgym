"""Attempt log, mastery scores and adaptive drill selection."""

from __future__ import annotations

import random
import time
from collections import defaultdict

from .catalog import CATEGORIES, CATEGORY_IDS

RECENT = 5  # mastery = mean score of the last N drills in a category


def new_state() -> dict:
    return {"attempts": [], "encounters": []}


def log_attempt(state: dict, *, category: str, snippet_id: str | None, score: int, solved: bool,
                hints_used: int, nudges_used: int, checks: int, seconds: float, source: str,
                demo: bool = False) -> None:
    state["attempts"].append({
        "ts": time.time(), "category": category, "snippet_id": snippet_id, "score": score,
        "solved": solved, "hints_used": hints_used, "nudges_used": nudges_used,
        "checks": checks, "seconds": round(seconds, 1), "source": source, "demo": demo,
    })


def log_encounter(state: dict, category: str, error_type: str, demo: bool = False) -> None:
    """A bug the student hit in their OWN code (from Diagnose)."""
    state["encounters"].append({"ts": time.time(), "category": category,
                                "error_type": error_type, "demo": demo})


def mastery(state: dict) -> dict[str, float | None]:
    by_cat: dict[str, list[int]] = defaultdict(list)
    for a in state["attempts"]:
        by_cat[a["category"]].append(a["score"])
    return {c: (sum(v[-RECENT:]) / len(v[-RECENT:]) if (v := by_cat.get(c)) else None) for c in CATEGORY_IDS}


def encounters(state: dict) -> dict[str, int]:
    out = {c: 0 for c in CATEGORY_IDS}
    for e in state["encounters"]:
        out[e["category"]] = out.get(e["category"], 0) + 1
    return out


def priorities(state: dict) -> dict[str, float]:
    """Higher = should practise sooner. Unseen categories and real-world bugs rank high."""
    m, enc = mastery(state), encounters(state)
    pr = {}
    for c in CATEGORY_IDS:
        base = 70.0 if m[c] is None else 100.0 - m[c]
        pr[c] = base + 15.0 * min(enc[c], 4)
    return pr


def next_category(state: dict, exclude: str | None = None) -> tuple[str, str]:
    """Return (category, reason) for the next drill."""
    pr = priorities(state)
    if exclude and len(pr) > 1:
        pr.pop(exclude, None)
    top = max(pr.values())
    choices = [c for c, v in pr.items() if abs(v - top) < 1e-9]
    cat = random.choice(choices)
    m, enc = mastery(state), encounters(state)
    name = CATEGORIES[cat]["name"]
    if enc[cat] and m[cat] is not None:
        reason = f"You've hit {name} bugs {enc[cat]}x in your own code and your mastery is {m[cat]:.0f}/100."
    elif enc[cat]:
        reason = f"You've hit {name} bugs {enc[cat]}x in your own code but never trained it."
    elif m[cat] is None:
        reason = f"You haven't trained {name} yet."
    else:
        reason = f"{name} is your weakest area ({m[cat]:.0f}/100)."
    return cat, reason


def stats(state: dict) -> dict:
    att = state["attempts"]
    solved = [a for a in att if a["solved"]]
    return {
        "drills": len(att),
        "solved": len(solved),
        "no_hint": sum(1 for a in solved if a["hints_used"] == 0 and a["nudges_used"] == 0),
        "avg_seconds": (sum(a["seconds"] for a in solved) / len(solved)) if solved else None,
        "encounters": len(state["encounters"]),
    }


def demo_history(seed: int = 7) -> dict:
    """A clearly-labelled sample history so the dashboard can be explored instantly."""
    rng = random.Random(seed)
    st = new_state()
    profile = {  # (number of drills, typical score)
        "off_by_one": (4, 45), "boundary_compare": (3, 55), "mutable_default": (2, 90),
        "missing_return": (3, 85), "type_mixup": (2, 70), "scope": (1, 60),
        "aliasing": (2, 35), "logic": (1, 80),
    }
    t0 = time.time() - 6 * 86400
    for cat, (n, mu) in profile.items():
        for i in range(n):
            score = max(0, min(100, int(rng.gauss(mu + i * 6, 12))))
            hints = 0 if score >= 85 else (1 if score >= 60 else 2)
            st["attempts"].append({
                "ts": t0 + rng.random() * 5 * 86400, "category": cat, "snippet_id": None,
                "score": score, "solved": score > 0, "hints_used": hints, "nudges_used": 0,
                "checks": rng.randint(1, 4), "seconds": rng.randint(40, 420),
                "source": "demo", "demo": True,
            })
    for cat in ["off_by_one", "off_by_one", "aliasing", "type_mixup", "off_by_one"]:
        st["encounters"].append({"ts": t0 + rng.random() * 5 * 86400, "category": cat,
                                 "error_type": "demo", "demo": True})
    st["attempts"].sort(key=lambda a: a["ts"])
    return st
