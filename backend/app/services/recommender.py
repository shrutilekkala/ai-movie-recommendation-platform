from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Content
from app.models.user import UserContentState
from redis.asyncio import Redis
from app.core.config import settings

ARTIFACT_PATH = Path('/app/artifacts/movielens_model.json')


def load_artifact() -> dict[str, Any] | None:
    if not ARTIFACT_PATH.exists():
        return None
    try:
        return json.loads(ARTIFACT_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def status_payload() -> dict[str, Any]:
    artifact = load_artifact()
    empty_metrics = {'hit_rate_at_10': None, 'recall_at_10': None, 'ndcg_at_10': None, 'evaluated_users': 0}
    if not artifact:
        return {
            'ready': False, 'dataset': 'MovieLens latest-small', 'movies': 0, 'ratings': 0, 'users': 0,
            'positive_ratings': 0, 'trained_items': 0, 'metrics': empty_metrics, 'model_comparison': {},
            'winner': None, 'learned_weights': {},
            'message': 'Run: docker compose exec backend python -m app.scripts.import_movielens',
        }
    stats = artifact.get('stats', {})
    return {
        'ready': True,
        'dataset': artifact.get('dataset', 'MovieLens latest-small'),
        'movies': stats.get('movies', 0), 'ratings': stats.get('ratings', 0), 'users': stats.get('users', 0),
        'positive_ratings': stats.get('positive_ratings', 0), 'trained_items': stats.get('trained_items', 0),
        'metrics': artifact.get('metrics', empty_metrics),
        'model_comparison': artifact.get('model_comparison', {}),
        'winner': artifact.get('winner'),
        'learned_weights': artifact.get('learned_weights', {}),
        'message': 'Real MovieLens data loaded. Hybrid candidate generation and learned ranking weights are ready.',
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b: return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _content_affinity(seed_ids: list[int], target_id: int, genre_map: dict[str, list[str]]) -> float:
    target = set(genre_map.get(str(target_id), []))
    if not target or not seed_ids: return 0.0
    sims = [_jaccard(target, set(genre_map.get(str(seed), []))) for seed in seed_ids[-20:]]
    return max(sims, default=0.0) * 0.65 + (sum(sims) / max(1, len(sims))) * 0.35


async def nexus_recommendations(db: AsyncSession, user_id: int, limit: int = 12) -> list[dict[str, Any]]:
    artifact = load_artifact()
    if not artifact:
        rows = list((await db.scalars(select(Content).where(Content.catalog_source == 'movielens').order_by(desc(Content.rating_count), desc(Content.avg_rating)).limit(limit))).all())
        return [{'content': item, 'score': .70, 'reason': 'Popular with MovieLens viewers', 'signals': {'popularity': 1.0, 'collaborative': 0.0, 'content': 0.0}} for item in rows]

    states = list((await db.scalars(select(UserContentState).where(UserContentState.user_id == user_id))).all())
    content_ids = [s.content_id for s in states]
    content_map: dict[int, Content] = {}
    if content_ids:
        items = list((await db.scalars(select(Content).where(Content.id.in_(content_ids)))).all())
        content_map = {i.id: i for i in items}

    seed_weights: dict[int, float] = {}
    excluded: set[int] = set()
    seed_titles: dict[int, str] = {}
    for state in states:
        item = content_map.get(state.content_id)
        if not item or item.movielens_id is None: continue
        mlid = item.movielens_id
        if state.reaction == 'dislike': excluded.add(mlid); continue
        weight = (3.0 if state.reaction == 'like' else 0.0) + (1.0 if state.in_my_list else 0.0)
        if state.progress_seconds > 0:
            weight += min(2.0, state.progress_seconds / max(1, item.duration_minutes * 60) * 2.0)
        if weight > 0:
            seed_weights[mlid] = seed_weights.get(mlid, 0.0) + weight
            seed_titles[mlid] = item.title

    neighbor_map = artifact.get('neighbors', {})
    popularity = artifact.get('popularity', [])
    popularity_norm = artifact.get('popularity_norm', {})
    genre_map = artifact.get('movie_genres', {})
    weights = artifact.get('learned_weights') or {'collaborative': .55, 'content': .25, 'popularity': .20}

    cf_raw: dict[int, float] = {}
    best_seed: dict[int, tuple[int, float]] = {}
    for seed_id, seed_weight in seed_weights.items():
        for target, sim in neighbor_map.get(str(seed_id), []):
            target = int(target); sim = float(sim)
            if target in seed_weights or target in excluded: continue
            val = sim * seed_weight
            cf_raw[target] = cf_raw.get(target, 0.0) + val
            if target not in best_seed or val > best_seed[target][1]: best_seed[target] = (seed_id, val)
    cf_max = max(cf_raw.values(), default=1.0) or 1.0
    cf_norm = {m: v / cf_max for m, v in cf_raw.items()}

    candidates = set(cf_raw)
    candidates.update(int(pair[0]) for pair in popularity[:250])
    candidates.difference_update(seed_weights)
    candidates.difference_update(excluded)
    seed_ids = list(seed_weights)

    scored = []
    for movie_id in candidates:
        cf = cf_norm.get(movie_id, 0.0)
        content = _content_affinity(seed_ids, movie_id, genre_map)
        pop = float(popularity_norm.get(str(movie_id), 0.0))
        # Cold-start: if no behavior exists, let popularity dominate while preserving learned model semantics.
        if seed_ids:
            final = float(weights.get('collaborative', .55))*cf + float(weights.get('content', .25))*content + float(weights.get('popularity', .20))*pop
        else:
            final = .15*cf + .10*content + .75*pop
        scored.append((movie_id, final, cf, content, pop))
    scored.sort(key=lambda x: x[1], reverse=True)
    shortlist = scored[:max(limit * 4, 50)]
    mlids = [x[0] for x in shortlist]
    rows = list((await db.scalars(select(Content).where(Content.movielens_id.in_(mlids)))).all()) if mlids else []
    by_ml = {i.movielens_id: i for i in rows}
    max_final = max((x[1] for x in shortlist), default=1.0) or 1.0

    # Phase 4: low-latency session features produced from Kafka and stored in Redis.
    session_genres = {}
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        session_genres = {k: float(v) for k,v in (await redis.hgetall(f'nexus:session:{user_id}:genres')).items()}
    except Exception:
        session_genres = {}
    finally:
        try: await redis.aclose()
        except Exception: pass

    results = []
    for mlid, final, cf, content, pop in shortlist:
        item = by_ml.get(mlid)
        if not item: continue
        item_genres = [g.strip() for g in (item.genres or item.genre or '').split('|') if g.strip()]
        raw_session = max([session_genres.get(g, 0.0) for g in item_genres], default=0.0)
        session_affinity = max(-1.0, min(1.0, raw_session / 3.0))
        # Preserve the offline hybrid as the backbone; session context can move candidates up/down in real time.
        final = max(0.0, final * 0.82 + max(0.0, session_affinity) * 0.18) if session_affinity >= 0 else max(0.0, final + session_affinity * 0.12)
        seed = best_seed.get(mlid, (None, 0))[0]
        if seed and seed_titles.get(seed): reason = f'Because you engaged with {seed_titles[seed]}'
        elif content > .45: reason = 'Strong genre affinity with your recent taste'
        else: reason = 'Popular with real MovieLens viewers'
        results.append({
            'content': item,
            'score': round(min(.99, .60 + .39 * final / max_final), 4),
            'reason': reason,
            'signals': {'collaborative': round(cf, 4), 'content': round(content, 4), 'popularity': round(pop, 4), 'session_affinity': round(session_affinity,4), 'final_rank_score': round(final, 4)},
        })
        if len(results) >= limit: break
    return results


async def movielens_user_recommendations(db: AsyncSession, movielens_user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    artifact = load_artifact()
    if not artifact: return []
    histories = artifact.get('user_histories', {})
    seen = histories.get(str(movielens_user_id), [])
    if not seen: return []
    neighbors = artifact.get('neighbors', {})
    pop_norm = artifact.get('popularity_norm', {})
    genre_map = artifact.get('movie_genres', {})
    weights = artifact.get('learned_weights') or {'collaborative': .55, 'content': .25, 'popularity': .20}
    seen_set = set(seen); cf_raw: dict[int,float] = {}
    for seed in seen[-30:]:
        for target, sim in neighbors.get(str(seed), []):
            target=int(target)
            if target not in seen_set: cf_raw[target]=cf_raw.get(target,0.0)+float(sim)
    cfmax=max(cf_raw.values(),default=1.0) or 1.0
    candidates=set(cf_raw) | {int(x[0]) for x in artifact.get('popularity',[])[:250] if int(x[0]) not in seen_set}
    scored=[]
    for m in candidates:
        cf=cf_raw.get(m,0.0)/cfmax; content=_content_affinity(seen,m,genre_map); pop=float(pop_norm.get(str(m),0.0))
        final=float(weights.get('collaborative',.55))*cf+float(weights.get('content',.25))*content+float(weights.get('popularity',.20))*pop
        scored.append((m,final,cf,content,pop))
    scored.sort(key=lambda x:x[1],reverse=True)
    mlids=[x[0] for x in scored[:max(limit*3,30)]]
    rows=list((await db.scalars(select(Content).where(Content.movielens_id.in_(mlids)))).all()) if mlids else []
    by_ml={i.movielens_id:i for i in rows}; maxscore=max((x[1] for x in scored),default=1.0) or 1.0
    out=[]
    for m,final,cf,content,pop in scored:
        if m not in by_ml: continue
        out.append({'content':by_ml[m],'score':round(min(.99,.60+.39*final/maxscore),4),'reason':f'Hybrid profile for real MovieLens user {movielens_user_id}','signals':{'collaborative':round(cf,4),'content':round(content,4),'popularity':round(pop,4),'final_rank_score':round(final,4)}})
        if len(out)>=limit: break
    return out
