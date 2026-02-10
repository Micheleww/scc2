# DNS Verification Script for mcp.timquant.tech
# PowerShell Version

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DNS Verification - mcp.timquant.tech" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$DOMAIN = "mcp.timquant.tech"
$EXPECTED_IP = "13.229.100.10"
$LOG_FILE = "dns_verification_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').txt"

Write-Host "[1/4] Checking DNS resolution for $DOMAIN..." -ForegroundColor Yellow
Write-Host ""

# Check using nslookup
try {
    $result = nslookup $DOMAIN 2>&1
    $result | Out-File -FilePath $LOG_FILE -Encoding utf8
    Write-Host "DNS resolution completed using nslookup." -ForegroundColor Green
}
catch {
    Write-Host "nslookup failed: $_" -ForegroundColor Red
}

# Check using Resolve-DnsName
Write-Host "[2/4] Checking DNS resolution using Resolve-DnsName..." -ForegroundColor Yellow
try {
    $dnsResult = Resolve-DnsName -Name $DOMAIN -DnsOnly -ErrorAction Stop | 
        Select-Object -First 1 -ExpandProperty AddressList,IPAddressToString
    if ($dnsResult) {
        $ip = $dnsResult.IPAddressToString
        if ($ip -eq $EXPECTED_IP) {
            Write-Host "[SUCCESS] DNS correctly resolves to $EXPECTED_IP" -ForegroundColor Green
            Add-Content -Path $LOG_FILE -Value "[SUCCESS] DNS correctly resolves to $EXPECTED_IP"
        } else {
            Write-Host "[FAILED] DNS resolves to $ip (expected: $EXPECTED_IP)" -ForegroundColor Red
            Add-Content -Path $LOG_FILE -Value "[FAILED] DNS resolves to $ip (expected: $EXPECTED_IP)"
        }
    } else {
        Write-Host "[FAILED] DNS resolution failed" -ForegroundColor Red
        Add-Content -Path $LOG_FILE -Value "[FAILED] DNS resolution failed"
    }
}
catch {
    Write-Host "Resolve-DnsName failed: $_" -ForegroundColor Red
    Add-Content -Path $LOG_FILE -Value "[FAILED] Resolve-DnsName error: $_"
}

Write-Host ""
Write-Host "[3/4] Analyzing DNS results..." -ForegroundColor Yellow
Write-Host ""

# Check if DNS resolved correctly
$logContent = Get-Content -Path $LOG_FILE -Raw
if ($logContent -match "\[SUCCESS\]") {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " DNS Verification Complete" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Results saved to: $LOG_FILE" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Verify DNS propagation (5-30 minutes)" -ForegroundColor White
    Write-Host "2. Configure AWS Security Group (ports 80 and 443)" -ForegroundColor White
    Write-Host "3. Deploy Caddy on EC2: ssh ubuntu@13.229.100.10" -ForegroundColor White
    Write-Host "4. Run: bash tools/mcp_bus/deploy/caddy_setup.sh" -ForegroundColor White
    Write-Host "5. Verify HTTPS: curl https://mcp.timquant.tech/health" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host " DNS Verification Failed" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Expected IP: $EXPECTED_IP" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Check DNS A record in control panel" -ForegroundColor White
    Write-Host "2. Wait for DNS propagation (up to 48 hours)" -ForegroundColor White
    Write-Host "3. Verify EC2 instance is running" -ForegroundColor White
    Write-Host "4. Check AWS Security Group rules" -ForegroundColor White
}

Write-Host ""
Write-Host "Log file: $LOG_FILE" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey()
