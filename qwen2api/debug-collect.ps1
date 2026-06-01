Write-Host "=" * 56
Write-Host "  Qwen2OpenAI Debug Info Collector"
Write-Host "=" * 56
Write-Host ""
Write-Host "Timestamp: $(Get-Date)"
Write-Host "System:    $env:COMPUTERNAME"
Write-Host "OS:        $([Environment]::OSVersion)"
Write-Host "PowerShell:$($PSVersionTable.PSVersion)"
Write-Host ""

Write-Host "===== Python ====="
python --version 2>&1
pip --version 2>&1
Write-Host ""

Write-Host "===== Project State ====="
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match "^QWEN_TOKENS=") {
            Write-Host "QWEN_TOKENS=***redacted***"
        } elseif ($_ -match "^API_KEY=") {
            Write-Host "API_KEY=***redacted***"
        } else {
            Write-Host $_
        }
    }
} else {
    Write-Host ".env: NOT FOUND"
}
Write-Host ""

Write-Host "===== Port Check ====="
netstat -ano | Select-String ":8000 "
Write-Host ""

Write-Host "===== Server Health ====="
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
    Write-Host ($health | ConvertTo-Json -Compress)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "===== Token Status ====="
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/models" -TimeoutSec 5
    Write-Host ($status | ConvertTo-Json -Compress)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "===== Debug Endpoint ====="
try {
    $debug = Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug" -TimeoutSec 5
    Write-Host ($debug | ConvertTo-Json -Compress)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "===== Directory Structure ====="
Get-ChildItem -Path $PSScriptRoot -Recurse -Depth 2 | Where-Object { $_.Name -notmatch '__pycache__' } | ForEach-Object {
    $prefix = if ($_.PSIsContainer) { "[DIR]" } else { "     " }
    $size = if ($_.PSIsContainer) { "" } else { ("{0,8} bytes" -f $_.Length) }
    Write-Host ("$prefix $size $($_.FullName.Substring($PSScriptRoot.Length+1))")
}
Write-Host ""

Write-Host "=" * 56
Write-Host "  Done."
Write-Host "=" * 56
