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
    # вычисляем корректную «последнюю фазу» для open
    if to_last_phase and target.type == "open":
        ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == target.id))
        gs.phase = 3 if ideas_count else 1
    elif to_last_phase and target.type == "quiz":
        gs.phase = 1
    else:
        gs.phase = 0
    await session.commit()

async def build_public_context(session: AsyncSession, step: Step, gs: GlobalState):
    ctx = {"step": step, "phase": gs.phase, "since": gs.step_started_at}
    if step.type == "registration":
        users = (await session.execute(select(User).where(User.name != "").order_by(User.joined_at.asc()))).scalars().all()
        ctx.update(users=users)
    elif step.type == "open":
        ideas = (await session.execute(select(Idea).where(Idea.step_id == step.id).order_by(Idea.submitted_at.asc()))).scalars().all()
        ctx.update(ideas=ideas)
        if gs.phase == 2:  # vote
            voters = (await session.execute(select(IdeaVote.voter_id).where(IdeaVote.step_id == step.id).group_by(IdeaVote.voter_id))).all()
            last_vote_at = await session.scalar(select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id))
            last_vote_ago_s = None
            if last_vote_at:
                last_vote_ago_s = int((datetime.utcnow() - last_vote_at).total_seconds())
            ctx.update(voters_count=len(voters), last_vote_ago_s=last_vote_ago_s)
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
