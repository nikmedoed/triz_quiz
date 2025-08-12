"""Database models (SQLAlchemy 2.0 style)."""
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    total_answer_ms: Mapped[int] = mapped_column(Integer, default=0)
    open_answer_ms: Mapped[int] = mapped_column(Integer, default=0)
    open_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    quiz_answer_ms: Mapped[int] = mapped_column(Integer, default=0)
    quiz_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    last_vote_msg_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_for_name: Mapped[bool] = mapped_column(Boolean, default=False)  # /start → True, до сохранения имени
    waiting_for_avatar: Mapped[bool] = mapped_column(Boolean, default=False)


class Step(Base):
    __tablename__ = "steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32))  # registration | open | quiz | sequence | leaderboard
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timer_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GlobalState(Base):
    __tablename__ = "global_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"))
    step_started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    phase_started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    phase: Mapped[int] = mapped_column(Integer, default=0)


class StepOption(Base):
    __tablename__ = "step_options"
    __table_args__ = (UniqueConstraint("step_id", "idx"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = (UniqueConstraint("step_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdeaVote(Base):
    __tablename__ = "idea_votes"
    __table_args__ = (UniqueConstraint("step_id", "idea_id", "voter_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    voter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class McqAnswer(Base):
    __tablename__ = "mcq_answers"
    __table_args__ = (UniqueConstraint("step_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    choice_idx: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SequenceAnswer(Base):
    __tablename__ = "sequence_answers"
    __table_args__ = (UniqueConstraint("step_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    order_json: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
