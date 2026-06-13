<#
.SYNOPSIS
  Start the full smistress stack for local all-in-one development on Windows.

.DESCRIPTION
  Brings up everything needed to run smistress on one machine, in order:
    1. Docker infra (Postgres + FalkorDB) via docker compose
    2. Database migrations (alembic upgrade head)
    3. Backend API   -> http://localhost:8000   (uvicorn, in its own window)
    4. Frontend (PWA) -> http://localhost:5173   (vite, in its own window)
    5. Heartbeat agent -> POSTs /llm/heartbeat so the Mistress shows "online"

  Two Windows-specific reasons this script exists (see README "Windows notes"):
    * The backend MUST run under asyncio's SelectorEventLoop. uvicorn picks that
      only for subprocess launches, so we always pass --reload. A plain
      `uvicorn app.main:app` uses ProactorEventLoop and every DB call 500s.
    * Availability is heartbeat-driven. Without the agent the app shows the
      Mistress as "away" even when Ollama is up; the README quickstart does not
      start it.

  The three long-running processes each open in their own PowerShell window so
  you can read their logs and Ctrl+C them individually. Run .\stop.ps1 to stop
  everything at once.

.PARAMETER NoMigrate
  Skip `alembic upgrade head` (use when the schema is already current).

.PARAMETER NoDocker
  Skip `docker compose up -d` (use when Postgres/FalkorDB are already running).

.EXAMPLE
  .\start.ps1
#>
[CmdletBinding()]
param(
  [switch]$NoMigrate,
  [switch]$NoDocker
)

# NOTE: deliberately NOT 'Stop'. Under 'Stop', any native command that writes to
# stderr (docker warnings, `docker compose` status lines, uv/alembic INFO logs)
# is turned into a terminating NativeCommandError. We gate native commands on
# $LASTEXITCODE instead, and mark the cmdlets we care about with -ErrorAction Stop.
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!! $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "!!! $msg" -ForegroundColor Red; exit 1 }

# --- .env -------------------------------------------------------------------
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
  Info 'Creating .env from .env.example'
  Copy-Item (Join-Path $root '.env.example') $envFile -ErrorAction Stop
}

# The heartbeat agent probes the same LLM endpoint the backend uses. Read it
# from .env when present so this script honours your provider/model choice.
$llmBaseUrl = 'http://localhost:11434/v1'
$match = Select-String -Path $envFile -Pattern '^\s*SMISTRESS_LLM_BASE_URL\s*=\s*(.+?)\s*$' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($match) { $llmBaseUrl = $match.Matches[0].Groups[1].Value }

# --- 1. Docker infra --------------------------------------------------------
if (-not $NoDocker) {
  Info 'Checking Docker daemon'
  # Run through cmd so docker's stdout/stderr never reach PowerShell; we only
  # care about the exit code.
  & cmd /c "docker info >NUL 2>&1"
  if ($LASTEXITCODE -ne 0) {
    Fail 'Docker daemon is not reachable. Start Docker Desktop and re-run, or pass -NoDocker.'
  }

  Info 'Starting Postgres + FalkorDB (docker compose up -d)'
  Push-Location $root
  try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed.' }
  } finally { Pop-Location }

  Info 'Waiting for Postgres to accept connections'
  $ready = $false
  foreach ($i in 1..30) {
    Push-Location $root
    try { & cmd /c "docker compose exec -T postgres pg_isready -U smistress >NUL 2>&1" } finally { Pop-Location }
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
  }
  if (-not $ready) { Fail 'Postgres did not become ready in time.' }
}

# --- 2. Migrations ----------------------------------------------------------
if (-not $NoMigrate) {
  Info 'Applying database migrations (alembic upgrade head)'
  Push-Location $backend
  try {
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail 'Migrations failed.' }
  } finally { Pop-Location }
}

# --- 3-5. Long-running processes, each in its own window --------------------
function Start-DevWindow($title, $workdir, $command) {
  # -NoExit keeps the window open so logs stay visible and Ctrl+C works.
  $inner = "`$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$workdir'; $command"
  Start-Process powershell -ArgumentList '-NoExit', '-Command', $inner | Out-Null
}

Info 'Launching backend (uvicorn --reload, :8000)'
Start-DevWindow 'smistress backend' $backend 'uv run uvicorn app.main:app --reload --port 8000'

Info 'Launching frontend (vite, :5173)'
Start-DevWindow 'smistress frontend' $frontend 'npm run dev'

Info 'Launching heartbeat agent'
$hbCmd = "`$env:SMISTRESS_VPS_URL='http://localhost:8000'; " +
         "`$env:SMISTRESS_LLM_BASE_URL='$llmBaseUrl'; " +
         "`$env:SMISTRESS_HEARTBEAT_INTERVAL='30'; " +
         'uv run python -m app.agent.heartbeat'
Start-DevWindow 'smistress heartbeat' $backend $hbCmd

Write-Host ''
Info 'smistress is starting up. Three windows opened (backend / frontend / heartbeat).'
Write-Host '    App:      http://localhost:5173'
Write-Host '    API:      http://localhost:8000  (docs at /docs)'
Write-Host '    Stop all: .\stop.ps1'
Write-Host ''
Write-Host '    The frontend reads availability on page load only, so once the' -ForegroundColor DarkGray
Write-Host '    heartbeat window logs "heartbeat sent", reload the app to see the' -ForegroundColor DarkGray
Write-Host '    Mistress come online.' -ForegroundColor DarkGray
