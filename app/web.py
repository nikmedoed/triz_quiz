"""FastAPI routes for public screen and moderator actions."""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.rich_text import format_rich_text
from app.db import get_session
from app.hub import hub
from app.models import (
    User,
    Step,
    StepOption,
    GlobalState,
    Idea,
    IdeaVote,
    McqAnswer,
    MultiAnswer,
    SequenceAnswer,
)
from app.public_context import build_public_context, format_mmss
from app.scenario_loader import load_if_empty, load_preview_steps
from app.state import advance

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["rich_text"] = format_rich_text


@router.get("/", response_class=HTMLResponse)
async def public(request: Request, session: AsyncSession = Depends(get_session)):
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)
    ctx = await build_public_context(session, step, gs)
    template = f"stages/{step.type}.jinja2"
    return templates.TemplateResponse(template, {"request": request, "texts": texts, **ctx})


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    logging.info("Reset link accessed: /reset")
    return templates.TemplateResponse(
        "reset.jinja2",
        {
            "request": request,
            "stage_title": "Сброс",
            "texts": texts,
            "show_next": False,
            "disable_ws": True,
        },
    )


@router.post("/reset")
async def reset_confirm(request: Request, session: AsyncSession = Depends(get_session)):
    await api_reset(session, broadcast=False)
    resp = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    asyncio.create_task(hub.broadcast({"type": "reload"}))
    return resp


@router.post("/api/reset")
async def api_reset(session: AsyncSession = Depends(get_session), broadcast: bool = True):
    for model in [
        IdeaVote,
        Idea,
        McqAnswer,
        MultiAnswer,
        SequenceAnswer,
        User,
        StepOption,
        Step,
        GlobalState,
    ]:
        await session.execute(delete(model))
    await session.commit()

    if os.path.exists("scenario.yaml"):
        await load_if_empty(session, path="scenario.yaml")
    elif os.path.exists("scenario.json"):
        await load_if_empty(session, path="scenario.json")

    if broadcast:
        await hub.broadcast({"type": "reload"})
    return {"ok": True}


@router.get("/preview", response_class=HTMLResponse)
async def preview(request: Request, idx: int = 0):
    steps = load_preview_steps()
    total = len(steps)
    if total == 0:
        return templates.TemplateResponse(
            "preview_empty.jinja2",
            {
                "request": request,
                "texts": texts,
                "stage_title": texts.PREVIEW_TITLE,
                "instruction": texts.PREVIEW_INSTRUCTION,
                "phase": 0,
                "step": None,
                "since": datetime.utcnow(),
                "show_next": False,
                "disable_ws": True,
                "preview_mode": True,
                "content_class": "",
            },
        )
    current_idx = max(0, min(idx, total - 1))
    preview_step = steps[current_idx]
    step = preview_step.step
    step.id = step.id or current_idx + 1
    options = preview_step.options
    if step.type == "sequence":
        shuffled = list(options)
        rng = random.Random(step.id)
        rng.shuffle(shuffled)
        options = shuffled
    template = f"stages/{step.type}.jinja2"
    prev_url = f"/preview?idx={current_idx - 1}" if current_idx > 0 else None
    next_url = f"/preview?idx={current_idx + 1}" if current_idx < total - 1 else None
    content_class = ""
    timer_id = None
    timer_ms = 0
    timer_text = ""
    instruction = texts.PREVIEW_INSTRUCTION
    if step.type == "open":
        timer_ms = step.timer_ms or 5 * 60 * 1000
        timer_id = "ideaTimer"
        timer_text = format_mmss(timer_ms)
        instruction = texts.OPEN_PUBLIC_INSTR
        if step.text:
            desc_len = len(step.text)
            content_class = "description-page"
            if desc_len > 500:
                content_class = content_class + " description-long"
    elif step.type in {"quiz", "multi"}:
        timer_ms = step.timer_ms or 60 * 1000
        timer_id = "quizTimer"
        timer_text = format_mmss(timer_ms)
        instruction = texts.QUIZ_PUBLIC_INSTR if step.type == "quiz" else texts.MULTI_PUBLIC_INSTR
    elif step.type == "sequence":
        timer_ms = step.timer_ms or 2 * 60 * 1000
        timer_id = "sequenceTimer"
        timer_text = format_mmss(timer_ms)
        instruction = texts.SEQUENCE_PUBLIC_INSTR
    if step.type == "open" and step.text:
        desc_len = len(step.text)
        content_class = "description-page"
        if desc_len > 500:
            content_class = content_class + " description-long"
    stage_title = {
        "open": texts.TITLE_OPEN,
        "quiz": "Выбери верный",
        "multi": "Выбери верные",
        "sequence": texts.TITLE_SEQUENCE,
        "registration": texts.TITLE_REGISTRATION,
    }.get(step.type, step.title or texts.PREVIEW_TITLE)
    ctx = {
        "request": request,
        "texts": texts,
        "step": step,
        "phase": 0,
        "options": options,
        "stage_title": stage_title,
        "instruction": instruction,
        "timer_id": timer_id,
        "timer_text": timer_text,
        "timer_ms": timer_ms,
        "status_mode": "",
        "status_current": 0,
        "status_total": 0,
        "status_last": "-",
        "show_reset": False,
        "show_next": False,
        "content_class": content_class,
        "since": datetime.utcnow(),
        "preview_mode": True,
        "preview_prev_url": prev_url,
        "preview_next_url": next_url,
        "disable_ws": True,
    }
    return templates.TemplateResponse(template, ctx)


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
