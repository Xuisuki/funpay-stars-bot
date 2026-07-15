# Funpay-Telegram-Stars — установщик для Windows (PowerShell).
# Проверяет Python, создаёт .venv, ставит зависимости и запускает мастер настройки.
# by ProdX (prodx.pro) · dev @Xuisuki + @mawlikow
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Line($t,$c="Cyan"){ Write-Host $t -ForegroundColor $c }

Write-Host ""
Line "  ==================================================" Cyan
Line "  Funpay-Telegram-Stars  - установщик" Cyan
Line "  by ProdX - prodx.pro - dev @Xuisuki + @mawlikow" DarkGray
Line "  ==================================================" Cyan
Write-Host ""

# 1) Python
$PY = $null
foreach ($cand in @("py","python","python3")) {
  if (Get-Command $cand -ErrorAction SilentlyContinue) {
    try { & $cand -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)"; if ($LASTEXITCODE -eq 0) { $PY=$cand; break } } catch {}
  }
}
if (-not $PY) {
  Line "  [1/4] Не найден Python 3.9+. Установите: https://www.python.org/downloads/ (галочка 'Add to PATH')" Red
  Read-Host "Enter для выхода"; exit 1
}
Line "  [1/4] Python: $(& $PY --version 2>&1)" Green

# 2) venv
if (-not (Test-Path ".venv")) { Line "  [2/4] Создаю .venv ..." Cyan; & $PY -m venv .venv }
else { Line "  [2/4] .venv уже есть" Green }
$VPY = ".venv\Scripts\python.exe"

# 3) зависимости
Line "  [3/4] Ставлю зависимости (может занять пару минут - tonutils/крипта) ..." Cyan
& $VPY -m pip install --quiet --upgrade pip
& $VPY -m pip install --quiet -r requirements.txt
Line "  [3/4] Зависимости готовы" Green

# 4) мастер
Line "  [4/4] Запускаю мастер настройки ..." Cyan
Write-Host ""
& $VPY first_start.py

Write-Host ""
Line "  Установка завершена. Запуск бота: .\run.ps1" Green
Read-Host "Enter для выхода"
