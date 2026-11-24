# NEXUS Phase 5.2 — Multilingual Semantic + Voice Discovery

Phase 5.2 extends the working Phase 5.1 stack with:

- Auto-clear after successful text/voice search, plus manual clear button.
- English and Telugu voice modes (`en-US` / `te-IN`) using browser speech recognition.
- Optional TMDB Telugu catalog ingestion using `with_original_language=te`.
- Cross-catalog PostgreSQL metadata with source-aware MovieLens vs TMDB signals.
- Telugu catalog rail on the consumer homepage when TMDB data is loaded.
- TMDB posters/backdrops for enriched titles.
- Qdrant indexing across MovieLens + TMDB catalog rows.
- Telugu deterministic query normalization for common genres before Phase 6 LLM agents.
- Language filter (`All / English / తెలుగు`) in semantic discovery.
- Search Debugger traces normalized query, language, Qdrant candidates, rejections and final ranking.
- Windows `.cmd` loader to avoid PowerShell unsigned-script execution-policy problems.

## Run

```powershell
cd "C:\Users\saith\Desktop\projects\nexus-phase5.2"
docker compose up --build
```

Open:

- Consumer app: http://localhost:3000
- System Lab: http://localhost:3000/system-lab
- FastAPI docs: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

## Load MovieLens

```powershell
docker compose exec backend python -m app.scripts.import_movielens
```

## Optional: add Telugu movies from TMDB

TMDB requires an API Read Access Token.

1. Copy `.env.example` to `.env`.
2. Add your token to:

```env
TMDB_BEARER_TOKEN=YOUR_TOKEN_HERE
```

3. Restart the stack so Docker Compose reads the new environment:

```powershell
docker compose down
docker compose up --build
```

4. Import Telugu movies:

```powershell
docker compose exec backend python -m app.scripts.import_tmdb_telugu
```

Default: 15 TMDB discover pages (up to about 300 returned items before deduplication). Override for a run:

```powershell
docker compose exec backend python -m app.scripts.import_tmdb_telugu --pages 25
```

## Rebuild Qdrant after catalog changes

```powershell
docker compose exec backend python -m app.scripts.build_semantic_index
```

Every time you add/rebuild the TMDB catalog, rebuild the Qdrant index so new movies are searchable.

## One-command Windows loader

After adding the optional TMDB token you can run:

```powershell
.\load-phase52.cmd
```

Unlike `.ps1`, this does not depend on PowerShell script execution policy.

## Test queries

English:

- `funny Telugu movie`
- `Telugu action thriller`
- `horror but not comedy`
- `dark psychological thriller`

Telugu mode:

- `తెలుగు కామెడీ సినిమా`
- `తెలుగు యాక్షన్ సినిమా`
- `ప్రేమ సినిమా`
- `హారర్ సినిమా`

Phase 5.2 uses deterministic Telugu genre normalization plus English-language semantic embeddings. Phase 6 will add LLM/agent-based query interpretation and translation for richer open-ended Telugu requests.
