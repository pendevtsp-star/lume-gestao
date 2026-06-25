$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
  Copy-Item ".env.clinic.example" ".env"
  Write-Host "Arquivo .env criado a partir de .env.clinic.example."
  Write-Host "Edite o .env, troque senhas e informe o IP da maquina da clinica antes de rodar novamente."
  exit 0
}

docker compose up --build -d
docker compose ps

Write-Host ""
Write-Host "Lume Gestao iniciado."
Write-Host "Acesse nesta maquina: http://127.0.0.1:8000"
Write-Host "Na rede local, acesse pelo IP configurado no .env: http://IP_DA_MAQUINA_DA_CLINICA:8000"
