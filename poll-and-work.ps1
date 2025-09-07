[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location -Path $PSScriptRoot

mkdir -Force .\logs | Out-Null
mkdir -Force .\storage\articles | Out-Null
mkdir -Force .\storage\queue | Out-Null

function Log([string]$m) {
  $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  Add-Content -LiteralPath .\logs\runner.log -Value ("$ts  $m")
}


function Run-Step([string]$name,[string]$cmd) {
  Log ("▶ " + $name + ": " + $cmd)   # ← фикс строки с двоеточием
  & powershell -NoProfile -Command $cmd 1>> .\logs\runner.log 2>> .\logs\runner.log
  $code = $LASTEXITCODE
  if ($code -ne 0) { Log ("✗ " + $name + " failed (" + $code + ")"); throw ($name + " failed: exit=" + $code) }
  else { Log ("✓ " + $name + " ok") }
}

if (-not $env:GOOGLE_SERVICE_ACCOUNT_JSON -or -not (Test-Path $env:GOOGLE_SERVICE_ACCOUNT_JSON)) { Log ("SA json missing: '" + $env:GOOGLE_SERVICE_ACCOUNT_JSON + "'"); throw "service account json missing" }
if (-not $env:SPREADSHEET_ID) { Log "SPREADSHEET_ID not set"; throw "spreadsheet id missing" }

while ($true) {
  try {
    Run-Step "poll" 'python main.py poll'
    Start-Sleep -Seconds 5
    Run-Step "work" 'python main.py work --worker-id scheduler'
    # Run-Step "flush-queue" 'python main.py flush-queue'  # если добавишь команду
  } catch { Log ("ERR: " + ($_.Exception | Out-String)) }
  Start-Sleep -Seconds 300
}
