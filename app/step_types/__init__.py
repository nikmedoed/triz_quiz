"""Registry of step types with hooks for public screen and Telegram."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import GlobalState, Step, User

ContextBuilder = Callable[[AsyncSession, Step, GlobalState, Dict[str, Any]], Awaitable[None]]
TotalPhasesFn = Callable[[AsyncSession, Step], Awaitable[int]]
PhaseHook = Callable[[AsyncSession, Step, int], Awaitable[None]]
ScenarioLoader = Callable[[AsyncSession, Callable[..., Step], Dict[str, Any]], Awaitable[None]]
BotPromptBuilder = Callable[[User, Step, int], Awaitable[list[tuple[str, dict]]]]
MessageHandler = Callable[[Message, Bot, AsyncSession, User, GlobalState, Step], Awaitable[bool]]
CallbackHandler = Callable[[CallbackQuery, Bot, AsyncSession, User, GlobalState, Step, str], Awaitable[None]]
PromptPreHook = Callable[[Bot, User, Step, int], Awaitable[None]]
PromptPostHook = Callable[[Bot, User, Step, int, Message], Awaitable[None]]


@dataclass
class StepType:
    """Metadata and helpers for a quiz step type."""

    build_context: ContextBuilder
    total_phases: TotalPhasesFn
    on_enter_phase: Optional[PhaseHook] = None
    load_item: Optional[ScenarioLoader] = None
    build_bot_prompts: Optional[BotPromptBuilder] = None
    on_text: Optional[MessageHandler] = None
    callback_prefix: Optional[str] = None
    on_callback: Optional[CallbackHandler] = None
    callback_error: str = texts.NOT_VOTE_PHASE
    on_prompt_pre: Optional[PromptPreHook] = None
    on_prompt_post: Optional[PromptPostHook] = None


STEP_TYPES: Dict[str, StepType] = {}


def register(name: str, step_type: StepType) -> None:
    STEP_TYPES[name] = step_type


# Import step modules to populate registry
from . import registration, open_step, quiz, leaderboard, multi  # noqa: E402,F401
