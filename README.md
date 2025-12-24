# README

> **Language note:** All code comments and this README are in **English** as requested.

This project implements a TRIZ-club quiz/presentation system with **Telegram + Web**:

* **Telegram bot (aiogram 3)** for registration, open-form ideas, voting, MCQ, and sequence ordering.
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
    * `quiz` and `sequence` block phases: **ask → reveal**.
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

3. **Install** (pick one):

```
# pip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# or uv (faster resolver, uses uv.lock)
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

4. **Run**:

```
./run_local.sh
```

Open:

* `http://localhost:8000/` (projector/public screen)

Invite participants to start the Telegram bot with `/start`. After they set a name, advancing phases with the Next
button will push messages to all registered participants.

Messages are throttled with a small delay (configurable via `TELEGRAM_SEND_DELAY`) to avoid Telegram rate limits.

### Operating the session

1. Start the bot and web server (`./run_local.sh`).
2. Share the bot link; users complete registration and set a name.
3. Open the projector at `BASE_URL/` on a big screen.
4. Moderator clicks **Next** to move through phases inside each block (collect → vote → reveal or ask → reveal).
5. To reload a scenario after edits, call `POST /api/reset` or restart the app (registration/leaderboard are auto-added).

---

## Docker

```
docker compose up --build
```

---

## Scenario format (simple blocks)

Write `scenario.yaml` **or** `scenario.json` as a **list of blocks**. Registration and final leaderboard are **implicit**
and auto-added.

**Supported blocks:**

* `open`: free-form idea collection with built-in vote & reveal.
* `quiz`: MCQ with built-in reveal. Optional `time` (seconds) overrides the default 60-second timer.
* `sequence`: order options in a correct sequence. Optional `time` overrides the default 120-second timer. Optional
  `points` override the default value of 3.
* `multi`: multiple choice with several correct options. Provide `correct_options` and list remaining distractors via
  `other_options` (or `options`). Choices are shuffled automatically; scores are split evenly between correct answers, and
  selecting any wrong option yields zero points.

**Example (minimal flow; vote steps are implicit inside `open`):**

```json
[
  {
    "type": "open",
    "title": "Scenario 1: opening a stuck jar lid",
    "description": "Everyday case: the lid is stuck; you need a quick idea to open it."
  },
  { "type": "vote", "title": "Voting ideas" },
  { "type": "vote_results", "title": "Voting results" },
  {
    "type": "quiz",
    "title": "Which TRIZ principle helps most here?",
    "options": [
      "Nested doll",
      "Dynamics",
      "Local heating",
      "Cushion in advance"
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
> * `multi` blocks accept `correct_options` (list of texts). Provide distractors via `other_options`, `wrong_options`, or
>   `options`; the loader shuffles everything automatically.
>
> See `scenario.example.yaml` for a complete example scenario.

### Developing / adjusting

- Edit `scenario.yaml`/`scenario.json` and restart or `POST /api/reset` to reload.
- Telegram/web copy lives in `texts.py`; projector templates live in `app/templates`.
- Scoring is applied only on phase transitions inside `web.advance`; avoid recomputing elsewhere.
- Keep user-provided text HTML-safe; the templates and bot handlers already escape content.

---

## Description rendering (plain text vs HTML)

`description` (or `text`) is rendered on the public screen as **rich text**:

### Plain text (recommended for simple prompts)

- Separate paragraphs with a blank line.
- Use `- ` at the start of a line to create bullet lists.
- Plain-text descriptions are centered and have a narrower max width for readability.

### HTML (for media/layout)

HTML is sanitized (scripts/styles are removed), but basic layout tags like `div`, `p`, `ul`, `table`, `img`, `picture`
are supported.

**Rules of thumb**

- Avoid `width:45%/55%/40%/60%` on `<td>`; it often breaks responsive layout. Use layout classes instead.
- Prefer local wrappers for per-question spacing (`padding`) instead of changing global CSS.
- For images, keep `object-fit: contain` behavior by using `max-width:100%; height:auto` unless you explicitly want a
  full-height media slot.

**Template: text + image below (no tables)**

```html
<div style="padding:0 50px; align-self:center;">
  <p>Context / conditions:</p>
  <ul>
    <li>Item one</li>
    <li>Item two</li>
  </ul>
  <div style="margin-top:16px; text-align:center;">
    <img src="/media/example.jpg" alt="Example" loading="lazy" style="max-width:100%; height:auto;">
  </div>
</div>
```

**Template: two columns (table, 1-row layout)**

Use a 1-row table as the top-level description element and add one of these classes:

- `layout-split-50` (50/50)
- `layout-split-33-67` (text 1/3, media 2/3)
- `layout-split-40-60` (text 40%, media 60%)

```html
<table class="layout-split-33-67" style="width:100%; border-collapse:collapse;">
  <tr>
    <td style="vertical-align:middle; padding-left:60px; padding-right:20px; align-self:center;">
      <p>Text goes here...</p>
    </td>
    <td style="vertical-align:middle; text-align:center;">
      <div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center;">
        <img src="/media/example.jpg" alt="Example" loading="lazy" style="width:100%; height:100%; object-fit:contain;">
      </div>
    </td>
  </tr>
</table>
```

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

Design tokens and component styles live in `app/static` as `tokens.css`, `base.css`, `leaderboard.css`, `ideas.css` and
`components.css`.

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
