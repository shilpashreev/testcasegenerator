# Test Case Generator - PowerShell launcher
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Test Case Generator - Startup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Detect Python
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.\d+") {
            $pythonCmd = $cmd
            Write-Host "[OK] Found: $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python 3 not found." -ForegroundColor Red
    Write-Host "  Install from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "`n[1/2] Installing dependencies..." -ForegroundColor Cyan
& $pythonCmd -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[2/2] Launching app on http://localhost:8501 ..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop.`n"
& $pythonCmd -m streamlit run app.py --server.port 8501 --server.headless false
