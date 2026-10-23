# GlitchGym — Glitchathon submission pack

Deadline: **Sun 25 Oct 2026, 5:00 pm IST = 7:30 pm Malaysia time.** Aim to submit by 5 pm MYT.

---

## 0. Things only you can do (in this order)

| # | Step | Time |
|---|---|---|
| 1 | Register on https://glitchathon.devpost.com ("Join hackathon"). Then send the organiser email (section 4). | 5 min |
| 2 | Get a free Gemini key at https://aistudio.google.com/apikey | 2 min |
| 3 | Run locally with the key (`cp .env.example .env`, paste key, `streamlit run app.py`). Do one Diagnose example and one drill to confirm the sidebar shows **Gemini ✓** and drills say "Gemini (...)" not "Offline bug bank". | 10 min |
| 4 | Create a **public** GitHub repo `glitchgym`, push (section 5). | 5 min |
| 5 | Deploy on Streamlit Community Cloud with the key in Secrets (README → Deploy). Test the link on your phone. | 10 min |
| 6 | Retake 2 screenshots with the AI on (they currently show offline mode): a Gym drill + a Diagnose result. Replace files in `docs/screenshots/`. | 5 min |
| 7 | Record the ≤3-min video (section 3), upload to YouTube as **Unlisted**, embedding allowed. | 45 min |
| 8 | Fill the Devpost form (section 1–2), pick track **Glitch Detective**, submit. | 15 min |

---

## 1. Devpost fields

**Project name:** GlitchGym

**Tagline (≤60 chars):** The debugging coach that breaks your code on purpose

**Track:** 2. Glitch Detective

**Built with:** python, streamlit, gemini, google-ai-studio, groq, llama, pandas, plotly, pytest

**Links:** live Streamlit URL · GitHub repo · YouTube video

**Images:** `docs/screenshots/1_gym_drill.png`, `2_gym_solved.png`, `3_diagnose.png`, `4_progress.png`, `docs/architecture.png`

---

## 2. Devpost description (paste into "About the project")

## Inspiration
Every CS student now has an AI that fixes their bugs. Paste the traceback, copy the fix, move on. The error disappears, and so does the one moment where you would have learned something. Debugging is a skill you only build by debugging, and nobody gives students practice reps. Glitchathon's tagline is "Break things, fix them with AI", so I built something that does exactly that.

## What it does
GlitchGym is a debugging coach with three parts:

- **🩺 Diagnose (the Glitch Detective brief).** Paste broken Python. GlitchGym runs it to capture the error, then explains *why* it broke: what the error means in plain English, the root cause at the exact line, a step-by-step trace of what Python did, a minimal fix, a rule of thumb, and a one-question quick check. The fix is executed in a sandbox before you see it, so you're told whether it actually works. One click turns the diagnosis into a practice drill on the same bug type.
- **🏋️ Gym (the twist).** GlitchGym takes code that *works*, and AI injects one realistic bug of a chosen type (off-by-one, mutable default, aliasing, and 7 more). The bug is only accepted after the sandbox proves the original passes every test and the broken version fails at least one. You fix it in the browser, with a 3-step hint ladder and a Socratic coach that reads *your current attempt* and asks a question instead of giving the answer. You can also paste your own working code: the AI writes tests for it, keeps only the ones your code passes, then breaks it.
- **📈 Progress.** Mastery per bug type, a drill-history heatmap and a count of bugs you hit in your own code. The next drill targets whichever is weakest, so it trains *your* blind spots.

## How we built it
Python + Streamlit for the app. Gemini (Google AI Studio, JSON mode) powers four jobs: diagnosis, bug injection, test writing and Socratic coaching, with Groq (Llama 3.3 70B) as an automatic fallback. Every piece of AI output that makes a claim about code goes through a sandbox: an isolated Python subprocess with a timeout and CPU/memory caps that runs each test separately and reports structured results, including the actual value on a failed assert. A verifier accepts an AI-generated bug only if it parses, keeps the same functions, changes at most a few lines, doesn't hang, and fails at least one test; rejected bugs go back to the model with the reason, up to three tries. A hand-verified offline bug bank (19 bugs across 10 categories) means the gym never dead-ends if the API is down. 48 pytest tests cover the sandbox, every seed bug, the verifier and the retry loop (with the LLM mocked).

## How we used AI
- **Gemini** for diagnosis (T=0.2), bug injection with hints and explanations (T=0.8), test generation (T=0.2) and live Socratic nudges (T=0.5), all with strict JSON output.
- **Groq / Llama 3.3 70B** as a fallback provider.
- **Design principle: the model proposes, the sandbox disposes.** No AI-written bug, test or fix reaches the student without being executed.
- I also used an AI coding assistant (Claude) while building; all code was written during the hackathon and reviewed and tested by me.

## Challenges we ran into
- **LLMs write convincing but wrong bugs.** Early mutants often still passed every test (no real bug) or changed half the function. The verify-and-retry loop with the rejection reason fed back to the model fixed most of this.
- **AI-written tests can be wrong too.** For pasted code, tests are run against the student's working code first and any that fail are dropped.
- **Showing "got X" on a failed assert without calling the function twice** (which corrupted results for stateful bugs like mutable defaults). I rewrote each assert's AST to capture the left-hand value first.
- Making it reliable for a live demo: model-name fallback, provider fallback, and the offline bug bank.

## Accomplishments that we're proud of
A full loop that a judge can try in two minutes: break → fail → hint → fix → green → explanation → next adaptive drill. And every AI claim is checked by running code.

## What we learned
Prompting is half the work; verification is the other half. Grounding an LLM with executable checks turned it from "usually right" into something I'd trust in front of a beginner.

## What's next for GlitchGym
Pyodide so code runs in the browser; JavaScript and Java; instructor mode that turns a lab's starter code into a set of verified bug drills for the class; spaced repetition; and a VS Code extension that offers a drill straight from a real traceback.

---

## 3. Demo video script (target 2:45)

Record the screen with OBS or the Xbox Game Bar (Win+G). 1080p, browser zoom 110%, close other tabs. Speak slowly. Use the **live AI**, not offline mode.

**0:00–0:20 — Hook.** (Show a chat window pasting an error and copying a fix.)
> "This is how most of us debug now: paste the error, copy the fix, move on. The bug's gone, but so is the learning. Glitchathon says 'break things, fix them with AI'. So I built GlitchGym, a debugging coach that breaks your code on purpose."

**0:20–0:55 — Diagnose.** Diagnose → "TypeError from text data" → Diagnose.
> "First, the Glitch Detective part. I paste broken code, no error needed: GlitchGym runs it, captures the TypeError, and explains why: split always returns strings. Root cause at line 4, a step-by-step trace, and a fix. Notice this green tick: the fix was actually executed in a sandbox before I was shown it. Then a rule of thumb, and one click to practise this exact bug type."
Click **Train Type mix-up now**.

**0:55–1:55 — Gym.** Break it → show failing tests → reveal hint 1 → click Nudge me → fix → Run tests → green → explanation + diff.
> "Now the twist. GlitchGym takes working code and Gemini injects one realistic bug. It's only accepted if the sandbox proves the original passes and the broken one fails. Here's the verification log: [open 'How this bug was made'] if the AI's bug doesn't break any test, it's rejected and sent back with the reason. (If the log shows a rejected attempt, point at it — that's the best moment in the video.) I get failing tests with the actual values... a hint... and the coach reads *my* attempt and asks me a question, it never gives the answer. Fixed. All green. Then the explanation and the exact change that was injected."

**1:55–2:20 — Progress.** Progress page.
> "Every drill feeds my bug fingerprint: mastery per bug type, a heatmap of recent drills, and the bugs I hit in my own code from Diagnose. The next drill targets my weakest spot."
(If showing sample data, say "here with sample data".)

**2:20–2:45 — How it's built.** How it works page / architecture image.
> "Under the hood: Streamlit, Gemini in JSON mode for diagnosis, bug injection, test writing and coaching, Groq as fallback, and a sandbox verifier so no AI output reaches a student unchecked. There's an offline bug bank so it never dead-ends, and 48 tests. GlitchGym: stop copying fixes, start training. Links are below."

Upload title: **GlitchGym – the debugging coach that breaks your code on purpose (Glitchathon 2026)**

---

## 4. Email to the organisers

Use the "Email the hackathon manager" link on the Devpost overview page.

**Subject:** Glitchathon – late registration and demo format (international student)

> Hi Glitchathon team,
>
> I'm Shermaine Yap, an undergraduate student at Asia Pacific University (APU) in Kuala Lumpur, Malaysia. I've registered on Devpost after the 16 October date because the "Join hackathon" button was still open, and I'm submitting a project in the Glitch Detective track before the 25 October deadline.
>
> Could you please confirm:
> 1. That late registrants are eligible for judging.
> 2. Whether the 25 October final demos are live, or whether the required demo video is sufficient. If live, what time (IST) and platform?
> 3. Whether participants outside India are eligible for the prize.
>
> Thank you for organising the event.
>
> Best regards,
> Shermaine Yap Shi Min
> Asia Pacific University of Technology and Innovation, Malaysia

---

## 5. Push to GitHub

The project folder is already a git repo with an initial commit.

```bash
cd glitchgym
git remote add origin https://github.com/<your-username>/glitchgym.git
git branch -M main
git push -u origin main
```
(Or use GitHub Desktop: File → Add local repository → Publish, untick "Keep this code private".)

Before pushing, make sure `.env` is **not** in the folder listing on GitHub (it's in `.gitignore`).

---

## 6. Final checklist (eligibility requirements)

- [ ] Title + tagline
- [ ] Description: problem & who it helps · how it works · how AI was used · challenges & learnings
- [ ] Working demo: live link **and** video
- [ ] Video ≤ 3:00, YouTube/Vimeo, embedding enabled
- [ ] Public GitHub repo with README explaining how to run
- [ ] "Built with" list
- [ ] ≥ 2 screenshots
- [ ] Optional: architecture diagram, future improvements (both in README / description)
- [ ] Track selected: Glitch Detective
- [ ] Submitted before 7:30 pm MYT, Sun 25 Oct
