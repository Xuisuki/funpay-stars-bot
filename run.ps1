# Funpay-Telegram-Stars — запуск бота под Windows.
Set-Location -Path $PSScriptRoot
$VPY = ".venv\Scripts\python.exe"
if (-not (Test-Path $VPY)) { Write-Host "Сначала запустите install.ps1" -ForegroundColor Red; exit 1 }
& $VPY bot_fragment.py @args
