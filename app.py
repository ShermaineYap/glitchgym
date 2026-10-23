"""GlitchGym - the debugging coach that breaks your code on purpose.

Run:  streamlit run app.py
"""

from __future__ import annotations

import difflib
import json
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from glitchgym import coach, llm, progress
from glitchgym.catalog import CATEGORIES, CATEGORY_IDS, SNIPPETS, SNIPPETS_BY_ID
from glitchgym.sandbox import run_tests

st.set_page_config(page_title="GlitchGym", page_icon="🏋️", layout="wide")

# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@400;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, p, li { font-family: 'Space Grotesk', sans-serif; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.02em; }
textarea, code, pre { font-family: 'JetBrains Mono', monospace !important; font-size: 0.86rem !important; font-variant-ligatures: none !important; }
.stMarkdown .gg-hero, .gg-hero { font-size: 2.5rem !important; font-weight: 700; line-height: 1.1 !important; margin: 0 0 .2rem 0; letter-spacing: -0.03em; }
.stMarkdown .gg-logo { font-size: 1.8rem !important; }
.gg-hero span { color: #C6FF3D; text-shadow: 1.5px 1.5px 0 #FF3D9A66; }
.stMarkdown .gg-sub, .gg-sub { color: #9aa4b2; margin: .3rem 0 1rem 0; font-size: 1.05rem !important; }
button[kind="primary"], button[kind="primary"] p { color: #0D1017 !important; font-weight: 700 !important; }
button[kind="primary"]:disabled, button[kind="primary"]:disabled p { color: #6b7587 !important; }
.gg-sub { color: #9aa4b2; margin: .3rem 0 1rem 0; font-size: 1.05rem; }
.gg-card { border: 1px solid #2a2f3a; border-radius: 14px; padding: 14px 16px; margin-bottom: 12px; background: #141821; }
.gg-pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600;
           border: 1px solid #C6FF3D55; color: #C6FF3D; background: #C6FF3D14; margin-right: 6px; }
.gg-pill.red { border-color: #FF5C7A55; color: #FF7A93; background: #FF5C7A14; }
.gg-pill.blue { border-color: #3DD8FF55; color: #6FE3FF; background: #3DD8FF14; }
.gg-test { font-family: 'JetBrains Mono', monospace; font-size: .82rem; padding: 6px 10px; border-radius: 8px; margin: 4px 0; }
.gg-pass { background: #13261a; border-left: 3px solid #3ddc84; }
.gg-fail { background: #2a1418; border-left: 3px solid #ff5c7a; }
.gg-err { color: #ff9fb0; display: block; margin-top: 2px; }
.gg-rule { border-left: 4px solid #C6FF3D; padding: 8px 14px; background: #C6FF3D10; border-radius: 6px; }
.gg-muted { color: #8b95a5; font-size: .85rem; }
</style>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
ss = st.session_state
ss.setdefault("page", "🏋️ Gym")
ss.setdefault("prog", progress.new_state())
ss.setdefault("ch", None)
ss.setdefault("ch_n", 0)
ss.setdefault("diag", None)
ss.setdefault("diag_code", "")
ss.setdefault("diag_err", "")
ss.setdefault("diag_expected", "")
ss.setdefault("pending_category", None)
ss.setdefault("suggest", None)


def suggestion():
    """Stable adaptive pick: computed once, refreshed only after a drill is logged."""
    if ss.suggest is None:
        ss.suggest = progress.next_category(ss.prog)
    return ss.suggest

DIAG_EXAMPLES = {
    "IndexError in a loop": (
        """temps = [31, 33, 30, 29]
for i in range(len(temps)):
    change = temps[i + 1] - temps[i]
    print(f"Day {i + 1} -> {i + 2}: {change:+d}")
""", "", ""),
    "TypeError from text data": (
        """ages = "19,21,20"
total = 0
for a in ages.split(","):
    total = total + a
print("Average age:", total / 3)
""", "", ""),
    "Wrong output, no error": (
        """def register(student, course_list=[]):
    course_list.append(student)
    return course_list

print(register("Aisyah"))
print(register("Ben"))
""", "", "The second print should show ['Ben'] but it shows ['Aisyah', 'Ben']"),
}


def go_to(page: str, category: str | None = None):
    ss.page = page
    if category:
        ss.pending_category = category


def reset_drill_state():
    ss.hints_used = 0
    ss.nudges = []
    ss.checks = 0
    ss.started = time.time()
    ss.solved = False
    ss.gave_up = False
    ss.logged = False
    ss.last_report = None
    ss.final_score = None
    ss.final_code = ""


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown('<div class="gg-hero gg-logo">Glitch<span>Gym</span></div>', unsafe_allow_html=True)
    st.caption("Break things. Fix them. Get better at both.")
    st.radio("Go to", ["🏋️ Gym", "🩺 Diagnose", "📈 Progress", "ℹ️ How it works"], key="page",
             label_visibility="collapsed")
    st.divider()
    av = llm.available()
    if av["gemini"] or av["groq"]:
        st.markdown(
            ("<span class='gg-pill'>Gemini ✓</span>" if av["gemini"] else "<span class='gg-pill red'>Gemini ✗</span>")
            + ("<span class='gg-pill blue'>Groq ✓</span>" if av["groq"] else ""),
            unsafe_allow_html=True)
    else:
        st.markdown("<span class='gg-pill red'>Offline mode</span>", unsafe_allow_html=True)
        st.caption("No API key found. Gym uses the pre-verified bug bank and Diagnose uses rule-based "
                   "explanations. Add GEMINI_API_KEY for the full AI coach.")
    s = progress.stats(ss.prog)
    st.metric("Drills solved", f"{s['solved']}/{s['drills']}")
    st.metric("Solved with zero help", s["no_hint"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def render_report(report):
    if report is None:
        return
    if report.timed_out:
        st.error("⏱️ Your code timed out. Is there a loop that never ends?")
        return
    if report.load_error:
        st.error("Your code doesn't load yet:")
        st.code(report.load_error, language="text")
        return
    html = []
    for r in report.results:
        cls = "gg-pass" if r.passed else "gg-fail"
        icon = "✅" if r.passed else "❌"
        err = f"<span class='gg-err'>{_esc(r.error)}</span>" if r.error else ""
        html.append(f"<div class='gg-test {cls}'>{icon} {_esc(r.test)}{err}</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unified(a: str, b: str, a_name: str, b_name: str) -> str:
    return "\n".join(difflib.unified_diff(a.strip().splitlines(), b.strip().splitlines(),
                                          fromfile=a_name, tofile=b_name, lineterm="", n=1))


# --------------------------------------------------------------------------- #
# GYM
# --------------------------------------------------------------------------- #
def page_gym():
    st.markdown('<div class="gg-hero">The debugging coach that <span>breaks your code</span> on purpose.</div>',
                unsafe_allow_html=True)
    st.markdown('<p class="gg-sub">AI tools fix our bugs for us now, so we never practise fixing them. '
                'GlitchGym injects one realistic bug, proves it with failing tests, and coaches you to the fix '
                'without handing it over.</p>', unsafe_allow_html=True)

    auto_cat, reason = suggestion()
    if ss.pending_category:
        auto_cat, reason = ss.pending_category, "You just hit this bug type in your own code (from Diagnose)."

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1.3])
        with c1:
            cat_options = ["🎯 Adaptive (my weakest area)"] + [CATEGORIES[c]["name"] for c in CATEGORY_IDS]
            default_idx = 0 if not ss.pending_category else 1 + CATEGORY_IDS.index(ss.pending_category)
            cat_choice = st.selectbox("Bug type to train", cat_options, index=default_idx)
        with c2:
            src_options = ["🎲 Sample exercise", "📋 My own code"] + [f"{s.title}" for s in SNIPPETS]
            src_choice = st.selectbox("Code to break", src_options)
        with c3:
            blind = st.toggle("Blind mode", help="Hide the bug type. Harder, closer to real life.")
        if cat_choice.startswith("🎯"):
            st.markdown(f"<span class='gg-muted'>Next adaptive drill: <b>{CATEGORIES[auto_cat]['name']}</b>. {reason}</span>",
                        unsafe_allow_html=True)

        custom_code = ""
        if src_choice == "📋 My own code":
            custom_code = st.text_area(
                "Paste WORKING Python that defines at least one function. The AI writes tests for it, "
                "checks they pass, then breaks it.", height=180, key="custom_code",
                placeholder="def is_palindrome(s):\n    s = s.lower()\n    return s == s[::-1]")

        auto = ss.pop("auto_start", False)
        if st.button("💥 Break it", type="primary", width="stretch") or auto:
            if auto:
                cat_choice, src_choice = cat_options[0], src_options[0]
            category = auto_cat if cat_choice.startswith("🎯") else CATEGORY_IDS[cat_options.index(cat_choice) - 1]
            snippet_id = None
            if src_choice == "🎲 Sample exercise":
                snippet_id = coach.pick_snippet_for(category)
            elif src_choice != "📋 My own code":
                snippet_id = SNIPPETS[src_options.index(src_choice) - 2].id
            try:
                with st.status("Breaking your code...", expanded=False) as status:
                    status.write("Running the original against its tests...")
                    ch = coach.make_challenge(category, snippet_id=snippet_id,
                                              custom_code=custom_code if src_choice == "📋 My own code" else None)
                    for line in ch.verification_log:
                        status.write(line)
                    status.update(label="Bug injected and verified ✔", state="complete")
                ss.ch = ch
                ss.ch_n += 1
                ss.pending_category = None
                ss.blind = blind
                reset_drill_state()
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    ch = ss.ch
    if ch is None:
        st.info("Pick a bug type and press **Break it** to start a drill. New here? Leave both on the defaults.")
        return

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader(f"🐛 {ch.title}")
        st.markdown(f"{ch.description}  \n<span class='gg-muted'>This code *used to* pass every test below. "
                    f"Someone broke it. Find the bug and fix it.</span>", unsafe_allow_html=True)
        code = st.text_area("Your fix", value=ch.mutated_code, height=max(180, 26 * ch.mutated_code.count("\n") + 60),
                            key=f"editor_{ss.ch_n}", disabled=ss.solved or ss.gave_up)
        b1, b2 = st.columns(2)
        run = b1.button("▶ Run tests", type="primary", width="stretch", disabled=ss.solved or ss.gave_up)
        giveup = b2.button("🏳️ Show me the answer", width="stretch", disabled=ss.solved or ss.gave_up)

        if ss.last_report is None:
            ss.last_report = ch.baseline and run_tests(ch.mutated_code, ch.tests)
        if run:
            ss.checks += 1
            ss.last_report = run_tests(code, ch.tests)
            if ss.last_report.ok:
                ss.solved = True
                ss.final_code = code
                st.rerun()
        if giveup:
            ss.gave_up = True
            st.rerun()

        st.markdown("**Tests**")
        render_report(ss.last_report)

        if (ss.solved or ss.gave_up) and not ss.logged:
            score = coach.score_attempt(ss.hints_used, len(ss.nudges), ss.checks, ss.solved, ss.gave_up)
            progress.log_attempt(ss.prog, category=ch.category, snippet_id=ch.snippet_id, score=score,
                                 solved=ss.solved, hints_used=ss.hints_used, nudges_used=len(ss.nudges),
                                 checks=ss.checks, seconds=time.time() - ss.started, source=ch.source)
            ss.final_score = score
            ss.logged = True
            ss.suggest = None
            if ss.solved:
                st.balloons()

        if ss.solved or ss.gave_up:
            if ss.solved:
                st.success(f"🎉 Fixed! All tests pass. Score **{ss.final_score}/100** "
                           f"({ss.hints_used} hints, {len(ss.nudges)} coach nudges, {ss.checks} test runs, "
                           f"{time.time() - ss.started:.0f}s).")
            else:
                st.warning("No worries, here's what happened. Seeing the bug is half the training.")
            st.markdown(f"### What the bug was: {CATEGORIES[ch.category]['name']}")
            st.markdown(f"<div class='gg-rule'>{_esc(ch.explanation)}</div>", unsafe_allow_html=True)
            st.markdown("**The injected change**")
            st.code(unified(ch.original_code, ch.mutated_code, "working.py", "broken.py"), language="diff")
            if ss.solved and (ss.get('final_code') or code).strip() != ch.original_code.strip():
                with st.expander("Your fix vs the original"):
                    st.code(unified(ch.original_code, (ss.get("final_code") or code), "original.py", "your_fix.py"), language="diff")
                    st.caption("Different from the original but every test passes, so it counts.")
            nxt, reason = suggestion()
            st.markdown(f"<span class='gg-muted'>Up next: <b>{CATEGORIES[nxt]['name']}</b>. {reason}</span>",
                        unsafe_allow_html=True)
            st.button(f"💥 Next drill: {CATEGORIES[nxt]['name']}", type="primary", width="stretch",
                      on_click=lambda: ss.update(auto_start=True))

    with right:
        if ss.blind and not (ss.solved or ss.gave_up):
            st.markdown("<span class='gg-pill red'>Blind mode: bug type hidden</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='gg-pill'>Bug type: {CATEGORIES[ch.category]['name']}</span>"
                        f"<span class='gg-pill blue'>{_esc(ch.source)}</span>", unsafe_allow_html=True)
            st.caption(CATEGORIES[ch.category]["blurb"])

        st.markdown("#### 🪜 Hint ladder")
        st.caption("Each hint costs 20 points. Try the tests first.")
        for i, h in enumerate(ch.hints):
            if i < ss.hints_used:
                st.markdown(f"<div class='gg-card'><b>Hint {i + 1}</b><br>{_esc(h)}</div>", unsafe_allow_html=True)
        if ss.hints_used < len(ch.hints) and not (ss.solved or ss.gave_up):
            if st.button(f"Reveal hint {ss.hints_used + 1} of {len(ch.hints)}", width="stretch"):
                ss.hints_used += 1
                st.rerun()

        st.markdown("#### 🧠 Ask the coach")
        st.caption("Reads YOUR current attempt and test results, then asks you a question. Never gives the answer. -10 points.")
        for n, prov in ss.nudges:
            st.markdown(f"<div class='gg-card'>💬 {_esc(n)}<br><span class='gg-muted'>{_esc(prov)}</span></div>",
                        unsafe_allow_html=True)
        if not (ss.solved or ss.gave_up):
            if st.button("Nudge me", width="stretch"):
                current = st.session_state.get(f"editor_{ss.ch_n}", ch.mutated_code)
                report = run_tests(current, ch.tests)
                with st.spinner("Coach is reading your attempt..."):
                    text, prov = coach.nudge(ch, current, report, ss.hints_used)
                ss.nudges.append((text, prov))
                ss.last_report = report
                st.rerun()

        with st.expander("🔬 How this bug was made and verified"):
            st.markdown("The AI proposes a bug; the sandbox only accepts it if the original passes every test, "
                        "the mutant parses, keeps the same functions, changes only a few lines, doesn't hang, "
                        "and fails at least one test.")
            for line in ch.verification_log:
                st.markdown(f"- {_esc(line)}")
            if ch.baseline:
                st.markdown(f"- Original code: {ch.baseline.summary()} ✔")


# --------------------------------------------------------------------------- #
# DIAGNOSE
# --------------------------------------------------------------------------- #
def page_diagnose():
    st.markdown('<div class="gg-hero">Paste the error. Get the <span>why</span>.</div>', unsafe_allow_html=True)
    st.markdown('<p class="gg-sub">Root cause in plain English, a step-by-step trace, a fix that is run in a sandbox '
                'before you see it, and a drill on the same bug type.</p>', unsafe_allow_html=True)

    ex_cols = st.columns(len(DIAG_EXAMPLES) + 1)
    ex_cols[0].markdown("<span class='gg-muted'>Try an example:</span>", unsafe_allow_html=True)
    for col, (name, (code, err, exp)) in zip(ex_cols[1:], DIAG_EXAMPLES.items()):
        if col.button(name, width="stretch"):
            ss.diag_code, ss.diag_err, ss.diag_expected, ss.diag = code, err, exp, None
            st.rerun()

    c1, c2 = st.columns([3, 2])
    with c1:
        code = st.text_area("Your code", value=ss.diag_code, height=260,
                            placeholder="Paste the Python that's breaking...")
    with c2:
        err = st.text_area("Error message (optional)", value=ss.diag_err, height=140,
                           placeholder="Leave empty and GlitchGym will run your code to capture the error.")
        expected = st.text_input("What did you expect instead? (for wrong-output bugs)", value=ss.diag_expected)
    if st.button("🩺 Diagnose", type="primary", width="stretch", disabled=not code.strip()):
        ss.diag_code, ss.diag_err, ss.diag_expected = code, err, expected
        with st.spinner("Running your code and reading the traceback..."):
            ss.diag = coach.diagnose(code, err, expected)
        d = ss.diag
        if not d.get("no_error"):
            progress.log_encounter(ss.prog, d.get("category", "logic"), d.get("error_type", "?"))
            ss.suggest = None

    d = ss.diag
    if not d:
        return
    if d.get("no_error"):
        st.success("Your code ran without errors. If the output is wrong, describe what you expected and diagnose again.")
        if d.get("stdout"):
            st.code(d["stdout"], language="text")
        return

    st.divider()
    cat = d.get("category", "logic")
    st.markdown(f"<span class='gg-pill red'>{_esc(str(d.get('error_type', 'Error')))}</span>"
                f"<span class='gg-pill'>Bug type: {CATEGORIES[cat]['name']}</span>"
                f"<span class='gg-pill blue'>{_esc(d.get('provider', ''))}</span>", unsafe_allow_html=True)
    if d.get("captured_error"):
        with st.expander("Captured error"):
            st.code(d["captured_error"], language="text")

    a, b = st.columns([3, 2], gap="large")
    with a:
        st.markdown("### What it means")
        st.write(d.get("plain_english", ""))
        st.markdown("### Root cause" + (f" (line {d['line']})" if d.get("line") else ""))
        st.write(d.get("root_cause", ""))
        if d.get("walkthrough"):
            st.markdown("### What Python did, step by step")
            for i, step in enumerate(d["walkthrough"], 1):
                st.markdown(f"{i}. {step}")
        if d.get("fix_code"):
            st.markdown("### The fix")
            st.code(d["fix_code"], language="python")
            chk = d.get("fix_check")
            if chk:
                {"pass": st.success, "warn": st.warning, "fail": st.error}[chk[0]](chk[1])
            if d.get("why_fix_works"):
                st.caption(d["why_fix_works"])
    with b:
        st.markdown("### Rule of thumb")
        st.markdown(f"<div class='gg-rule'>{_esc(d.get('mental_model', ''))}</div>", unsafe_allow_html=True)
        qc = d.get("quick_check")
        if isinstance(qc, dict) and qc.get("options"):
            st.markdown("### Quick check")
            pick = st.radio(qc.get("question", ""), qc["options"], index=None, key=f"qc_{hash(d.get('root_cause',''))}")
            if pick is not None:
                ok = qc["options"].index(pick) == int(qc.get("answer_index", 0))
                (st.success if ok else st.error)(("Correct! " if ok else "Not quite. ") + str(qc.get("why", "")))
        st.markdown("### Practise it")
        st.write(f"Understanding it once isn't the same as spotting it next time. Train **{CATEGORIES[cat]['name']}** "
                 "on fresh code, with a bug the AI injects and the tests prove.")
        st.button(f"🏋️ Train {CATEGORIES[cat]['name']} now", type="primary", width="stretch",
                  on_click=go_to, args=("🏋️ Gym", cat))


# --------------------------------------------------------------------------- #
# PROGRESS
# --------------------------------------------------------------------------- #
def page_progress():
    st.markdown('<div class="gg-hero">Your <span>bug fingerprint</span>.</div>', unsafe_allow_html=True)
    st.markdown('<p class="gg-sub">Mastery per bug type from your last 5 drills, plus the bugs you actually hit in your own '
                'code. The next drill always targets the gap.</p>', unsafe_allow_html=True)

    att = ss.prog["attempts"]
    if not att and not ss.prog["encounters"]:
        st.info("No drills yet. Do a couple in the Gym, or load a sample history to explore the dashboard.")
        if st.button("Load sample history (clearly marked as demo data)"):
            ss.prog = progress.demo_history()
            ss.suggest = None
            st.rerun()
        return
    if any(a.get("demo") for a in att):
        st.warning("Showing **sample demo data**. Use *Reset progress* below to start fresh.")

    s = progress.stats(ss.prog)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Drills", s["drills"])
    m2.metric("Solved", s["solved"])
    m3.metric("Zero-help solves", s["no_hint"])
    m4.metric("Avg time to fix", f"{s['avg_seconds']:.0f}s" if s["avg_seconds"] else "-")

    mast, enc, pr = progress.mastery(ss.prog), progress.encounters(ss.prog), progress.priorities(ss.prog)
    rows = []
    for c in CATEGORY_IDS:
        rows.append({"Bug type": CATEGORIES[c]["name"], "Mastery": mast[c], "Hit in own code": enc[c],
                     "Drills": sum(1 for a in att if a["category"] == c), "Priority": pr[c], "id": c})
    df = pd.DataFrame(rows).sort_values("Priority", ascending=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Mastery by bug type")
        colors = ["#3a4150" if pd.isna(v) else ("#ff5c7a" if v < 50 else "#ffc53d" if v < 75 else "#3ddc84")
                  for v in df["Mastery"]]
        fig = go.Figure(go.Bar(
            x=df["Mastery"].fillna(2), y=df["Bug type"], orientation="h", marker_color=colors,
            text=[("not trained" if pd.isna(v) else f"{v:.0f}") + (f"   · hit {e}x in your code" if e else "")
                  for v, e in zip(df["Mastery"], df["Hit in own code"])],
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:.0f}/100<extra></extra>"))
        fig.update_layout(xaxis=dict(range=[0, 135], title="mastery (0-100)", showgrid=False),
                          yaxis=dict(title=""), height=420, margin=dict(l=10, r=10, t=10, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#c9d1d9"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Sorted so the bug type you should practise next is at the top. Red < 50, amber < 75, green ≥ 75.")

    with right:
        st.markdown("#### Drill history heatmap")
        cats_seen = [c for c in CATEGORY_IDS if any(a["category"] == c for a in att)]
        if cats_seen:
            n = 6
            z, text = [], []
            for c in cats_seen:
                sc = [a["score"] for a in att if a["category"] == c][-n:]
                z.append([None] * (n - len(sc)) + sc)
                text.append([""] * (n - len(sc)) + [str(v) for v in sc])
            hm = go.Figure(go.Heatmap(
                z=z, x=[f"#{i}" for i in range(1, n + 1)], y=[CATEGORIES[c]["name"] for c in cats_seen],
                text=text, texttemplate="%{text}", colorscale=[[0, "#ff5c7a"], [0.5, "#ffc53d"], [1, "#3ddc84"]],
                zmin=0, zmax=100, showscale=False, hovertemplate="%{y} %{x}: %{z}<extra></extra>"))
            hm.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="last 6 drills →",
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#c9d1d9"))
            st.plotly_chart(hm, width="stretch")
        else:
            st.caption("Heatmap appears after your first drill.")

    nxt, reason = suggestion()
    with st.container(border=True):
        st.markdown(f"**🎯 Recommended next drill: {CATEGORIES[nxt]['name']}**  \n{reason}")
        st.button("Start it", type="primary", on_click=go_to, args=("🏋️ Gym", nxt))

    with st.expander("Raw attempt log"):
        if att:
            st.dataframe(pd.DataFrame(att).drop(columns=["ts"]), width="stretch", hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ Export progress (JSON)", json.dumps(ss.prog, indent=2), "glitchgym_progress.json",
                       "application/json", width="stretch")
    up = c2.file_uploader("Import progress", type="json", label_visibility="collapsed")
    if up is not None:
        try:
            data = json.load(up)
            assert "attempts" in data and "encounters" in data
            ss.prog = data
            ss.suggest = None
            st.success("Progress imported.")
        except Exception:
            st.error("That file isn't a GlitchGym progress export.")
    if c3.button("🗑️ Reset progress", width="stretch"):
        ss.prog = progress.new_state()
        ss.suggest = None
        st.rerun()


# --------------------------------------------------------------------------- #
# ABOUT
# --------------------------------------------------------------------------- #
def page_about():
    st.markdown('<div class="gg-hero">How <span>GlitchGym</span> works</div>', unsafe_allow_html=True)
    st.markdown("""
**The problem.** Students now paste errors into an AI and copy the fix. The bug disappears, and so does the
chance to learn. Debugging is a skill you only build by debugging, and nobody gives students reps.

**The idea.** Flip it. GlitchGym takes code that *works*, breaks it on purpose in one realistic way, proves the
break with failing tests, and coaches you to the fix with questions instead of answers. It remembers which bug
types you miss, including the ones you hit in your own code, and drills those next.

**Three ways AI is used**
1. **Diagnose** (Gemini, JSON mode): error → plain-English meaning, root cause at the exact line, a step-by-step
   trace, a minimal fix, a rule of thumb, and a quick-check question. The fix is **executed in a sandbox** before it is shown.
2. **Bug injection** (Gemini, temperature 0.8): given working code, its tests and a target bug category, the model
   writes one realistic mutant plus a 3-step hint ladder and an explanation. For your own code it first **writes the
   tests** too, and only tests your code actually passes are kept.
3. **Socratic coach** (Gemini): reads your *current* attempt and test results and asks one question that moves you
   forward, never pasting the fix.

**Why it can be trusted: the model proposes, the sandbox disposes.** A mutant is accepted only if the original
passes every test, the mutant parses, keeps the same functions, changes few lines, doesn't hang, and fails at
least one test. Rejected mutants are sent back to the model with the reason (up to 3 tries). If the AI is down or
there's no key, a hand-verified offline bug bank (19 bugs × 10 categories) keeps the gym running.

**Stack:** Python · Streamlit · Gemini API (Google AI Studio) with Groq (Llama 3.3 70B) fallback · subprocess
sandbox · pandas · Plotly.
""")
    if _exists("docs/architecture.png"):
        st.image("docs/architecture.png", width="stretch")


def _exists(p: str) -> bool:
    import os
    return os.path.exists(p)


PAGES = {"🏋️ Gym": page_gym, "🩺 Diagnose": page_diagnose, "📈 Progress": page_progress,
         "ℹ️ How it works": page_about}
PAGES[ss.page]()
