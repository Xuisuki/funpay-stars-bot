# Windows. Регистрирует Funpay Stars в Планировщике задач:
# автозапуск при входе в систему + рестарт при сбое, без лимита времени.
# Запуск (PowerShell от администратора):  .\deploy\windows_task.ps1
# Управление:  Stop-ScheduledTask -TaskName FunpayStarsBot / Start-ScheduledTask -TaskName FunpayStarsBot

$Dir    = "C:\funpay-stars-bot"                 # папка проекта
$Python = "C:\Python312\python.exe"             # путь к вашему python (проверьте: where python)

$action  = New-ScheduledTaskAction -Execute $Python -Argument "bot_fragment.py" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "FunpayStarsBot" -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Highest -Force

Write-Host "Задача FunpayStarsBot зарегистрирована. Старт: Start-ScheduledTask -TaskName FunpayStarsBot"
