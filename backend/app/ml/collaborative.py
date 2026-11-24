from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import product


def _genre_map(movies_rows: list[dict[str, str]]) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for row in movies_rows:
        genres = row.get("genres", "")
        values = {g for g in genres.split("|") if g and g != "(no genres listed)"}
        result[int(row["movieId"])] = values
    return result


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _content_scores(seen: list[int], genre_by_movie: dict[int, set[str]], candidates: set[int]) -> dict[int, float]:
    # Recency-weighted genre affinity from a user's observed positive history.
    recent = seen[-20:]
    if not recent:
        return {}
    scores: dict[int, float] = {}
    for cand in candidates:
        cg = genre_by_movie.get(cand, set())
        best = 0.0
        total = 0.0
        denom = 0.0
        for idx, seed in enumerate(reversed(recent), start=1):
            weight = 1.0 / math.sqrt(idx)
            sim = _jaccard(cg, genre_by_movie.get(seed, set()))
            best = max(best, sim)
            total += sim * weight
            denom += weight
        mean_sim = total / denom if denom else 0.0
        scores[cand] = 0.65 * best + 0.35 * mean_sim
    return scores


def _cf_scores(seen: list[int], neighbors: dict[str, list[list[float]]], seen_set: set[int]) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for idx, seed in enumerate(reversed(seen[-30:]), start=1):
        recency = 1.0 / math.sqrt(idx)
        for other, sim in neighbors.get(str(seed), []):
            other_id = int(other)
            if other_id not in seen_set:
                scores[other_id] += float(sim) * recency
    if not scores:
        return {}
    maximum = max(scores.values()) or 1.0
    return {movie: value / maximum for movie, value in scores.items()}


def _metric_for_ranked(ranked: list[int], target: int, k: int = 10) -> tuple[float, float, float]:
    top = ranked[:k]
    if target not in top:
        return 0.0, 0.0, 0.0
    rank = top.index(target) + 1
    return 1.0, 1.0, 1.0 / math.log2(rank + 1)


def _evaluate_model(
    held_out: dict[int, int],
    train_histories: dict[int, list[int]],
    neighbors: dict[str, list[list[float]]],
    genre_by_movie: dict[int, set[str]],
    popularity_norm: dict[int, float],
    popularity_ids: list[int],
    mode: str,
    weights: tuple[float, float, float] = (0.55, 0.25, 0.20),
) -> dict[str, float | int]:
    hits = recall = ndcg = 0.0
    evaluated = 0
    for user, target in held_out.items():
        seen = train_histories.get(user, [])
        seen_set = set(seen)
        # Retrieval pool combines CF candidates with broad popularity candidates.
        cf = _cf_scores(seen, neighbors, seen_set)
        candidates = set(cf) | {m for m in popularity_ids[:350] if m not in seen_set}
        content = _content_scores(seen, genre_by_movie, candidates)

        if mode == "popularity":
            scored = [(m, popularity_norm.get(m, 0.0)) for m in candidates]
        elif mode == "collaborative":
            scored = [(m, cf.get(m, 0.0)) for m in candidates]
        elif mode == "content":
            scored = [(m, content.get(m, 0.0)) for m in candidates]
        else:
            w_cf, w_content, w_pop = weights
            scored = [
                (m, w_cf * cf.get(m, 0.0) + w_content * content.get(m, 0.0) + w_pop * popularity_norm.get(m, 0.0))
                for m in candidates
            ]
        scored.sort(key=lambda x: x[1], reverse=True)
        h, r, n = _metric_for_ranked([m for m, _ in scored], target)
        hits += h; recall += r; ndcg += n; evaluated += 1
    denom = max(1, evaluated)
    return {
        "hit_rate_at_10": round(hits / denom, 4),
        "recall_at_10": round(recall / denom, 4),
        "ndcg_at_10": round(ndcg / denom, 4),
        "evaluated_users": evaluated,
    }


def train_model(ratings_rows: list[dict[str, str]], movies_rows: list[dict[str, str]]) -> dict:
    """Train/evaluate multiple recommenders on a per-user temporal holdout.

    Explicit MovieLens ratings >= 4.0 are treated as positive implicit feedback.
    The final ranker is a learned linear hybrid: its CF/content/popularity weights
    are selected on a validation subset to maximize NDCG@10, then reported on the
    remaining evaluation users. This is intentionally lightweight so it trains
    locally without a separate ML framework.
    """
    positives_by_user: dict[int, list[tuple[int, int]]] = defaultdict(list)
    rating_count = len(ratings_rows)
    all_users: set[int] = set()
    all_movies: set[int] = set()
    positive_count = 0
    raw_popularity = Counter()
    for row in ratings_rows:
        user = int(row["userId"]); movie = int(row["movieId"]); rating = float(row["rating"]); ts = int(row["timestamp"])
        all_users.add(user); all_movies.add(movie)
        if rating >= 4.0:
            positives_by_user[user].append((ts, movie)); positive_count += 1; raw_popularity[movie] += 1

    train_histories: dict[int, list[int]] = {}
    held_out: dict[int, int] = {}
    supports = Counter()
    for user, pairs in positives_by_user.items():
        pairs.sort()
        movies = [movie for _, movie in pairs]
        if len(movies) >= 3:
            held_out[user] = movies[-1]; train = movies[:-1]
        else:
            train = movies
        train = train[-50:]
        train_histories[user] = train
        supports.update(set(train))

    pair_counts: dict[int, Counter] = defaultdict(Counter)
    for movies in train_histories.values():
        unique = list(dict.fromkeys(movies))
        for i, left in enumerate(unique):
            for right in unique[i + 1:]:
                pair_counts[left][right] += 1; pair_counts[right][left] += 1

    neighbors: dict[str, list[list[float]]] = {}
    for movie, counter in pair_counts.items():
        scored = []
        for other, co_count in counter.items():
            denom = math.sqrt(max(1, supports[movie]) * max(1, supports[other]))
            similarity = co_count / denom
            if similarity > 0:
                scored.append((other, similarity))
        scored.sort(key=lambda x: x[1], reverse=True)
        neighbors[str(movie)] = [[other, round(sim, 6)] for other, sim in scored[:60]]

    popularity = [[movie, count] for movie, count in supports.most_common(500)]
    max_pop = max(supports.values(), default=1)
    popularity_norm = {movie: math.log1p(count) / math.log1p(max_pop) for movie, count in supports.items()}
    popularity_ids = [int(movie) for movie, _ in popularity]
    genre_by_movie = _genre_map(movies_rows)

    # Deterministic user split: tune hybrid weights on ~25%, report on the rest.
    user_ids = sorted(held_out)
    validation_users = {u for i, u in enumerate(user_ids) if i % 4 == 0}
    validation_holdout = {u: held_out[u] for u in validation_users}
    test_holdout = {u: held_out[u] for u in user_ids if u not in validation_users}
    if not test_holdout:
        test_holdout = held_out

    best_weights = (0.55, 0.25, 0.20)
    best_ndcg = -1.0
    # Coarse but real learned weight search. Sums to 1.0.
    for w_cf_i in range(2, 9):
        w_cf = w_cf_i / 10
        for w_content_i in range(1, 8):
            w_content = w_content_i / 10
            w_pop = round(1.0 - w_cf - w_content, 10)
            if w_pop < 0 or w_pop > 0.6:
                continue
            metrics = _evaluate_model(validation_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "hybrid", (w_cf, w_content, w_pop))
            if float(metrics["ndcg_at_10"]) > best_ndcg:
                best_ndcg = float(metrics["ndcg_at_10"]); best_weights = (w_cf, w_content, w_pop)

    fixed_weights = (0.55, 0.25, 0.20)
    comparisons = {
        "popularity": _evaluate_model(test_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "popularity"),
        "collaborative": _evaluate_model(test_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "collaborative"),
        "content_based": _evaluate_model(test_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "content"),
        "hybrid": _evaluate_model(test_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "hybrid", fixed_weights),
        "learned_hybrid": _evaluate_model(test_holdout, train_histories, neighbors, genre_by_movie, popularity_norm, popularity_ids, "hybrid", best_weights),
    }
    winner = max(comparisons, key=lambda name: float(comparisons[name]["ndcg_at_10"]))

    return {
        "dataset": "MovieLens latest-small",
        "stats": {
            "movies": len(all_movies), "ratings": rating_count, "users": len(all_users),
            "positive_ratings": positive_count, "trained_items": len(neighbors),
        },
        "metrics": comparisons["learned_hybrid"],
        "model_comparison": comparisons,
        "winner": winner,
        "learned_weights": {
            "collaborative": round(best_weights[0], 2),
            "content": round(best_weights[1], 2),
            "popularity": round(best_weights[2], 2),
        },
        "fixed_weights": {"collaborative": fixed_weights[0], "content": fixed_weights[1], "popularity": fixed_weights[2]},
        "neighbors": neighbors,
        "popularity": popularity,
        "popularity_norm": {str(k): round(v, 6) for k, v in popularity_norm.items()},
        "movie_genres": {str(k): sorted(v) for k, v in genre_by_movie.items()},
        "user_histories": {str(user): movies for user, movies in train_histories.items()},
    }
