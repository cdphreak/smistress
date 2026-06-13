<#
.SYNOPSIS
  Stop the local smistress stack started by start.ps1.

.DESCRIPTION
  Stops the three dev processes (backend on :8000, frontend on :5173, and the
  heartbeat agent) and then stops the Docker containers (without removing the
  data volume). Pass -KeepDocker to leave Postgres/FalkorDB running, or -Down to
  fully remove the containers (data volume is still preserved; use
  `docker compose down -v` by hand to wipe data).

.EXAMPLE
  .\stop.ps1
#>
[CmdletBinding()]
param(
  [switch]$KeepDocker,
  [switch]$Down
)

$ErrorActionPreference = 'SilentlyContinue'
$root = $PSScriptRoot

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Stop-Port($port, $label) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if (-not $conns) { Info "$label (:$port) not running"; return }
  foreach ($procId in ($conns.OwningProcess | Select-Object -Unique)) {
    try { Stop-Process -Id $procId -Force -ErrorAction Stop; Info "Stopped $label (:$port, PID $procId)" } catch {}
  }
}

# Backend and frontend are identified by their listening ports.
Stop-Port 8000 'backend'
Stop-Port 5173 'frontend'

# The heartbeat agent has no port; match it by command line.
$hb = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -like '*app.agent.heartbeat*' }
if ($hb) {
  foreach ($p in $hb) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Info "Stopped heartbeat agent (PID $($p.ProcessId))" } catch {} }
} else {
  Info 'heartbeat agent not running'
}

if (-not $KeepDocker) {
  Push-Location $root
  try {
    if ($Down) { Info 'docker compose down (containers removed, data volume kept)'; docker compose down }
    else { Info 'docker compose stop (containers + data preserved)'; docker compose stop }
  } finally { Pop-Location }
}

Info 'smistress stopped.'
