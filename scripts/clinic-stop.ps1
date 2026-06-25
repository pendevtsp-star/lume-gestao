$ErrorActionPreference = "Stop"

docker compose down
Write-Host "Lume Gestao parado. Os dados do PostgreSQL permanecem salvos no volume Docker."
