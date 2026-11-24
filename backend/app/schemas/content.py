from pydantic import BaseModel, ConfigDict, Field


class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    synopsis: str
    genre: str
    genres: str
    tags: str
    content_type: str
    year: int
    duration_minutes: int
    match_score: float = Field(ge=0, le=1)
    maturity_rating: str
    accent: str
    featured: bool
    catalog_source: str
    movielens_id: int | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None

    original_language: str = "en"
    original_title: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None

    avg_rating: float | None = None
    rating_count: int = 0
    tmdb_popularity: float | None = None
    tmdb_vote_average: float | None = None
    tmdb_vote_count: int = 0


class FeedSection(BaseModel):
    key: str
    title: str
    items: list[ContentOut]


class HomeFeed(BaseModel):
    hero: ContentOut
    sections: list[FeedSection]
