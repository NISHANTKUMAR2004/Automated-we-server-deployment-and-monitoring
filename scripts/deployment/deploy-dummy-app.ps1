param(
    [ValidateSet("portfolio", "cloud-console", "storefront")]
    [string]$Application = "portfolio",
    [string]$ApiUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"
try {
    $result = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/deployment/apps/$Application" -TimeoutSec 120
    if (-not $result.deployed) {
        throw "Puppet returned without a successful HTTP verification."
    }

    Write-Host "Puppet deployment succeeded."
    Write-Host "Application: $($result.name)"
    Write-Host "HTTP status: $($result.status_code)"
    Write-Host "Demo URL: $($result.url)"
    Write-Host "If the public URL is blocked, use the SSH tunnel instructions in README.md."
}
catch {
    Write-Error "Deployment failed: $($_.Exception.Message)"
    Write-Host "Make sure the local API is running at $ApiUrl and EC2 SSH access works."
    exit 1
}
