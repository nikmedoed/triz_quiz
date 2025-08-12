# README

> **Language note:** All code comments and this README are in **English** as requested.

This project implements a TRIZ-club quiz/presentation system with **Telegram + Web**:

* **Telegram bot (aiogram 3)** for registration, open-form ideas, voting, and MCQ.
* **Web app (FastAPI + WebSockets)** for a live projector screen controlled locally.
* **SQLite** by default (switchable to Postgres). All state is persisted to survive restarts.
* **Scenario loaded from JSON/YAML list of blocks** (simple), activated on startup.
* **Scoring**: +`points` per correct MCQ; +1 per received vote on ideas; tie-breaker by total response time.

### Design decisions aligned with your requirements

* **No admin password**. Everything runs locally at `http://localhost:8000/`.
* **Mandatory Registration & Leaderboard** are **implicit** and **auto-inserted**: you **do not** specify them in the
  scenario.
* **Blocks, not micro-steps**: Each content item is a **block** with **internal phases** and a single **Next** control.

    * `open` block phases: **collect → vote (if ideas exist) → reveal**. Voting is skipped if there are no ideas.
    * `quiz` block phases: **ask → reveal**.
* **Next button** advances to the next **phase** inside the current block; if it was the last phase, it moves to the
  next block.
* **Late join**: a participant who joins at any time is synced to the current block & phase.

---

## Quick start (local)

1. **Create `.env`** with:

```
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
BASE_URL=http://localhost:8000
DATABASE_URL=sqlite+aiosqlite:///./quiz.db
TELEGRAM_SEND_DELAY=0.05
```

2. **Copy example scenario** (optional):

```
cp scenario.example.yaml scenario.yaml  # edit as needed
```

3. **Install**:

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

4. **Run**:

```
./run_local.sh
```

Open:

* `http://localhost:8000/`

Invite participants to start the Telegram bot with `/start`. After they set a name, advancing phases with the Next
button will push messages to all registered participants.

Messages are throttled with a small delay (configurable via `TELEGRAM_SEND_DELAY`) to avoid Telegram rate limits.

---

## Docker

```
docker compose up --build
```

---

## Scenario format (simple blocks)

Write `scenario.yaml` **or** `scenario.json` as a **list of blocks**. Registration and final leaderboard are **implicit
** and auto-added.

**Supported blocks:**

* `open`: free-form idea collection with built-in vote & reveal.
* `quiz`: MCQ with built-in reveal. Optional `time` (seconds) overrides the default 60-second timer.
* `multi`: multiple choice with several correct options. Scores are split evenly between correct answers; selecting any wrong option yields zero points.

**Example (your sample, with vote steps tolerated but folded into the `open` block):**

```json
[
  {
    "type": "open",
    "title": "Ситуация 1: как открыть банку с тугой крышкой?",
    "description": "Домашний пример, крышка не поддаётся…"
  },
  { "type": "vote", "title": "Голосование идей" },
  { "type": "vote_results", "title": "Результаты голосования" },
  {
    "type": "quiz",
    "title": "Какой приём ТРИЗ был использован?",
    "options": [
      "Матрёшка",
      "Динамичность",
      "Применение локальных нагревов",
      "Ещё какой-то вариант"
    ],
    "correct": "3",
    "time": 45,
    "points": 2
  }
]
```

> Notes:
>
> * `vote` and `vote_results` lines are **optional** and ignored by the loader (the `open` block already includes voting
    and reveal). You can keep them for readability.
> * `quiz.correct` accepts either a **1-based string/number** (e.g., `"3"`) or a **0-based index**.
>
> See `scenario.example.yaml` for a complete example scenario.

---

## Scoring rules

* **MCQ**: each correct answer gives `points` (per-quiz configurable).
* **Ideas**: **+1** to the author per received vote.
* **Tie-breaker**: lower total response time across blocks where the participant answered/voted.

---

## PPT usage

* Present your normal PowerPoint deck.
* When you need live results, **Alt-Tab** to the browser tab with the **Public screen** (or add a hyperlink to
  `BASE_URL/`).

---

## Reliability

* SQLite or Postgres (set `DATABASE_URL`).
* All transitions are idempotent; late joiners are synced.

---

## Styling tokens

Design tokens and component styles live in `app/static` as `tokens.css`, `base.css`, `leaderboard.css`, `ideas.css` and `components.css`.

### Tokens

* Color palette `--color-primary-*`, `--color-slate-*`, `--color-dark`, `--color-light`, `--color-black`.
* Typography: `--font-sans` (Roboto) with weights 300/400/500/900.
* Spacing & radii: `--space-*` and `--radius-*` following an 8‑pt grid.

### Updated components

* Header/navigation bar with active link underline.
* Primary and secondary buttons.
* Registration cards and leaderboard table borders.
* General typography for questions, hints and timers.

### Roboto font

Roboto weights are loaded from Google Fonts in `base.jinja2`:

```html
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;900&display=swap" rel="stylesheet" />
```

For offline usage, download these font files and serve them locally, adjusting the `<link>` accordingly.

