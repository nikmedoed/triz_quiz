# aiogram 3 bot handlers — blocks with internal phases
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pathlib import Path
import random
from io import BytesIO

import requests
try:  # optional, may require system cairo library
    import cairosvg  # type: ignore
except Exception:  # pragma: no cover - fallback when cairo missing
    cairosvg = None
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Sticker
from aiogram.utils.keyboard import InlineKeyboardBuilder
from html import escape

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User, GlobalState, Step, StepOption, Idea, IdeaVote, McqAnswer
from app.scoring import add_mcq_points, get_leaderboard_users
from app.web import hub
from app.settings import settings
import app.texts as texts

router = Router()

AVATAR_SIZE = 640


def _gradient(size: int) -> Image.Image:
    """Create a colorful four-corner gradient image."""
    corners = [
        tuple(random.randint(0, 255) for _ in range(3)) for _ in range(4)
    ]  # tl, tr, bl, br
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        rx = x / (size - 1)
        for y in range(size):
            ry = y / (size - 1)
            top = [
                int(corners[0][i] * (1 - rx) + corners[1][i] * rx) for i in range(3)
            ]
            bottom = [
                int(corners[2][i] * (1 - rx) + corners[3][i] * rx) for i in range(3)
            ]
            r = int(top[0] * (1 - ry) + bottom[0] * ry)
            g = int(top[1] * (1 - ry) + bottom[1] * ry)
            b = int(top[2] * (1 - ry) + bottom[2] * ry)
            draw.point((x, y), fill=(r, g, b, 255))
    return img


def _emoji_avatar(path: Path, user: User, emoji: str) -> None:
    """Generate avatar with given emoji on colorful gradient background."""
    size = AVATAR_SIZE
    img = _gradient(size)
    draw = ImageDraw.Draw(img)

    codepoints = "-".join(f"{ord(c):x}" for c in emoji)
    emoji_size = int(size * 0.7)
    emoji_img = None

    if cairosvg:
        try:
            url_svg = f"https://twemoji.maxcdn.com/v/latest/svg/{codepoints}.svg"
            resp = requests.get(url_svg, timeout=10)
            resp.raise_for_status()
            png_bytes = cairosvg.svg2png(
                bytestring=resp.content,
                output_width=emoji_size,
                output_height=emoji_size,
            )
            emoji_img = Image.open(BytesIO(png_bytes)).convert("RGBA")
        except Exception:
            emoji_img = None

    if emoji_img is None:
        try:
            url_png = f"https://twemoji.maxcdn.com/v/latest/72x72/{codepoints}.png"
            resp = requests.get(url_png, timeout=10)
            resp.raise_for_status()
            emoji_img = Image.open(BytesIO(resp.content)).convert("RGBA")
            emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.LANCZOS)
        except Exception:
            emoji_img = None

    if emoji_img is None:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", emoji_size)
        except Exception:
            font = ImageFont.load_default()
        draw.text(
            (size / 2, size / 2),
            emoji,
            font=font,
            anchor="mm",
            embedded_color=True,
        )
    else:
        shadow = Image.new("RGBA", emoji_img.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 80), mask=emoji_img.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(4))
        x = (size - emoji_size) // 2
        y = (size - emoji_size) // 2
        img.paste(shadow, (x + 4, y + 4), shadow)
        img.paste(emoji_img, (x, y), emoji_img)

    img.save(path / f"{user.id}.png")


async def _sticker_avatar(bot: Bot, user: User, sticker: Sticker) -> None:
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    buf = BytesIO()
    await bot.download(sticker.file_id, destination=buf)
    buf.seek(0)
    try:
        img = Image.open(buf).convert("RGBA")
    except Exception:
        if sticker.thumbnail:
            buf = BytesIO()
            await bot.download(sticker.thumbnail.file_id, destination=buf)
            buf.seek(0)
            img = Image.open(buf).convert("RGBA")
        else:
            raise
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    size = AVATAR_SIZE
    max_size = int(size * 0.8)
    if sticker.is_animated or sticker.is_video:
        scale = max_size / max(img.width, img.height)
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)), Image.LANCZOS
        )
    else:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    background = _gradient(size)
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    background.alpha_composite(img, dest=(x, y))
    background.save(path / f"{user.id}.png")


async def save_avatar(bot: Bot, user: User) -> bool:
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    chat = await bot.get_chat(user.id)
    if chat.photo:
        buf = BytesIO()
        await bot.download(chat.photo.big_file_id, destination=buf)
        buf.seek(0)
        img = Image.open(buf)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.thumbnail((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        background = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
        x = (AVATAR_SIZE - img.width) // 2
        y = (AVATAR_SIZE - img.height) // 2
        background.alpha_composite(img, dest=(x, y))
        background.save(path / f"{user.id}.png")
        return True
    return False

async def get_ctx(tg_id: str):
    session = AsyncSessionLocal()
    try:
        user = (await session.execute(select(User).where(User.id == tg_id))).scalar_one_or_none()
        if not user:
            user = User(id=tg_id, name="")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            avatar = Path(settings.AVATAR_DIR) / f"{user.id}.png"
            if avatar.exists():
                avatar.unlink()
        state = await session.get(GlobalState, 1)
        step = await session.get(Step, state.current_step_id)
        return session, user, state, step
    except Exception:
        await session.close()
        raise

# Keyboards

def mcq_kb(options: List[str], selected: Optional[int]) -> InlineKeyboardMarkup:
    """Inline keyboard with options as button labels."""
    kb = InlineKeyboardBuilder()
    for i, text in enumerate(options):
        label = f"{i + 1}. {text}"
        if selected == i:
            label = "✅ " + label
        kb.button(text=label, callback_data=f"mcq:{i}")
    kb.adjust(1)
    return kb.as_markup()

async def idea_vote_kb(session: AsyncSession, open_step: Step, voter: User):
    ideas = (
        await session.execute(
            select(Idea)
            .where(Idea.step_id == open_step.id)
            .order_by(Idea.submitted_at.asc())
        )
    ).scalars().all()
    voted_ids = set(
        x
        for (x,) in (
            await session.execute(
                select(IdeaVote.idea_id).where(
                    IdeaVote.step_id == open_step.id,
                    IdeaVote.voter_id == voter.id,
                )
            )
        ).all()
    )
    rows = []
    for idx, idea in enumerate(ideas, start=1):
        if idea.user_id == voter.id:
            continue
        text = idea.text[:40].replace("\n", " ")
        prefix = "✅ " if idea.id in voted_ids else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=prefix + f"{idx}. {text}", callback_data=f"vote:{idea.id}"
                )
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        await save_avatar(bot, user)
        user.waiting_for_name = True
        await session.commit()
        if user.name:
            await message.answer(texts.CURRENT_NAME.format(name=user.name))
        else:
            await message.answer(texts.ENTER_NAME)
    finally:
        await session.close()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        user.waiting_for_name = False
        await session.commit()
        await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_UNCHANGED)
    finally:
        await session.close()

@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            emoji = message.text.strip()
            if not emoji:
                await message.answer(texts.ASK_AVATAR)
                return
            path = Path(settings.AVATAR_DIR)
            path.mkdir(exist_ok=True)
            _emoji_avatar(path, user, emoji[0])
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        # 1) режим ввода имени работает ТОЛЬКО если он активирован /start
        if user.waiting_for_name:
            new_name = message.text.strip()[:120]
            if not new_name:
                await message.answer(texts.NAME_EMPTY)
                return
            was_new = user.name == ""
            user.name = new_name
            user.waiting_for_name = False
            await session.commit()
            saved = await save_avatar(bot, user)
            if was_new and not saved:
                user.waiting_for_avatar = True
                await session.commit()
                await message.answer(texts.ASK_AVATAR)
            else:
                await hub.broadcast({"type": "reload"})
                await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        # 2) обычные текстовые ответы принимаем только в open:collect
        if step.type == "open" and state.phase == 0:
            existing = (
                await session.execute(
                    select(Idea).where(Idea.step_id == step.id, Idea.user_id == user.id)
                )
            ).scalar_one_or_none()
            now = datetime.utcnow()
            delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
            delta_ms = max(0, delta_ms)
            if existing:
                old_delta = int(
                    (existing.submitted_at - state.step_started_at).total_seconds() * 1000
                )
                existing.text = message.text.strip()
                existing.submitted_at = now
                user.total_answer_ms += delta_ms - old_delta
                user.open_answer_ms += delta_ms - old_delta
            else:
                session.add(
                    Idea(
                        step_id=step.id,
                        user_id=user.id,
                        text=message.text.strip(),
                        submitted_at=now,
                    )
                )
                user.total_answer_ms += delta_ms
                user.open_answer_ms += delta_ms
                user.open_answer_count += 1
            await session.commit()
            await message.answer(texts.IDEA_ACCEPTED, parse_mode="HTML")
            count = await session.scalar(
                select(func.count(Idea.id)).where(Idea.step_id == step.id)
            )
            total = await session.scalar(
                select(func.count(User.id)).where(User.name != "")
            )
            last_at = await session.scalar(
                select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id)
            )
            last_ago = None
            if last_at:
                last_ago = int((datetime.utcnow() - last_at).total_seconds())
            await hub.broadcast(
                {"type": "idea_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago}
            )
        else:
            await message.answer(texts.TEXT_NOT_ACCEPTED)
    finally:
        await session.close()


@router.message(F.sticker)
async def on_sticker(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            await _sticker_avatar(bot, user, message.sticker)
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
    finally:
        await session.close()

@router.callback_query(F.data.startswith("mcq:"))
async def cb_mcq(cb: CallbackQuery, bot: Bot):
    choice_idx = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "quiz" or state.phase != 0:
            await cb.answer(texts.NOT_ANSWER_PHASE, show_alert=True)
            return
        existing = (
            await session.execute(
                select(McqAnswer).where(
                    McqAnswer.step_id == step.id, McqAnswer.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        now = datetime.utcnow()
        delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
        delta_ms = max(0, delta_ms)
        if existing and existing.choice_idx == choice_idx:
            await cb.answer(texts.ANSWER_UNCHANGED)
            return
        if existing:
            old_delta = int(
                (existing.answered_at - state.step_started_at).total_seconds() * 1000
            )
            existing.choice_idx = choice_idx
            existing.answered_at = now
            user.total_answer_ms += delta_ms - old_delta
            user.quiz_answer_ms += delta_ms - old_delta
        else:
            session.add(
                McqAnswer(
                    step_id=step.id,
                    user_id=user.id,
                    choice_idx=choice_idx,
                    answered_at=now,
                )
            )
            user.total_answer_ms += delta_ms
            user.quiz_answer_ms += delta_ms
            user.quiz_answer_count += 1
        await session.commit()
        await cb.answer(texts.ANSWER_SAVED)
        options = [o.text for o in (await session.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
        await cb.message.edit_reply_markup(reply_markup=mcq_kb(options, selected=choice_idx))
        count = await session.scalar(select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id))
        total = await session.scalar(select(func.count(User.id)).where(User.name != ""))
        last_at = await session.scalar(
            select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
        )
        last_ago = None
        if last_at:
            last_ago = int((datetime.utcnow() - last_at).total_seconds())
        await hub.broadcast({"type": "mcq_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago})
    finally:
        await session.close()

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(cb: CallbackQuery, bot: Bot):
    idea_id = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "open" or state.phase != 1:
            await cb.answer(texts.NOT_VOTE_PHASE, show_alert=True)
            return
        existing = (await session.execute(select(IdeaVote).where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea_id, IdeaVote.voter_id == user.id))).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
            await cb.answer(texts.VOTE_REMOVED)
        else:
            session.add(IdeaVote(step_id=step.id, idea_id=idea_id, voter_id=user.id))
            await session.commit()
            await cb.answer(texts.VOTE_COUNTED)
        kb = await idea_vote_kb(session, step, user)
        await cb.message.edit_reply_markup(reply_markup=kb)
        # обновить прогресс на общем экране (voters_count, last_vote_at)
        voters = (await session.execute(
            select(IdeaVote.voter_id)
            .where(IdeaVote.step_id == step.id)
            .group_by(IdeaVote.voter_id)
        )).all()
        last_vote_at = await session.scalar(
            select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id)
        )
        last_ago = None
        if last_vote_at:
            last_ago = int((datetime.utcnow() - last_vote_at).total_seconds())
        await hub.broadcast(
            {"type": "vote_progress", "count": len(voters), "last": last_ago}
        )
    finally:
        await session.close()

async def build_prompt_messages(user: User, step: Step, phase: int):
    msgs = []
    if step.type == "registration":
        msgs.append((texts.REGISTRATION_WAIT, {}))
    elif step.type == "open":
        if phase == 0:
            header = texts.OPEN_HEADER
            title = escape(step.title)
            body = escape(step.text or "")
            instr = texts.OPEN_INSTR
            text = (
                f"<b>{header}</b>\n\n"
                f"{title}\n\n"
                f"{body}\n\n\n"
                f"<i>{instr}</i>"
            ).strip()
            msgs.append((text, {"parse_mode": "HTML"}))
        elif phase == 1:
            async with AsyncSessionLocal() as s:
                kb = await idea_vote_kb(s, step, user)
                if kb:
                    msgs.append((texts.VOTE_START, {"parse_mode": "HTML", "reply_markup": kb}))
                else:
                    msgs.append((texts.VOTE_NO_OPTIONS, {}))
        elif phase == 2:
            async with AsyncSessionLocal() as s:
                points = await s.scalar(
                    select(func.count(IdeaVote.id))
                    .join(Idea, Idea.id == IdeaVote.idea_id)
                    .where(Idea.step_id == step.id, Idea.user_id == user.id)
                )
            msgs.append((texts.VOTE_FINISHED.format(points=int(points or 0)), {}))
    elif step.type == "quiz":
        if phase == 0:
            async with AsyncSessionLocal() as s:
                options = [
                    o.text
                    for o in (
                        await s.execute(
                            select(StepOption)
                            .where(StepOption.step_id == step.id)
                            .order_by(StepOption.idx)
                        )
                    ).scalars().all()
                ]
            header = texts.QUIZ_HEADER
            title = escape(step.title)
            instr = texts.QUIZ_INSTR
            text = f"<b>{header}</b>\n\n{title}\n\n<i>{instr}</i>"
            msgs.append((text, {"parse_mode": "HTML", "reply_markup": mcq_kb(options, selected=None)}))
        else:
            async with AsyncSessionLocal() as s:
                ans = (
                    await s.execute(
                        select(McqAnswer).where(
                            McqAnswer.step_id == step.id, McqAnswer.user_id == user.id
                        )
                    )
                ).scalar_one_or_none()
            if not ans:
                text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
            elif step.correct_index is not None and ans.choice_idx == step.correct_index:
                points = step.points_correct or 0
                text = texts.CORRECT_PREFIX.format(points=points) + texts.RESPONSES_CLOSED
            else:
                text = texts.WRONG_ANSWER + texts.RESPONSES_CLOSED
            msgs.append((text, {}))
    elif step.type == "leaderboard":
        async with AsyncSessionLocal() as s:
            users = await get_leaderboard_users(s)
        place = next(i for i, u in enumerate(users, start=1) if u.id == user.id)
        open_avg = (
            user.open_answer_ms / user.open_answer_count / 1000
            if user.open_answer_count
            else 0
        )
        quiz_avg = (
            user.quiz_answer_ms / user.quiz_answer_count / 1000
            if user.quiz_answer_count
            else 0
        )
        text = texts.LEADERBOARD.format(
            score=user.total_score, place=place, open_avg=open_avg, quiz_avg=quiz_avg
        )
        msgs.append((text, {}))
    return msgs


async def send_prompt(bot: Bot, user: User, step: Step, phase: int, prefix: str | None = None):
    if step.type == "open" and phase == 2 and user.last_vote_msg_id:
        try:
            await bot.edit_message_reply_markup(user.id, user.last_vote_msg_id, reply_markup=None)
        except Exception:
            pass
        async with AsyncSessionLocal() as s:
            u = await s.get(User, user.id)
            if u:
                u.last_vote_msg_id = None
                await s.commit()
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
        if step.type == "open" and phase == 1 and kwargs.get("reply_markup"):
            async with AsyncSessionLocal() as s:
                u = await s.get(User, user.id)
                if u:
                    u.last_vote_msg_id = msg.message_id
                    await s.commit()
