from pydantic import BaseModel, Field
from app.schemas.content import ContentOut


class RecommendationSignals(BaseModel):
    collaborative: float = 0.0
    content: float = 0.0
    popularity: float = 0.0
    final_rank_score: float | None = None


class RecommendationOut(BaseModel):
    content: ContentOut
    score: float
    reason: str
    signals: RecommendationSignals | None = None


class ModelMetrics(BaseModel):
    hit_rate_at_10: float | None = None
    recall_at_10: float | None = None
    ndcg_at_10: float | None = None
    evaluated_users: int = 0


class RecommendationStatus(BaseModel):
    ready: bool
    dataset: str
    movies: int
    ratings: int
    users: int
    positive_ratings: int
    trained_items: int
    metrics: ModelMetrics
    model_comparison: dict[str, ModelMetrics] = Field(default_factory=dict)
    winner: str | None = None
    learned_weights: dict[str, float] = Field(default_factory=dict)
    message: str
