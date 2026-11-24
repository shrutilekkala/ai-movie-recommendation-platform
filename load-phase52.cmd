@echo off
setlocal

echo [1/3] Importing MovieLens + training recommender...
docker compose exec backend python -m app.scripts.import_movielens
if errorlevel 1 goto :error

echo.
echo [2/3] Importing Telugu catalog from TMDB (requires TMDB_BEARER_TOKEN in .env)...
docker compose exec backend python -m app.scripts.import_tmdb_telugu
if errorlevel 1 (
  echo TMDB import did not complete. You can add the token later and run:
  echo docker compose exec backend python -m app.scripts.import_tmdb_telugu
  echo Continuing with MovieLens-only indexing...
)

echo.
echo [3/3] Building Qdrant semantic index...
docker compose exec backend python -m app.scripts.build_semantic_index
if errorlevel 1 goto :error

echo.
echo Phase 5.2 data load complete.
echo Open http://localhost:3000 and http://localhost:3000/system-lab
exit /b 0

:error
echo.
echo Phase 5.2 loader stopped because a required step failed.
exit /b 1
