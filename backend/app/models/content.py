from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Content(Base):
    __tablename__ = "content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(220), index=True)
    synopsis: Mapped[str] = mapped_column(Text)
    genre: Mapped[str] = mapped_column(String(120), index=True)
    genres: Mapped[str] = mapped_column(String(500), default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(30), default="Movie")
    year: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=110)
    match_score: Mapped[float] = mapped_column(Float, default=0.8)
    maturity_rating: Mapped[str] = mapped_column(String(10), default="NR")
    accent: Mapped[str] = mapped_column(String(50), default="aurora")
    featured: Mapped[bool] = mapped_column(Boolean, default=False)

    catalog_source: Mapped[str] = mapped_column(String(30), default="nexus", index=True)
    movielens_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Cross-catalog / multilingual metadata.
    original_language: Mapped[str] = mapped_column(String(10), default="en", index=True)
    original_title: Mapped[str | None] = mapped_column(String(250), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Source-aware rating/popularity signals. MovieLens and TMDB scores are kept separate.
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    tmdb_popularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmdb_vote_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmdb_vote_count: Mapped[int] = mapped_column(Integer, default=0)
