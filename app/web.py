# FastAPI web (public screen), WebSockets broadcasting, block/phase transitions
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Set

from aiogram import Bot
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.db import get_session
from app.models import User, Step, StepOption, GlobalState, Idea, IdeaVote, McqAnswer
from app.scoring import add_vote_points, add_mcq_points, get_leaderboard_users
from app.settings import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def humanize_seconds(sec: int) -> str:
    m, s = divmod(sec, 60)
    return f"{m} мин {s} с" if m else f"{s} с"


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
    template = f"stages/{step.type}.jinja2"
    return templates.TemplateResponse(template, {"request": request, "texts": texts, **ctx})


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    logging.info("Ссылка сброса: /reset")
    return templates.TemplateResponse("reset.jinja2", {"request": request, "stage_title": "Сброс"})


@router.post("/reset")
async def reset_confirm(request: Request, session: AsyncSession = Depends(get_session)):
    await api_reset(session, broadcast=False)
    resp = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    asyncio.create_task(hub.broadcast({"type": "reload"}))
    return resp


@router.post("/api/reset")
async def api_reset(session: AsyncSession = Depends(get_session), broadcast: bool = True):
    # wipe dynamic data
    for model in [IdeaVote, Idea, McqAnswer, User]:
        await session.execute(delete(model))
    # restore first step
    first = await session.scalar(select(Step.id).order_by(Step.order_index.asc()))
    gs = await session.get(GlobalState, 1)
    gs.current_step_id = first
    now = datetime.utcnow()
    gs.step_started_at = now
    gs.phase_started_at = now
    gs.phase = 0
    await session.commit()
    if broadcast:
        await hub.broadcast({"type": "reload"})
    return {"ok": True}


@router.websocket("/ws")
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


async def notify_all(session: AsyncSession):
    from app.bot import send_prompt
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    users = (await session.execute(select(User))).scalars().all()
    for u in users:
        try:
            await send_prompt(bot, u, step, gs.phase)
            await asyncio.sleep(settings.TELEGRAM_SEND_DELAY)
        except Exception:
            pass
    await bot.session.close()


async def advance(session: AsyncSession, forward: bool):
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)

    async def commit_and_notify():
        await session.commit()
        await notify_all(session)

    if forward:
        if step.type == "open":
            ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
            total_phases = 3 if ideas_count else 2
            if gs.phase + 1 < total_phases:
                gs.phase += 1
                gs.phase_started_at = datetime.utcnow()
                if ideas_count and gs.phase == 2:
                    await add_vote_points(session, step.id)
                await commit_and_notify()
            else:
                await move_to_block(session, step.order_index + 1)
                await commit_and_notify()
        elif step.type == "quiz":
            if gs.phase == 0:
                gs.phase = 1
                gs.phase_started_at = datetime.utcnow()
                await add_mcq_points(session, step)
                await commit_and_notify()
            else:
                await move_to_block(session, step.order_index + 1)
                await commit_and_notify()
        else:
            await move_to_block(session, step.order_index + 1)
            await commit_and_notify()
    else:
        if step.type in ("open", "quiz") and gs.phase > 0:
            gs.phase -= 1
            gs.phase_started_at = datetime.utcnow()
            await commit_and_notify()
        else:
            await move_to_block(session, step.order_index - 1, to_last_phase=True)
            await commit_and_notify()


async def move_to_block(session: AsyncSession, target_order_index: int, to_last_phase: bool = False):
    target = await session.scalar(select(Step).where(Step.order_index == target_order_index))
    if not target:
        return
    gs = await session.get(GlobalState, 1)
    gs.current_step_id = target.id
    now = datetime.utcnow()
    gs.step_started_at = now
    gs.phase_started_at = now
    # compute correct "last phase" depending on step type and existing data
    if to_last_phase and target.type == "open":
        ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == target.id))
        gs.phase = 2 if ideas_count else 1
    elif to_last_phase and target.type == "quiz":
        gs.phase = 1
    else:
        gs.phase = 0
    await session.commit()


async def build_public_context(session: AsyncSession, step: Step, gs: GlobalState):
    ctx = {
        "step": step,
        "phase": gs.phase,
        "since": gs.phase_started_at,
        "stage_title": "",
        "instruction": "",
        "timer_id": None,
        "timer_text": "",
        "timer_ms": 0,
        "status_mode": "",
        "status_current": 0,
        "status_total": 0,
        "status_last": "-",
        "show_reset": False,
        "content_class": "",
    }
    if step.type == "registration":
        users = (
            await session.execute(select(User).where(User.name != "").order_by(User.joined_at.asc()))).scalars().all()
        ctx.update(users=users, stage_title="Регистрация", show_reset=True)
    elif step.type == "open":
        rows = (
            await session.execute(
                select(Idea, User)
                .join(User, User.id == Idea.user_id)
                .where(Idea.step_id == step.id)
                .order_by(Idea.submitted_at.asc())
            )
        ).all()
        ideas = []
        for idea, author in rows:
            idea.author = author
            ideas.append(idea)
        if ideas:
            for i in ideas:
                delta = int((i.submitted_at - gs.step_started_at).total_seconds())
                i.delay_text = humanize_seconds(max(0, delta))
        ctx.update(ideas=ideas)
        suffix = ''
        if gs.phase == 1:
            suffix = ' — ' + texts.STAGE_VOTING_SUFFIX
            ctx.update(content_class='ideas-page')
        elif gs.phase == 2:
            suffix = ' — ' + texts.STAGE_RESULTS_SUFFIX
            ctx.update(content_class='ideas-page')
        ctx.update(stage_title=texts.TITLE_OPEN + suffix)
        if gs.phase == 0:
            total_users = await session.scalar(select(func.count(User.id)).where(User.name != ""))
            last_at = await session.scalar(select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id))
            last_ago_s = None
            if last_at:
                last_ago_s = int((datetime.utcnow() - last_at).total_seconds())
            ctx.update(
                total_users=int(total_users or 0),
                last_answer_ago_s=last_ago_s,
                timer_id="ideaTimer",
                timer_text="05:00",
                timer_ms=5 * 60 * 1000,
                status_mode="answers",
                status_current=len(ideas),
                status_total=int(total_users or 0),
                status_last=last_ago_s if last_ago_s is not None else "-",
                instruction="Отправляйте идеи боту. Здесь они пока не видны.",
            )
        if gs.phase == 1 and ideas:  # vote
            voters = (
                await session.execute(
                    select(IdeaVote.voter_id)
                    .where(IdeaVote.step_id == step.id)
                    .group_by(IdeaVote.voter_id)
                )
            ).all()
            last_vote_at = await session.scalar(
                select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id)
            )
            total_users = await session.scalar(
                select(func.count(User.id)).where(User.name != "")
            )
            last_vote_ago_s = None
            if last_vote_at:
                last_vote_ago_s = int((datetime.utcnow() - last_vote_at).total_seconds())
            ctx.update(
                voters_count=len(voters),
                last_vote_ago_s=last_vote_ago_s,
                timer_id="voteTimer",
                timer_text="01:00",
                timer_ms=60 * 1000,
                status_mode="votes",
                status_current=len(voters),
                status_total=int(total_users or 0),
                status_last=last_vote_ago_s if last_vote_ago_s is not None else "-",
            )
        if gs.phase == 2:  # reveal
            # map idea_id -> [User]
            voters_map = {}
            for idea in ideas:
                rows = (
                    await session.execute(
                        select(User)
                        .join(IdeaVote, IdeaVote.voter_id == User.id)
                        .where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea.id)
                    )
                ).scalars().all()
                voters_map[idea.id] = rows
            ideas.sort(key=lambda i: len(voters_map.get(i.id, [])), reverse=True)
            ctx.update(voters_map=voters_map, ideas=ideas)
    elif step.type == "quiz":
        options = (
            await session.execute(
                select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx)
            )
        ).scalars().all()
        ctx.update(options=options, stage_title="Выбери верный" if gs.phase == 0 else "Выбери верный — результаты")
        if gs.phase == 0:
            total_users = await session.scalar(select(func.count(User.id)).where(User.name != ""))
            answers_count = await session.scalar(
                select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id)
            )
            last_at = await session.scalar(
                select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
            )
            last_answer_ago_s = None
            if last_at:
                last_answer_ago_s = int((datetime.utcnow() - last_at).total_seconds())
            ctx.update(
                total_users=int(total_users or 0),
                answers_count=int(answers_count or 0),
                last_answer_ago_s=last_answer_ago_s,
                status_mode="answers",
                status_current=int(answers_count or 0),
                status_total=int(total_users or 0),
                status_last=last_answer_ago_s if last_answer_ago_s is not None else "-",
                instruction="Участники выбирают вариант в боте.",
                timer_id="quizTimer",
                timer_text="01:00",
                timer_ms=60 * 1000,
            )
        if gs.phase == 1:
            counts = []
            avatars_map = []
            names_map = {}
            for opt in options:
                n = await session.scalar(
                    select(func.count(McqAnswer.id)).where(
                        McqAnswer.step_id == step.id, McqAnswer.choice_idx == opt.idx
                    )
                )
                counts.append(int(n or 0))
                users = (
                    await session.execute(
                        select(User)
                        .join(McqAnswer, McqAnswer.user_id == User.id)
                        .where(McqAnswer.step_id == step.id, McqAnswer.choice_idx == opt.idx)
                    )
                ).scalars().all()
                avatars_map.append([u.id for u in users])
                for u in users:
                    names_map[str(u.id)] = u.name
            total = sum(counts)
            percents = [round((c / total) * 100) if total else 0 for c in counts]
            ctx.update(
                counts=counts,
                percents=percents,
                correct=step.correct_index,
                avatars_map=avatars_map,
                names_map=names_map,
                content_class="mcq-results",
            )
    elif step.type == "leaderboard":
        users = await get_leaderboard_users(session)
        ctx.update(
            users=users,
            stage_title="Результаты",
            show_reset=True,
            show_next=False,
            content_class="leaderboard-page",
        )
    return ctx
