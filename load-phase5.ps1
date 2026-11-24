Write-Host "NEXUS Phase 5 - loading MovieLens and building semantic index" -ForegroundColor Green
docker compose exec backend python -m app.scripts.import_movielens
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose exec backend python -m app.scripts.build_semantic_index
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Phase 5 data + semantic index ready. Open http://localhost:3000" -ForegroundColor Green
