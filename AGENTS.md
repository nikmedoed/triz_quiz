## Purpose

You are a coding agent for this repo. Your job: implement focused changes that help the TRIZ club quiz system run smoothly across **Telegram (aiogram 3)** and **Web (FastAPI + WebSockets)** without rewriting the architecture.

Keep changes minimal, safe, and production-ready.

---

## System map (quick)

* **app\_factory.py** — FastAPI app + lifespan: boot DB, load scenario (YAML/JSON), start aiogram polling.
* **bot.py** — Telegram flows (registration, open answers, voting, MCQ). Sends prompts per **current block + phase**.
* **web.py** — Public screen, state machine, `/api/next` transitions, `/api/reset`, `/ws` Hub broadcast.
* **models.py** — Async SQLAlchemy models; scoring/time fields; uniqueness constraints.
* **db.py** — Async engine/session + tiny in-place migration via `apply_migrations`.
* **scenario\_loader.py** — Loads list of blocks; auto-adds `registration` and `leaderboard`.
* **scoring.py** — MCQ points and idea-vote points; leaderboard ordering.
* **templates/** — Projector UI (Jinja2). **static/** — styles + Chart.js renderer.
* **texts.py** — User-facing Russian strings (bot messages and default titles).
* **settings.py** — .env configuration.

---

## Runtime model

* **Blocks**: `registration`, `open`, `quiz`, `leaderboard`.
* **Phases**:

  * `open`: `collect → vote (if any ideas) → reveal`
  * `quiz`: `ask → reveal`
* **Transitions**: moderator clicks **Next** (POST `/api/next`). Server updates state, scores when entering reveal, and broadcasts. Late joiners sync automatically.

---

## Ground rules

1. **English for code and docs.** Keep all code comments, commit text, and docs in English.
2. **Don’t overchange.** Touch only the files and functions you truly need. Preserve public behavior and data.
3. **Idempotency matters.** Ensure actions won’t double-award points or re-emit markup when reloaded.
4. **No blocking I/O.** Use async DB calls; avoid long CPU tasks in handlers.
5. **Escaping & safety.** HTML-escape any user text rendered into Telegram messages or templates.
6. **Texts live in `texts.py`.** Don’t hardcode Russian strings in handlers/templates.
7. **UI tokens.** Use existing CSS tokens and structures; avoid adding custom colors.
8. **No diff syntax in outputs.** When returning patches, show full replaced functions/blocks with clear file paths, not unified diffs.

---

## Common tasks (recipes)

### Add a quiz step

* Edit `scenario.yaml`/`.json` to add a block:

  * `type: quiz`, `title`, `options` (list), `correct` (1-based or 0-based), optional `points`.
* Loader maps options into `step_options`, sets `correct_index` and `points_correct`.
* Verify: run app, reach step, submit answers, press **Next** → reveal bar chart with correct highlighted and avatars under bars.

### Add an open (ideas) step

* Add `type: open` with `title` and `description` (or `text`).
* Flow: collect → (if any) vote → reveal; points are awarded on reveal (+1 per vote to the idea’s author).
* Verify progress widgets (answers count, last activity) update via WebSocket.

### Change scoring

* Update `scoring.py`. Keep scoring applied exactly once:

  * `open`: applied when moving to **reveal** (phase 2).
  * `quiz`: applied when moving from **ask** to **reveal** (phase 1).
* Never recompute on refresh; rely on transition hooks in `web.advance`.

### Add a DB field

* Add to `models.py`.
* Extend `apply_migrations` in `db.py` with a schema probe (e.g., `PRAGMA table_info`) and `ALTER TABLE ... ADD COLUMN ... DEFAULT`.
* Provide sensible defaults to avoid `NULL` surprises in templates/handlers.

### Adjust Telegram prompts or keyboards

* Define strings in `texts.py`.
* Build keyboards with `InlineKeyboardBuilder` (see `mcq_kb` / `idea_vote_kb`).
* When closing a vote, clear `reply_markup` for stored `last_vote_msg_id`.

### Avatars

* Primary source: Telegram profile photo.
* Fallback: ask user for emoji or sticker, save to `/avatars/{user.id}.png`.

---

## State machine contract

* `GlobalState`:

  * `current_step_id`, `step_started_at`, `phase_started_at`, `phase`.
* `advance(session, forward=True)`:

  * Decides next phase or block; applies scoring; commits; `notify_all`.
* `notify_all`:

  * Rebuilds per-user prompts based on current step/phase; throttled by `TELEGRAM_SEND_DELAY`.

---

## Quality checklist

Before you say a task is done:

* Start locally, walk through: **registration → open → vote → reveal → quiz → reveal → leaderboard**.
* Confirm:

  * Progress counters and “last activity” timers update live.
  * Scoring is correct and applied once.
  * Late joiner gets the correct current prompt.
  * No console errors from Chart.js or WebSocket.
* Code:

  * Async functions only perform async DB and bot calls.
  * Names and constants live in the right module (`texts.py`, not templates/handlers).
  * Unique constraints are respected (e.g., one MCQ answer per user per step).

---

## Local run quickstart

* `.env`:

  * `TELEGRAM_BOT_TOKEN`, `BASE_URL`, `DATABASE_URL`, `TELEGRAM_SEND_DELAY`.
* Install and run:

  * `python -m venv .venv && source .venv/bin/activate`
  * `pip install -r requirements.txt`
  * `./run_local.sh` or `docker compose up --build`
* Open `http://localhost:8000/`. Use `/reset` to wipe dynamic data.

---

## Return format for agent outputs

When you deliver changes:

* Provide a short summary of intent and impact.
* List touched files.
* Paste complete replacement **functions/blocks** or whole small files as needed (no `+`/`-` diffs).
* Include manual test steps and expected outcomes.
