from sqlalchemy import Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MovieLensRating(Base):
    __tablename__ = "movielens_ratings"
    __table_args__ = (
        Index("ix_ml_user_movie", "movielens_user_id", "content_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movielens_user_id: Mapped[int] = mapped_column(Integer, index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id", ondelete="CASCADE"), index=True)
    rating: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[int] = mapped_column(Integer)
