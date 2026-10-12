<#
  Starts orqestra (NestJS) on http://localhost:8080 and opens it in the browser. For a LOCAL demo only.
  Needs Node.js 22 or newer. Set CALLVERSE_DEMO_PASSWORD (12+ characters) to choose your own demo password.
#>
Set-Location $PSScriptRoot

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js is not installed. Install it from https://nodejs.org first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path node_modules)) { Write-Host "Installing packages..."; npm ci }
Write-Host "Building..."
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "The build failed." -ForegroundColor Red; exit 1 }

if (-not $env:CALLVERSE_DEMO_PASSWORD) { $env:CALLVERSE_DEMO_PASSWORD = "demo-password-123" }
$env:CALLVERSE_COOKIE_SECURE = "false"   # plain http://localhost

Start-Job { Start-Sleep 3; Start-Process "http://localhost:8080" } | Out-Null
Write-Host "orqestra is starting at http://localhost:8080 (Ctrl+C to stop)" -ForegroundColor Green
Write-Host "Sign in as: admin (everything), yasmine (client), karim (advisor), sana (workforce),"
Write-Host "            nour (quality), amine (complaints), rim (training), leila (sales)"
Write-Host "Password: the value of CALLVERSE_DEMO_PASSWORD, or the demo default if you did not set one."
node dist/main.js
