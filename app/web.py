"""FastAPI routes for public screen and moderator actions."""
from __future__ import annotations

import asyncio
import logging
import os

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
from app.public_context import build_public_context
from app.scenario_loader import load_if_empty
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
    return templates.TemplateResponse("reset.jinja2", {"request": request, "stage_title": "Сброс"})


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
