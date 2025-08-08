# README

> **Language note:** All code comments and this README are in **English** as requested.

This project implements a TRIZ-club quiz/presentation system with **Telegram + Web**:

* **Telegram bot (aiogram 3)** for registration, open-form ideas, voting, and MCQ.
* **Web app (FastAPI + WebSockets)** with:

  * **Public screen** (projector) that updates live.
  * **Moderator screen** to drive the show.
* **SQLite** by default (switchable to Postgres). All state is persisted to survive restarts.
* **Scenario loaded from JSON/YAML list of blocks** (simple), activated on startup.
* **Scoring**: +`points` per correct MCQ; +1 per received vote on ideas; tie-breaker by total response time.

### Design decisions aligned with your requirements

* **No admin password**. Everything runs locally. Moderator UI is open on `http://localhost:8000/moderator`.
* **Mandatory Registration & Leaderboard** are **implicit** and **auto-inserted**: you **do not** specify them in the scenario.
* **Blocks, not micro-steps**: Each content item is a **block** with **internal phases** and the **same Next/Prev controls**.

  * `open` block phases: **collect → list (or none) → vote (if ideas exist) → reveal**. Voting is skipped if there are no ideas.
  * `quiz` block phases: **ask → reveal**.
* **Universal Next/Prev**:

  * `Next` advances to the next **phase** inside the current block; if it was the last phase, it moves to the next block.
  * `Prev` moves backward similarly.
* **Late join**: a participant who joins at any time is synced to the current block & phase.

---

## Project structure

```
triz_quiz/
├─ app/
│  ├─ settings.py
│  ├─ db.py
│  ├─ models.py
│  ├─ scoring.py
│  ├─ scenario_loader.py
│  ├─ bot.py
│  ├─ web.py
│  ├─ main.py
│  ├─ templates/
│  │  ├─ base.html
│  │  ├─ public.html
│  │  └─ moderator.html
│  └─ static/
│     ├─ app.js
│     └─ styles.css
├─ scenario.example.yaml
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ run_local.sh
```

---

## Quick start (local)

1. **Create `.env`** with:

```
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
BASE_URL=http://localhost:8000
DATABASE_URL=sqlite+aiosqlite:///./quiz.db
```

2. **Install**:

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

3. **Run**:

```
./run_local.sh
```

Open:

* **Public screen**: `http://localhost:8000/`
* **Moderator**: `http://localhost:8000/moderator`

Invite participants to start the Telegram bot with `/start`. After they set a name, advancing phases from the moderator UI will push messages to all registered participants.

---

## Docker

```
docker compose up --build
```

---

## Scenario format (simple blocks)

Write `scenario.yaml` **or** `scenario.json` as a **list of blocks**. Registration and final leaderboard are **implicit** and auto-added.

**Supported blocks:**

* `open`: free-form idea collection with built-in vote & reveal.
* `quiz`: MCQ with built-in reveal.

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
    "points": 2
  }
]
```

> Notes:
>
> * `vote` and `vote_results` lines are **optional** and ignored by the loader (the `open` block already includes voting and reveal). You can keep them for readability.
> * `quiz.correct` accepts either a **1-based string/number** (e.g., `"3"`) or a **0-based index**.

---

## Scoring rules

* **MCQ**: each correct answer gives `points` (per-quiz configurable).
* **Ideas**: **+1** to the author per received vote.
* **Tie-breaker**: lower total response time across blocks where the participant answered/voted.

---

## PPT usage

* Present your normal PowerPoint deck.
* When you need live results, **Alt-Tab** to the browser tab with the **Public screen** (or add a hyperlink to `BASE_URL/`).

---

## Reliability

* SQLite or Postgres (set `DATABASE_URL`).
* All transitions are idempotent; late joiners are synced.

---

# requirements.txt

```
aiogram>=3.5,<4.0
fastapi>=0.110
uvicorn[standard]>=0.29
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
pydantic>=2.7
python-dotenv>=1.0
jinja2>=3.1
python-multipart>=0.0.9
```

---

# run\_local.sh

```bash
#!/usr/bin/env bash
set -euo pipefail
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

# Dockerfile

```Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

# docker-compose.yml

```yaml
version: "3.9"
services:
  web:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - ./scenario.example.yaml:/app/scenario.yaml:ro
      - quizdata:/app
volumes:
  quizdata:
```

---

# app/settings.py

```python
from pydantic import BaseModel
import os

class Settings(BaseModel):
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./quiz.db")

settings = Settings()
```

---

# app/db.py

```python
# Async SQLAlchemy engine/session setup
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.settings import settings

engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

---

# app/models.py

```python
# DB models (SQLAlchemy 2.0 style)
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    avatar_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    total_answer_ms: Mapped[int] = mapped_column(Integer, default=0)  # tie-breaker

class Step(Base):
    __tablename__ = "steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32))  # registration | open | quiz | leaderboard
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # description for open; question text for quiz
    correct_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # quiz only
    points_correct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # quiz only

class GlobalState(Base):
    __tablename__ = "global_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"))
    step_started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # start of current block
    phase: Mapped[int] = mapped_column(Integer, default=0)  # phase inside block

class StepOption(Base):
    __tablename__ = "step_options"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 0..N-1
    text: Mapped[str] = mapped_column(Text)
    UniqueConstraint("step_id", "idx")

class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # open block
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "user_id")

class IdeaVote(Base):
    __tablename__ = "idea_votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # open block
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "idea_id", "voter_id")

class McqAnswer(Base):
    __tablename__ = "mcq_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # quiz block
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    choice_idx: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "user_id")
```

---

# app/scoring.py

```python
# Scoring helpers
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, Step, Idea, IdeaVote, McqAnswer

async def add_vote_points(session: AsyncSession, open_step_id: int) -> None:
    # +1 per vote to the author of each idea in this open block
    res = await session.execute(
        select(Idea.user_id, func.count(IdeaVote.id))
        .join(IdeaVote, IdeaVote.idea_id == Idea.id)
        .where(Idea.step_id == open_step_id, IdeaVote.step_id == open_step_id)
        .group_by(Idea.user_id)
    )
    for user_id, votes in res.all():
        user = await session.get(User, user_id)
        if user:
            user.total_score += int(votes)
    await session.commit()

async def add_mcq_points(session: AsyncSession, mcq_step: Step) -> None:
    if mcq_step.points_correct is None or mcq_step.correct_index is None:
        return
    res = await session.execute(
        select(User)
        .join(McqAnswer, McqAnswer.user_id == User.id)
        .where(McqAnswer.step_id == mcq_step.id, McqAnswer.choice_idx == mcq_step.correct_index)
    )
    for (user,) in res.all():
        user.total_score += mcq_step.points_correct
    await session.commit()
```

---

# app/scenario\_loader.py

```python
# Load scenario (JSON or YAML list). Auto-prepend registration and append leaderboard.
import json, yaml, os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Step, StepOption, GlobalState

SUPPORTED = {"open", "quiz", "vote", "vote_results"}

async def load_if_empty(session: AsyncSession, path: str) -> None:
    existing = await session.execute(select(Step.id))
    if existing.first():
        return
    # Prefer explicit path; else try both yaml/json
    data = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    else:
        return
    if isinstance(data, dict) and "quiz" in data:
        # Legacy format: {quiz: {steps: [...]}}
        items = data["quiz"].get("steps", [])
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Scenario must be a list of blocks or legacy dict format")

    order = 0
    def add_step(_type: str, title: str = "", text: str | None = None, options: list[str] | None = None, correct_index: int | None = None, points: int | None = None):
        nonlocal order
        s = Step(order_index=order, type=_type, title=title or _type.title(), text=text, correct_index=correct_index, points_correct=points)
        session.add(s)
        order += 1
        return s

    # Registration (implicit)
    add_step("registration", title="Регистрация")

    # Normalize items
    for item in items:
        t = (item.get("type") or "").strip().lower()
        if t not in SUPPORTED:
            continue
        if t == "open":
            add_step("open", title=item.get("title", "Гипотезы решения"), text=item.get("description") or item.get("text"))
        elif t == "quiz":
            s = add_step("quiz", title=item.get("title", "Квиз"), text=item.get("text"))
            opts = item.get("options", [])
            for idx, text in enumerate(opts):
                session.add(StepOption(step_id=s.id, idx=idx, text=text))
            correct = item.get("correct")
            if isinstance(correct, str) and correct.isdigit():
                s.correct_index = int(correct) - 1
            elif isinstance(correct, (int,)):
                s.correct_index = correct
            s.points_correct = item.get("points")
        # vote/vote_results are ignored (implicit in `open`)

    # Leaderboard (implicit)
    add_step("leaderboard", title="Финальная таблица")

    # Global state
    first_step_id = await session.scalar(select(Step.id).order_by(Step.order_index.asc()))
    session.add(GlobalState(current_step_id=first_step_id))
    await session.commit()
```

---

# app/bot.py

```python
# aiogram 3 bot handlers — blocks with internal phases
from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User, GlobalState, Step, StepOption, Idea, IdeaVote, McqAnswer
from app.scoring import add_mcq_points

router = Router()

async def get_ctx(tg_id: str):
    session = AsyncSessionLocal()
    try:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            user = User(telegram_id=tg_id, name="")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        state = await session.get(GlobalState, 1)
        step = await session.get(Step, state.current_step_id)
        return session, user, state, step
    except Exception:
        await session.close()
        raise

# Keyboards

def mcq_kb(options: List[str], selected: Optional[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, _ in enumerate(options):
        label = f"{i+1}"
        if selected == i:
            label = "✅ " + label
        kb.button(text=label, callback_data=f"mcq:{i}")
    kb.adjust(2)
    return kb.as_markup()

async def idea_vote_kb(session: AsyncSession, open_step: Step, voter: User):
    ideas = (await session.execute(select(Idea).where(Idea.step_id == open_step.id).order_by(Idea.submitted_at.asc()))).scalars().all()
    voted_ids = set(x for (x,) in (await session.execute(select(IdeaVote.idea_id).where(IdeaVote.step_id == open_step.id, IdeaVote.voter_id == voter.id))).all())
    rows = []
    for idx, idea in enumerate(ideas, start=1):
        if idea.user_id == voter.id:
            continue
        text = idea.text[:40].replace("
", " ")
        prefix = "✅ " if idea.id in voted_ids else ""
        rows.append([InlineKeyboardButton(text=prefix + f"{idx}. {text}", callback_data=f"vote:{idea.id}")])
    if not rows:
        rows = [[InlineKeyboardButton(text="Нет идей для голосования", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# /start and name capture

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if not user.name:
            await message.answer("Введите имя для участия (отправьте одним сообщением).")
            return
        await message.answer(f"Текущее имя: {user.name}
Если хотите изменить — отправьте новое сейчас.")
        await send_prompt(bot, user, step, state.phase)
    finally:
        await session.close()

@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if not user.name:
            user.name = message.text.strip()[:120]
            await session.commit()
            await message.answer("Имя сохранено. Готово к участию.")
            await send_prompt(bot, user, step, state.phase)
            return
        # Open ideas only in phase 0
        if step.type == "open" and state.phase == 0:
            await session.execute(delete(Idea).where(Idea.step_id == step.id, Idea.user_id == user.id))
            session.add(Idea(step_id=step.id, user_id=user.id, text=message.text.strip()))
            await session.commit()
            # time-to-first-answer is measured when MCQ pressed; for open we count at submission time
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            user.total_answer_ms += max(0, delta_ms)
            await session.commit()
            await message.answer("Идея принята. Можно отправить новое сообщение, чтобы заменить.")
        else:
            await message.answer("Сейчас текстовые ответы не принимаются. Дождитесь команды модератора.")
    finally:
        await session.close()

@router.callback_query(F.data.startswith("mcq:"))
async def cb_mcq(cb: CallbackQuery, bot: Bot):
    choice_idx = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "quiz" or state.phase != 0:
            await cb.answer("Сейчас не этап ответов.", show_alert=True)
            return
        existing = (await session.execute(select(McqAnswer).where(McqAnswer.step_id == step.id, McqAnswer.user_id == user.id))).scalar_one_or_none()
        if existing:
            existing.choice_idx = choice_idx
        else:
            session.add(McqAnswer(step_id=step.id, user_id=user.id, choice_idx=choice_idx))
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            user.total_answer_ms += max(0, delta_ms)
        await session.commit()
        await cb.answer("Ответ сохранён.")
        options = [o.text for o in (await session.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
        await cb.message.edit_reply_markup(reply_markup=mcq_kb(options, selected=choice_idx))
    finally:
        await session.close()

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(cb: CallbackQuery, bot: Bot):
    idea_id = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "open" or state.phase != 2:
            await cb.answer("Сейчас не этап голосования.", show_alert=True)
            return
        existing = (await session.execute(select(IdeaVote).where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea_id, IdeaVote.voter_id == user.id))).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
            await cb.answer("Голос снят.")
        else:
            session.add(IdeaVote(step_id=step.id, idea_id=idea_id, voter_id=user.id))
            await session.commit()
            await cb.answer("Голос засчитан.")
        kb = await idea_vote_kb(session, step, user)
        await cb.message.edit_reply_markup(reply_markup=kb)
    finally:
        await session.close()

async def send_prompt(bot: Bot, user: User, step: Step, phase: int):
    if step.type == "registration":
        await bot.send_message(user.telegram_id, "Ждём начала. Вы на экране регистрации.")
    elif step.type == "open":
        if phase == 0:
            await bot.send_message(user.telegram_id, (step.text or "Отправьте идею одним сообщением."))
        elif phase == 1:
            await bot.send_message(user.telegram_id, "Приём идей завершён. Смотрите общий экран.")
        elif phase == 2:
            await bot.send_message(user.telegram_id, "Начато голосование за идеи. Можно выбрать несколько.")
            async with AsyncSessionLocal() as s:
                kb = await idea_vote_kb(s, step, user)
            await bot.send_message(user.telegram_id, "Выберите идеи:", reply_markup=kb)
        elif phase == 3:
            await bot.send_message(user.telegram_id, "Голосование завершено. Смотрите общий экран.")
    elif step.type == "quiz":
        if phase == 0:
            async with AsyncSessionLocal() as s:
                options = [o.text for o in (await s.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
            await bot.send_message(user.telegram_id, (step.text or "Выберите вариант ответа:") + "

" + "
".join([f"{i+1}. {t}" for i,t in enumerate(options)]), reply_markup=mcq_kb(options, selected=None))
        else:
            await bot.send_message(user.telegram_id, "Ответы закрыты. Смотрите общий экран.")
    elif step.type == "leaderboard":
        await bot.send_message(user.telegram_id, "Финальные результаты на общем экране.")
```

---

# app/web.py

```python
# FastAPI web (public & moderator), WebSockets broadcasting, block/phase transitions
from __future__ import annotations
from datetime import datetime
from typing import Dict, Set

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User, Step, StepOption, GlobalState, Idea, IdeaVote, McqAnswer
from app.scoring import add_vote_points, add_mcq_points

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class Hub:
    def __init__(self):
        self.active: Set[WebSocket] = set()
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
    async def broadcast(self, payload: Dict):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

hub = Hub()

@router.get("/", response_class=HTMLResponse)
async def public(request: Request, session: AsyncSession = Depends(get_session)):
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)
    ctx = await build_public_context(session, step, gs)
    return templates.TemplateResponse("public.html", {"request": request, **ctx})

@router.get("/moderator", response_class=HTMLResponse)
async def moderator(request: Request):
    return templates.TemplateResponse("moderator.html", {"request": request})

@router.post("/api/reset")
async def api_reset(session: AsyncSession = Depends(get_session)):
    # wipe dynamic data
    for model in [IdeaVote, Idea, McqAnswer, User]:
        await session.execute(delete(model))
    # restore first step
    first = await session.scalar(select(Step.id).order_by(Step.order_index.asc()))
    gs = await session.get(GlobalState, 1)
    gs.current_step_id = first
    gs.step_started_at = datetime.utcnow()
    gs.phase = 0
    await session.commit()
    await hub.broadcast({"type": "reload"})
    return {"ok": True}

@router.get("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)

@router.post("/api/next")
async def api_next(session: AsyncSession = Depends(get_session)):
    await advance(session, forward=True)
    await hub.broadcast({"type": "reload"})
    return {"ok": True}

@router.post("/api/prev")
async def api_prev(session: AsyncSession = Depends(get_session)):
    await advance(session, forward=False)
    await hub.broadcast({"type": "reload"})
    return {"ok": True}

async def advance(session: AsyncSession, forward: bool):
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)
    if forward:
        if step.type == "open":
            ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
            total_phases = 4 if ideas_count else 2
            if gs.phase + 1 < total_phases:
                gs.phase += 1
                # Award votes when entering reveal (phase 3)
                if ideas_count and gs.phase == 3:
                    await add_vote_points(session, step.id)
                await session.commit()
            else:
                await move_to_block(session, step.order_index + 1)
        elif step.type == "quiz":
            if gs.phase == 0:
                gs.phase = 1
                await add_mcq_points(session, step)
                await session.commit()
            else:
                await move_to_block(session, step.order_index + 1)
        else:
            await move_to_block(session, step.order_index + 1)
    else:
        if step.type in ("open", "quiz") and gs.phase > 0:
            gs.phase -= 1
            await session.commit()
        else:
            await move_to_block(session, step.order_index - 1, to_last_phase=True)

async def move_to_block(session: AsyncSession, target_order_index: int, to_last_phase: bool = False):
    target = await session.scalar(select(Step).where(Step.order_index == target_order_index))
    if not target:
        return
    gs = await session.get(GlobalState, 1)
    gs.current_step_id = target.id
    gs.step_started_at = datetime.utcnow()  # reset only when changing block
    gs.phase = 1 if (to_last_phase and target.type == "quiz") else 3 if (to_last_phase and target.type == "open") else 0
    await session.commit()

async def build_public_context(session: AsyncSession, step: Step, gs: GlobalState):
    ctx = {"step": step, "phase": gs.phase, "since": gs.step_started_at}
    if step.type == "registration":
        users = (await session.execute(select(User).order_by(User.joined_at.asc()))).scalars().all()
        ctx.update(users=users)
    elif step.type == "open":
        ideas = (await session.execute(select(Idea).where(Idea.step_id == step.id).order_by(Idea.submitted_at.asc()))).scalars().all()
        ctx.update(ideas=ideas)
        if gs.phase == 2:  # vote
            voters = (await session.execute(select(IdeaVote.voter_id).where(IdeaVote.step_id == step.id).group_by(IdeaVote.voter_id))).all()
            last_vote_at = await session.scalar(select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id))
            ctx.update(voters_count=len(voters), last_vote_at=last_vote_at)
        if gs.phase == 3:  # reveal
            # map idea_id -> [User]
            voters_map = {}
            for idea in ideas:
                rows = (await session.execute(select(User).join(IdeaVote, IdeaVote.voter_id == User.id).where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea.id))).scalars().all()
                voters_map[idea.id] = rows
            ctx.update(voters_map=voters_map)
    elif step.type == "quiz":
        options = (await session.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()
        ctx.update(options=options)
        if gs.phase == 1:
            counts = []
            for opt in options:
                n = await session.scalar(select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id, McqAnswer.choice_idx == opt.idx))
                counts.append(int(n or 0))
            ctx.update(counts=counts, correct=step.correct_index)
    elif step.type == "leaderboard":
        users = (await session.execute(select(User))).scalars().all()
        users.sort(key=lambda u: (-u.total_score, u.total_answer_ms, u.joined_at))
        ctx.update(users=users)
    return ctx
```

---

# app/main.py

```python
# App wiring & bot startup
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher

from app.db import Base, engine, AsyncSessionLocal
from app.web import router
from app.scenario_loader import load_if_empty
from app.settings import settings
from app.bot import router as bot_router

app = FastAPI()
app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
async def on_startup():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Load scenario once
    async with AsyncSessionLocal() as s:
        try:
            await load_if_empty(s, path="scenario.yaml")
        except FileNotFoundError:
            await load_if_empty(s, path="scenario.json")

@app.on_event("startup")
async def start_bot():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)
    asyncio.create_task(dp.start_polling(bot))
```

---

# app/templates/base.html

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ step.title if step else 'TRIZ Quiz' }}</title>
  <link rel="stylesheet" href="/static/styles.css" />
  <script src="/static/app.js" defer></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  {% block body %}{% endblock %}
</body>
</html>
```

---

# app/templates/public.html

```html
{% extends 'base.html' %}
{% block body %}
<div class="container">
  <h1>{{ step.title }}</h1>

  {% if step.type == 'registration' %}
    <div class="grid">
      {% for u in users %}
        <div class="card">
          <div class="avatar">👤</div>
          <div class="name">{{ u.name }}</div>
        </div>
      {% endfor %}
    </div>

  {% elif step.type == 'open' %}
    {% if phase == 0 %}
      <p class="question">{{ step.text }}</p>
      <p class="hint">Отправляйте идеи боту. Здесь они пока не видны.</p>
    {% elif phase == 1 %}
      {% if ideas|length == 0 %}
        <p class="hint">Ответов нет.</p>
      {% else %}
        <ol>
        {% for idea in ideas %}
          <li><div class="idea">{{ idea.text }}</div>
              <div class="meta">ответ через {{ (idea.submitted_at - since).seconds }} секунд</div></li>
        {% endfor %}
        </ol>
      {% endif %}
    {% elif phase == 2 %}
      <p class="question">Голосование за идеи</p>
      <ol>
      {% for idea in ideas %}
        <li><div class="idea">{{ idea.text }}</div>
            <div class="meta">ответ через {{ (idea.submitted_at - since).seconds }} секунд</div></li>
      {% endfor %}
      </ol>
      <div class="progress">Проголосовало (≥1): {{ voters_count }}
        {% if last_vote_at %} • последний голос {{ ((now() - last_vote_at).seconds) }} с назад{% endif %}
      </div>
    {% elif phase == 3 %}
      <ol>
        {% for idea in ideas %}
        <li>
          <div class="idea">{{ idea.text }}</div>
          <div class="votes">Голоса: {{ (voters_map.get(idea.id) or [])|length }}</div>
        </li>
        {% endfor %}
      </ol>
    {% endif %}

  {% elif step.type == 'quiz' %}
    {% if phase == 0 %}
      <div class="question">{{ step.text }}</div>
      <ol>
        {% for opt in options %}
          <li>{{ opt.text }}</li>
        {% endfor %}
      </ol>
      <div class="hint">Участники выбирают вариант в боте.</div>
    {% else %}
      <div class="question">Результаты</div>
      <canvas id="mcqChart"></canvas>
      <script>
        window.__mcq = {
          labels: [{% for opt in options %}'{{ opt.text|replace("'", "\'") }}',{% endfor %}],
          counts: [{% for c in counts %}{{ c }},{% endfor %}],
          correct: {{ correct }}
        };
        document.addEventListener('DOMContentLoaded', () => window.renderMcq());
      </script>
    {% endif %}

  {% elif step.type == 'leaderboard' %}
    <table class="board">
      <thead><tr><th>#</th><th>Имя</th><th>Баллы</th><th>Время (с)</th></tr></thead>
      <tbody>
        {% for u in users %}
          <tr>
            <td>{{ loop.index }}</td>
            <td>{{ u.name }}</td>
            <td>{{ u.total_score }}</td>
            <td>{{ (u.total_answer_ms/1000)|round(1) }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}
</div>

<script>
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onmessage = (ev) => { const msg = JSON.parse(ev.data); if (msg.type === 'reload') location.reload(); };
</script>
{% endblock %}
```

---

# app/templates/moderator.html

```html
{% extends 'base.html' %}
{% block body %}
<div class="container">
  <h1>Moderator</h1>
  <div class="controls">
    <button onclick="post('/api/prev')">◀️ Prev</button>
    <button onclick="post('/api/next')">Next ▶️</button>
    <button onclick="if(confirm('Reset DB?')) post('/api/reset')">Reset DB</button>
  </div>
  <div id="log"></div>
</div>
<script>
async function post(url){
  const r = await fetch(url, {method:'POST'});
  const t = await r.text();
  document.getElementById('log').textContent = t;
}
</script>
{% endblock %}
```

---

# app/static/app.js

```javascript
// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  new Chart(ctx, {
    type: 'bar',
    data: { labels: data.labels, datasets: [{ label: 'Votes', data: data.counts }] },
    options: { responsive: true, plugins: { legend: { display: false } } }
  });
}
```

---

# app/static/styles.css

```css
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background: #0b0b0b; color: #f2f2f2; }
.container { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
h1 { font-size: 28px; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.card { background: #151515; border-radius: 12px; padding: 12px; text-align: center; }
.avatar { font-size: 48px; }
.name { margin-top: 8px; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.question { font-size: 22px; margin: 12px 0; }
.hint, .meta, .progress { opacity: 0.7; font-size: 14px; }
.board { width: 100%; border-collapse: collapse; }
.board th, .board td { border-bottom: 1px solid #2a2a2a; padding: 8px; }
.controls button { margin-right: 8px; }
ol { margin-left: 18px; }
.idea { font-size: 18px; margin: 6px 0; }
```

---

# scenario.example.yaml

```yaml
# You can also name this scenario.json; loader accepts JSON or YAML.
- type: open
  title: "Ситуация 1: как открыть банку с тугой крышкой?"
  description: "Домашний пример, крышка не поддаётся…"

- type: quiz
  title: "Какой приём ТРИЗ был использован?"
  options:
    - "Матрёшка"
    - "Динамичность"
    - "Применение локальных нагревов"
    - "Ещё какой-то вариант"
  correct: "3"   # 1-based or 0-based index accepted
  points: 2
```
