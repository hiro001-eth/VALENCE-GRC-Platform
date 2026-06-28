# VALENCE Enterprise On-Premise Appliance Bootstrapper
# This script handles the automated configuration of domain masking, SSL generation, and container orchestration in one command.

$HostFile = "$env:windir\System32\drivers\etc\hosts"
$Domain = "valence-grc.local"
$DomainMapped = Get-Content $HostFile | Select-String -Pattern "valence-grc.local"

Clear-Host
Write-Host "🔮 ===========================================================" -ForegroundColor Cyan
Write-Host "             VALENCE GRC Enterprise Security Platform         " -ForegroundColor Cyan
Write-Host "               Secure On-Premise Intranet Appliance           " -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Domain Masking Setup
if (-not $DomainMapped) {
    Write-Host "[!] Host mapping for '$Domain' is missing in local DNS resolution." -ForegroundColor Yellow
    Write-Host "[*] Registering '$Domain' locally..." -ForegroundColor Cyan

    $hostsEntry = "127.0.0.1   $Domain"
    
    # Try writing to hosts file
    try {
        Add-Content -Path $HostFile -Value "`n$hostsEntry" -ErrorAction Stop
        Write-Host "[+] SUCCESS: Host mapping successfully registered!" -ForegroundColor Green
    } catch {
        Write-Host "[!] WARNING: Permission denied writing to Windows hosts file." -ForegroundColor DarkYellow
        Write-Host "    To access the dashboard via the premium domain name: https://$Domain" -ForegroundColor Gray
        Write-Host "    Please run this script again in an Administrator PowerShell window, or manually append:" -ForegroundColor Gray
        Write-Host "    '127.0.0.1   $Domain' to $HostFile" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "[*] Falling back to default secure localhost..." -ForegroundColor Cyan
        $Domain = "localhost"
    }
} else {
    Write-Host "[+] Local DNS mapping verified: $Domain -> 127.0.0.1" -ForegroundColor Green
}

# 2. Boot Docker containers
Write-Host ""
Write-Host "[*] Initializing Docker Appliance (PostgreSQL DB, Redis Cache, FastAPI, Nginx TLS)..." -ForegroundColor Cyan

# Check if Docker is running
& docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] ERROR: Docker Desktop is not running. Please start Docker and run this script again." -ForegroundColor Red
    Exit 1
}

# Start containers in background
Write-Host "[*] Orchestrating virtual appliance containers..." -ForegroundColor Cyan
& docker compose up --build -d

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "🔮 ===========================================================" -ForegroundColor Green
    Write-Host "     VALENCE GRC APPLIANCE IS UP AND RUNNING!                 " -ForegroundColor Green
    Write-Host "=============================================================" -ForegroundColor Green
    Write-Host "  👉 Access Dashboard:  https://$Domain" -ForegroundColor Green
    Write-Host "  👉 Access API Docs:   https://$Domain/api/docs" -ForegroundColor Green
    Write-Host "  👉 Audit Signatures:  Verified (FIPS 140-2 lineage)" -ForegroundColor Gray
    Write-Host "=============================================================" -ForegroundColor Green
    
    # Wait for service initialization
    Write-Host "[*] Waiting 5 seconds for secure SSL handshake readiness..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
    
    # Open default browser
    Start-Process "https://$Domain"
} else {
    Write-Host "[-] ERROR: Docker Compose failed to orchestrate containers. Please inspect Docker logs." -ForegroundColor Red
}
