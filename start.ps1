# Sets up the virtual environment if needed, then starts the dev server.
# Usage:  .\start.ps1        (add -Seed to load the demo content first)

param([switch]$Seed)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env with a fresh secret key..."
    $secret = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content ".env.example") -replace "^SECRET_KEY=$", "SECRET_KEY=$secret" |
        Set-Content ".env" -Encoding utf8
}

if ($Seed) {
    Write-Host "Seeding demo content..."
    .\.venv\Scripts\python.exe seed.py
}

Write-Host ""
Write-Host "  Public site  http://127.0.0.1:8000"
Write-Host "  Admin portal http://127.0.0.1:8000/admin"
Write-Host ""

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
