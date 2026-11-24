from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    favorite_genres: Mapped[str] = mapped_column(String(255), default='Sci-Fi,Comedy,Thriller')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserContentState(Base):
    __tablename__ = 'user_content_state'
    __table_args__ = (UniqueConstraint('user_id','content_id',name='uq_user_content_state'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey('content.id', ondelete='CASCADE'), index=True)
    reaction: Mapped[str | None] = mapped_column(String(12), nullable=True)
    in_my_list: Mapped[int] = mapped_column(Integer, default=0)
    progress_seconds: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class InteractionEvent(Base):
    __tablename__ = 'interaction_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    content_id: Mapped[int | None] = mapped_column(ForeignKey('content.id', ondelete='SET NULL'), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
