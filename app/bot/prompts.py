from __future__ import annotations

from aiogram import Bot

from app.models import Step, User
from app.step_types import STEP_TYPES


async def build_prompt_messages(user: User, step: Step, phase: int):
    handler = STEP_TYPES.get(step.type)
    if handler and handler.build_bot_prompts:
        return await handler.build_bot_prompts(user, step, phase)
    return []


async def send_prompt(
        bot: Bot, user: User, step: Step, phase: int, prefix: str | None = None
):
    handler = STEP_TYPES.get(step.type)
    if handler and handler.on_prompt_pre:
        await handler.on_prompt_pre(bot, user, step, phase)
    msgs = await build_prompt_messages(user, step, phase)
    if prefix:
        if msgs:
            text, kwargs = msgs[0]
            sep = "\n\n" if text else ""
            msgs[0] = (f"{prefix}{sep}{text}", kwargs)
        else:
            msgs.insert(0, (prefix, {}))
    for text, kwargs in msgs:
        msg = await bot.send_message(user.id, text, **kwargs)
        if handler and handler.on_prompt_post:
            await handler.on_prompt_post(bot, user, step, phase, msg)
