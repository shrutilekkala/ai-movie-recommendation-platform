export type Content = {
  id: number;
  title: string;
  synopsis: string;
  genre: string;
  genres: string;
  tags: string;
  content_type: string;
  year: number;
  duration_minutes: number;
  match_score: number;
  maturity_rating: string;
  accent: string;
  featured: boolean;
  catalog_source: string;
  movielens_id: number | null;
  imdb_id: string | null;
  tmdb_id: number | null;
  original_language: string;
  original_title: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  avg_rating: number | null;
  rating_count: number;
  tmdb_popularity: number | null;
  tmdb_vote_average: number | null;
  tmdb_vote_count: number;
};

export type FeedSection = {
  key: string;
  title: string;
  items: Content[];
};

export type HomeFeed = {
  hero: Content;
  sections: FeedSection[];
};

export type User = {
  id: number;
  email: string;
  display_name: string;
  favorite_genres: string;
};

export type AuthResponse = {
  token: string;
  user: User;
};

export type LibraryItem = {
  content: Content;
  reaction: string | null;
  in_my_list: boolean;
  progress_seconds: number;
};

export type RecommendationSignals = {
  collaborative: number;
  content: number;
  popularity: number;
  final_rank_score?: number | null;
};

export type Recommendation = {
  content: Content;
  score: number;
  reason: string;
  signals?: RecommendationSignals | null;
};

export type ModelMetrics = {
  hit_rate_at_10: number | null;
  recall_at_10: number | null;
  ndcg_at_10: number | null;
  evaluated_users: number;
};

export type RecommendationStatus = {
  ready: boolean;
  dataset: string;
  movies: number;
  ratings: number;
  users: number;
  positive_ratings: number;
  trained_items: number;
  metrics: ModelMetrics;
  model_comparison: Record<string, ModelMetrics>;
  winner: string | null;
  learned_weights: Record<string, number>;
  message: string;
};

export type SessionAffinity = {
  genre: string;
  score: number;
};

export type SessionEvent = {
  event_type: string;
  content_id: number | null;
  title: string | null;
  genre: string | null;
  weight: number;
  occurred_at: string;
};

export type RealtimeSession = {
  event_count: number;
  last_event_type: string | null;
  updated_at: string | null;
  genre_affinity: SessionAffinity[];
  recent_events: SessionEvent[];
};

/* =========================================================
   PHASE 5 SEMANTIC TYPES
   ========================================================= */

export type DiscoverySignals = {
  semantic: number;
  lexical: number;
  genre: number;
  session: number;
  popularity: number;
  language?: number;
};

export type DiscoveryResult = {
  content: Content;
  score: number;
  reason: string;
  signals: DiscoverySignals;
};

export type DiscoveryIntent = {
  genres: string[];
  genre_match_mode: "all" | "any" | string;
  max_minutes: number | null;
  year: number | null;
  excluded_genres: string[];
  runtime_note: string | null;
  language: string;
  normalized_query: string;
};

export type DiscoveryResponse = {
  query: string;
  normalized_query?: string;
  source?: string;
  language?: string;
  intent: DiscoveryIntent;
  semantic_ready: boolean;
  results: DiscoveryResult[];
  message: string;
  detail?: string;
};

export type SemanticStatus = {
  ready: boolean;
  collection: string;
  vectors: number;
  embedding_model: string;
  message?: string;
  detail?: string;
};

export type CatalogStatus = {
  total: number;
  movielens: number;
  tmdb: number;
  telugu: number;
};

/* =========================================================
   PHASE 6 AGENT TYPES
   ========================================================= */

export type AgentConstraint = {
  type: string;
  value: string | number | boolean | string[] | null;
};

export type AgentIntent = {
  original_query: string;
  normalized_query: string;
  language: string | null;
  genres: string[];
  genre_match_mode: "all" | "any" | string;
  excluded_genres: string[];
  max_minutes: number | null;
  session_budget_minutes?: number | null;
  watch_context: string | null;
  moods: string[];
  hard_constraints: AgentConstraint[];
  soft_preferences: AgentConstraint[];
  parser_confidence: number;
};

export type AgentTraceStep = {
  step: number;
  tool: string;
  status: "success" | "degraded" | "skipped" | string;
  detail: string;
};

export type AgentProfile = {
  authenticated: boolean;
  user_id?: number;
  display_name?: string;
  favorite_genres: string[];
  liked_content_ids: number[];
  disliked_content_ids: number[];
  my_list_content_ids: number[];
};

export type AgentSession = {
  available: boolean;
  event_count: number;
  last_event_type?: string | null;
  updated_at?: string | null;
  genre_affinity: SessionAffinity[];
  recent_events: SessionEvent[];
  error?: string;
};

export type ContentGenreEvidence = {
  state?: "VERIFIED" | "CATALOG_BACKED" | "REJECTED" | string;
  catalog_support?: boolean;
  cue_hits?: number;
  cue_score?: number;
  cues?: string[];
  strongest_content_genre?: string | null;
  strongest_content_score?: number;
  contradicting_genre?: string | null;
  contradicting_score?: number;
  strong_contradiction?: boolean;
  supported?: boolean;
};

export type ContentGenreVerification = {
  allowed?: boolean;
  verified?: boolean;
  status?: "VERIFIED" | "CATALOG_BACKED" | "REJECTED" | string;
  reason?: string;
  requested?: string[];
  supported?: string[];
  verified_supported?: string[];
  catalog_backed?: string[];
  unsupported?: string[];
  top_content_genres?: string[];
  evidence?: Record<string, ContentGenreEvidence>;
};

export type AgentSignals = {
  semantic: number;
  personalized_recommendation: number;
  requested_genre: number;
  live_session: number;
  final_score: number;
  content_genre_verification?: ContentGenreVerification | null;
};

export type AgentResult = {
  content: Content;
  score: number;
  reason: string;
  match_type?: "EXACT" | "SIMILAR" | string;
  matched_genres?: string[];
  missing_genres?: string[];
  genre_coverage?: number;
  agent_signals: AgentSignals;
};

export type AgentRejectedCandidate = {
  content_id: number;
  title: string | null;
  genres?: string | null;
  runtime?: number | null;
  reasons: string[];
  content_genre_verification?: ContentGenreVerification | null;
};

export type AgentCandidateSummary = {
  semantic_candidates: number;
  recommendation_candidates: number;
  rejected_candidates: number;
  returned_candidates: number;
  similar_candidates?: number;
};

export type AgentResponse = {
  query: string;
  intent: AgentIntent;
  tools_used: string[];
  trace: AgentTraceStep[];

  context: {
    profile: AgentProfile;
    session: AgentSession;
  };

  candidate_summary: AgentCandidateSummary;

  results: AgentResult[];
  similar_results?: AgentResult[];
  exact_match_count?: number;
  similar_match_count?: number;

  rejected_count: number;
  rejected: AgentRejectedCandidate[];

  agent_version: string;
};