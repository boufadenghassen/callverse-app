<#
  Starts everything orqestra needs for a demo, on this machine: the agents (port 8000), the emotion model (port 8001) and the web app (port 8080).

    .\start-all.ps1              start the three services and open the browser
    .\start-all.ps1 -Reset       first restart the clock of the complaint cases (their deadlines run in real time, so a demo prepared yesterday shows them all late)
    .\start-all.ps1 -Clean       first start from the clean demo state: the complaint, sales and quality stores (what your rehearsals and the browser tests added to them) are moved to
                                 services\agents\data\backup-<date> (nothing is deleted) and recreated with their simulated history. Use it just before a presentation.
    .\start-all.ps1 -Stop        stop the three services
    .\start-all.ps1 -NoBrowser   do not open the browser

  Needs Node.js 22 or newer and the Python environment next to this folder (..\venv). The first start loads the speech and emotion models and can take a minute.
  The demo password is CALLVERSE_DEMO_PASSWORD if you set it, else demo-password-123. For a LOCAL demo only.
#>
param([switch]$Reset, [switch]$Clean, [switch]$Stop, [switch]$NoBrowser)

$root = $PSScriptRoot
$agents = Join-Path $root "services\agents"
$py = Join-Path $root "..\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
$logs = Join-Path $env:TEMP "orqestra-logs"
New-Item -ItemType Directory -Force $logs | Out-Null

function Test-Port($port) {
    $c = New-Object Net.Sockets.TcpClient
    try { $c.Connect("127.0.0.1", $port); $true } catch { $false } finally { $c.Close() }
}
function Stop-Port($port) {
    $p = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
    if ($p) { Stop-Process -Id $p -Force; Write-Host "stopped the service on port $port"; Start-Sleep -Seconds 1 }
    # Get-NetTCPConnection does not list the port on every machine, and a service left running would keep serving the old code
    if (Test-Port $port) {
        $service = @{ 8000 = 'uvicorn.*main:app'; 8001 = 'uvicorn.*serve:app'; 8080 = 'dist[/\\]main\.js' }[$port]
        Get-CimInstance Win32_Process -Filter "name='python.exe' or name='node.exe'" | Where-Object { $_.CommandLine -match $service } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "stopped the service on port $port" }
        Start-Sleep -Seconds 2
    }
    if (Test-Port $port) { Write-Host "Port $port is still in use by another program: close it, then start again." -ForegroundColor Red; exit 1 }
}
function Wait-Up($name, $url, $seconds) {
    $until = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $until) {
        try { if ((Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { Write-Host "  $name is up" -ForegroundColor Green; return $true } } catch { }
        Start-Sleep -Seconds 2
    }
    Write-Host "  $name did not answer in $seconds s (log: $logs)" -ForegroundColor Red
    return $false
}

if ($Stop) { 8000, 8001, 8080 | ForEach-Object { Stop-Port $_ }; exit 0 }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-Host "Node.js is not installed. Install it from https://nodejs.org first." -ForegroundColor Red; exit 1 }
if (-not $py) { Write-Host "No Python found (expected ..\venv\Scripts\python.exe)." -ForegroundColor Red; exit 1 }

8000, 8001, 8080 | ForEach-Object { Stop-Port $_ }
if ($Reset) {
    $db = Join-Path $agents "data\complaints.db"
    if (Test-Path $db) { Remove-Item $db -Force; Write-Host "the complaint cases will be recreated with fresh deadlines" }
}
if ($Clean) {
    $data = Join-Path $agents "data"
    $backup = Join-Path $data ("backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    $stores = Get-ChildItem $data -File | Where-Object { $_.Name -match '^((complaints|sales|quality|training)\.db|scenarios\.jsonl)' }
    if ($stores) {
        New-Item -ItemType Directory -Force $backup | Out-Null
        $stores | Move-Item -Destination $backup
        Write-Host "the complaint, sales, quality and training stores were moved to $backup; they are recreated with their simulated history"
    }
}

Write-Host "Building the web app..."
Push-Location (Join-Path $root "app")
if (-not (Test-Path node_modules)) { npm ci }
npm run build | Out-Null
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host "The build failed." -ForegroundColor Red; exit 1 }
Pop-Location

if (-not $env:CALLVERSE_DEMO_PASSWORD) { $env:CALLVERSE_DEMO_PASSWORD = "demo-password-123" }
$env:CALLVERSE_COOKIE_SECURE = "false"      # plain http://localhost
$env:AGENTS_MODE = "http"                   # the web app calls the real agents
$env:SCENARIO_STORE_PATH = Join-Path $agents "data\scenarios.jsonl"   # training scenarios survive a restart

Write-Host "Starting the services (logs in $logs)..."
Start-Process $py -ArgumentList "-m", "uvicorn", "main:app", "--port", "8000" -WorkingDirectory $agents -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "agents.out.log") -RedirectStandardError (Join-Path $logs "agents.err.log")
$weights = Join-Path $root "models\registry\emotion_wavlm_ft_full_aug2.pt"
if (Test-Path $weights) {
    Start-Process $py -ArgumentList "-m", "uvicorn", "serve:app", "--app-dir", "models/src", "--port", "8001" -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "emotion.out.log") -RedirectStandardError (Join-Path $logs "emotion.err.log")
} else {
    Write-Host "  (no emotion model weights found: the Call review page and voice tone are off, everything else works)" -ForegroundColor Yellow
}
Start-Process "node" -ArgumentList "dist/main.js" -WorkingDirectory (Join-Path $root "app") -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "web.out.log") -RedirectStandardError (Join-Path $logs "web.err.log")

$ok = (Wait-Up "the agents" "http://localhost:8000/health" 150)
if (Test-Path $weights) { $ok = (Wait-Up "the emotion model" "http://localhost:8001/health" 150) -and $ok }
$ok = (Wait-Up "the web app" "http://localhost:8080/actuator/health" 60) -and $ok
if (-not $ok) { exit 1 }

Write-Host ""
Write-Host "orqestra is running at http://localhost:8080" -ForegroundColor Green
Write-Host "Sign in as: admin (everything), yasmine (client), karim (advisor), sana (workforce),"
Write-Host "            nour (quality), amine (complaints), rim (training), leila (sales)"
Write-Host "Password: $env:CALLVERSE_DEMO_PASSWORD      Stop everything with: .\start-all.ps1 -Stop"
if (-not $NoBrowser) { Start-Process "http://localhost:8080" }
