# GitHub Copilot instructions

## Project overview

This repository contains an AI-powered, real-time movie recommendation and
semantic discovery platform. It combines MovieLens and TMDB catalog data,
hybrid recommendation ranking, multilingual semantic search, and live session
personalization.

## Architecture

- `backend/` is an asynchronous Python API built with FastAPI, SQLAlchemy, and
  PostgreSQL.
- `frontend/` is a Next.js application written in React and TypeScript.
- Qdrant stores semantic-search embeddings generated with FastEmbed.
- Kafka carries user-interaction events, and Redis stores low-latency session
  features used for recommendation reranking.
- Docker Compose defines the local application and infrastructure services.

## Backend conventions

- Preserve asynchronous database and network I/O. Do not introduce blocking
  calls inside async request handlers.
- Keep API routes thin. Put recommendation, discovery, and personalization
  logic in `backend/app/services/` or `backend/app/ml/`.
- Use SQLAlchemy models from `backend/app/models/` and Pydantic schemas from
  `backend/app/schemas/` rather than returning unvalidated dictionaries from
  API routes.
- Read configuration and credentials through `backend/app/core/config.py` and
  environment variables. Never hard-code tokens, passwords, or connection
  strings.
- Maintain compatibility with both MovieLens and TMDB catalog records,
  including records that do not have a MovieLens identifier.

## Recommendation and search behavior

- Treat collaborative, content-affinity, popularity, and real-time session
  signals as separate explainable ranking features.
- Preserve cold-start behavior for users without interaction history.
- Exclude disliked and already-consumed seed items where the existing workflow
  requires it.
- Evaluate ranking changes with recommendation metrics such as Hit Rate@10,
  Recall@10, and NDCG@10. Do not describe generic classification accuracy as a
  recommender metric.
- Keep semantic retrieval and deterministic genre constraints compatible.
  Explicit inclusions, exclusions, and language filters must not be discarded
  when vector similarity is applied.
- Preserve English and Telugu query normalization and canonical genre mapping.

## Frontend conventions

- Use typed interfaces from `frontend/lib/types.ts` and centralized API helpers
  from `frontend/lib/api.ts`.
- Prefer reusable React components over duplicating page-level UI logic.
- Preserve loading, empty, and error states for network-backed experiences.
- Maintain accessible labels and keyboard behavior for interactive controls.

## Infrastructure and reliability

- Keep service names and internal ports consistent with `docker-compose.yml`.
- Add health checks or graceful fallbacks when introducing infrastructure
  dependencies.
- Kafka consumers should tolerate malformed events without terminating the
  processing loop.
- Redis and Qdrant outages should degrade optional personalization or semantic
  features gracefully where practical.

## Testing and quality

- Add or update tests for observable behavior changes.
- Run backend tests with `pytest` and validate the frontend with its TypeScript
  or build command when the relevant dependencies are available.
- Avoid committing generated model artifacts, dependency directories, caches,
  local databases, `.env` files, or credentials.
- Keep changes focused and update the README when setup steps, architecture, or
  user-visible capabilities change.

