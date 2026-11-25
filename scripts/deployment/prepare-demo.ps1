$ErrorActionPreference = "Stop"
$port = 8001
$apiUrl = "http://127.0.0.1:$port"
$apiReady = $false

try {
    $health = Invoke-RestMethod -Uri "$apiUrl/api/health" -TimeoutSec 3
    $schema = Invoke-RestMethod -Uri "$apiUrl/openapi.json" -TimeoutSec 3
    $paths = $schema.paths.PSObject.Properties.Name
    $appPath = $schema.paths.PSObject.Properties["/api/deployment/apps/{app_id}"].Value
    $apiReady = $health.status -eq "healthy" `
        -and $paths -contains "/api/dashboard" `
        -and $paths -contains "/api/deployment/upload" `
        -and $null -ne $appPath.delete
} catch {
    $apiReady = $false
}

if ($apiReady) {
    Write-Host "Current project API is already running."
    exit 0
}

$processIds = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $processIds) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if ($process.CommandLine -match "uvicorn backend\.app\.main:app") {
        Write-Host "Stopping stale project API process $($process.ProcessId)..."
        Stop-Process -Id $process.ProcessId -Force
        Start-Sleep -Seconds 1
        continue
    }

    Write-Error "Port $port is occupied by unrelated process $($process.Name) (PID $($process.ProcessId)). Close it and retry."
    exit 1
}
