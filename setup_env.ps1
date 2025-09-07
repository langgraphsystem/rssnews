# Настройка переменной окружения для Railway PostgreSQL
# Запустите этот скрипт в PowerShell

Write-Host "🔧 Настройка переменной окружения PG_DSN..." -ForegroundColor Blue

if (-not $env:PG_DSN) {
  Write-Host "PG_DSN не установлен. Установите переменную окружения со своими данными подключения." -ForegroundColor Yellow
  Write-Host "Пример:" -ForegroundColor Yellow
  Write-Host "  $env:PG_DSN = 'postgresql://user:pass@host:5432/dbname'" -ForegroundColor Gray
  Write-Host "  [System.Environment]::SetEnvironmentVariable('PG_DSN', 'postgresql://user:pass@host:5432/dbname', 'User')" -ForegroundColor Gray
  return
}

Write-Host "✅ Переменная PG_DSN уже установлена для текущей сессии" -ForegroundColor Green
Write-Host "🔍 Текущее значение: $env:PG_DSN" -ForegroundColor Yellow

Write-Host "`n🚀 Теперь можно запускать команды:" -ForegroundColor Blue
Write-Host "   python main.py ensure" -ForegroundColor White
Write-Host "   python main.py discovery --feed <url>" -ForegroundColor White
Write-Host "   python main.py poll" -ForegroundColor White
Write-Host "   python main.py work" -ForegroundColor White

Write-Host "`n💡 Для постоянной установки переменной (опционально):" -ForegroundColor Cyan
Write-Host "   [System.Environment]::SetEnvironmentVariable('PG_DSN', '$env:PG_DSN', 'User')" -ForegroundColor Gray
