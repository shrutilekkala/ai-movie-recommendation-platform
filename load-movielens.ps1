Write-Host "NEXUS Phase 3 - importing official MovieLens latest-small..." -ForegroundColor Green
docker compose exec backend python -m app.scripts.import_movielens
