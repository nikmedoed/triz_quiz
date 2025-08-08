# DB models (SQLAlchemy 2.0 style)
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    avatar_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    total_answer_ms: Mapped[int] = mapped_column(Integer, default=0)  # tie-breaker

class Step(Base):
    __tablename__ = "steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32))  # registration | open | quiz | leaderboard
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # description for open; question text for quiz
    correct_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # quiz only
    points_correct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # quiz only

class GlobalState(Base):
    __tablename__ = "global_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"))
    step_started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # start of current block
    phase: Mapped[int] = mapped_column(Integer, default=0)  # phase inside block

class StepOption(Base):
    __tablename__ = "step_options"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 0..N-1
    text: Mapped[str] = mapped_column(Text)
    UniqueConstraint("step_id", "idx")

class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # open block
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "user_id")

class IdeaVote(Base):
    __tablename__ = "idea_votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # open block
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "idea_id", "voter_id")

class McqAnswer(Base):
    __tablename__ = "mcq_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id"), index=True)  # quiz block
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    choice_idx: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    UniqueConstraint("step_id", "user_id")
