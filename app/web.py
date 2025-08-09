# FastAPI web (public & moderator), WebSockets broadcasting, block/phase transitions
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Dict, Set

import logging

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User, Step, StepOption, GlobalState, Idea, IdeaVote, McqAnswer
from app.scoring import add_vote_points, add_mcq_points
from aiogram import Bot
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
    return templates.TemplateResponse("public.html", {"request": request, **ctx})

@router.get("/moderator", response_class=HTMLResponse)
async def moderator(request: Request):
    return templates.TemplateResponse("moderator.html", {"request": request})


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    logging.info("Reset link: /reset")
    return templates.TemplateResponse("reset.html", {"request": request})


@router.post("/reset")
async def reset_confirm(request: Request, session: AsyncSession = Depends(get_session)):
    await api_reset(session)
    return RedirectResponse("/", status_code=302)

@router.post("/api/reset")
async def api_reset(session: AsyncSession = Depends(get_session)):
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
    ctx = {"step": step, "phase": gs.phase, "since": gs.phase_started_at}
    if step.type == "registration":
        users = (await session.execute(select(User).where(User.name != "").order_by(User.joined_at.asc()))).scalars().all()
        ctx.update(users=users)
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
        if gs.phase == 0:
            total_users = await session.scalar(select(func.count(User.id)).where(User.name != ""))
            last_at = await session.scalar(select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id))
            last_ago_s = None
            if last_at:
                last_ago_s = int((datetime.utcnow() - last_at).total_seconds())
            ctx.update(total_users=int(total_users or 0), last_answer_ago_s=last_ago_s)
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
            last_vote_ago_s = None
            if last_vote_at:
                last_vote_ago_s = int((datetime.utcnow() - last_vote_at).total_seconds())
            ctx.update(voters_count=len(voters), last_vote_ago_s=last_vote_ago_s)
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
            ctx.update(voters_map=voters_map)
    elif step.type == "quiz":
        options = (
            await session.execute(
                select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx)
            )
        ).scalars().all()
        ctx.update(options=options)
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
                avatars_map.append([u.telegram_id for u in users])
                for u in users:
                    names_map[str(u.telegram_id)] = u.name
            total = sum(counts)
            percents = [round((c / total) * 100) if total else 0 for c in counts]
            ctx.update(
                counts=counts,
                percents=percents,
                correct=step.correct_index,
                avatars_map=avatars_map,
                names_map=names_map,
            )
    elif step.type == "leaderboard":
        users = (await session.execute(select(User))).scalars().all()
        users.sort(key=lambda u: (-u.total_score, u.total_answer_ms, u.joined_at))
        ctx.update(users=users)
    return ctx
