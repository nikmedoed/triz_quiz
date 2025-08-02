"""Formatting helpers for messages and keyboards."""

import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import state


def vote_keyboard_for(uid: int) -> InlineKeyboardMarkup:
    """Build inline keyboard with checkmarks for selected ideas."""
    selected = state.votes_current.get(uid, set())
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅ ' if idea['id'] in selected else ''}{idea['id']}. {idea['text'][:30]}",
                    callback_data=f"vote:{idea['id']}",
                )
            ]
            for idea in state.ideas
            if idea['user_id'] != uid
        ]
    )


def quiz_keyboard_for(step: dict, uid: int) -> InlineKeyboardMarkup:
    """Build quiz keyboard with a checkmark on the selected option."""
    chosen = state.answers_current.get(uid, {}).get('text')
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅ ' if str(i + 1) == str(chosen) else ''}{i + 1}. {opt[:30]}",
                    callback_data=f"quiz:{i + 1}",
                )
            ]
            for i, opt in enumerate(step.get('options', []))
        ]
    )


def format_step(step: dict) -> str:
    """Render message for current step according to its type."""
    t = step.get("type")
    if t == "open":
        header = (
            "<b>Предложите идею решения проблемной ситуации (открытый ответ)</b>\n\n\n"
        )
        body = html.escape(step.get("title", ""))
        if step.get("description"):
            body += f"\n\n{html.escape(step['description'])}"
        tail = (
            "\n\n\n<i>Пришлите ваш ответ в этот чат.\n"
            "- Учитывается один последний ответ\n"
            "- В свободной форме\n"
            "- Лаконично, важна скорость\n"
            "- Укажите логику решения, использванные приёмы, методы, обоснуйте</i>"
        )
        return header + body + tail
    if t == "quiz":
        header = "<b>Выберите один вариант ответа</b>\n\n\n"
        body = html.escape(step.get("title", ""))
        if step.get("description"):
            body += f"\n{html.escape(step['description'])}"
        tail = (
            "\n\n\n<i>Выберите\n"
            "- Наиболее подходящий вариант\n"
            "- Быстро, пока есть время\n"
            "- Можно изменить выбор</i>"
        )
        return header + body + tail
    if t == "vote":
        return (
            "Ответы более не принимаются.\n\n"
            "<b>Начато голосование за идеи.</b>\n\n"
            "Выберите номера, которые считаете достойным и методологически "
            "обоснованным решением описанной проблемы."
        )
    if t == "vote_results":
        return "Голосование завершено. Результаты на экране."
    text = f"Сейчас идёт шаг: {step['title']}"
    if step.get('description'):
        text += f"\n{step['description']}"
    return text


def format_leaderboard(rows: list[dict]) -> str:
    """Return leaderboard as multiline string."""
    return "\n".join(f"{r['place']}. {r['name']}: {r['score']}" for r in rows)


def build_rating(rows: list[dict]) -> list[dict]:
    """Convert leaderboard rows to rating payload."""
    return [
        {'id': r['id'], 'name': r['name'], 'score': r['score'], 'place': r['place']}
        for r in rows
    ]
