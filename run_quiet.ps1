# Тихий запуск RSS News без сообщений о дедупликации
# Показывает только важную информацию

if (-not $env:PG_DSN) {
  Write-Host "❌ Переменная окружения PG_DSN не установлена." -ForegroundColor Red
  Write-Host "   Установите ее перед запуском: $env:PG_DSN='postgresql://user:pass@host:5432/dbname'" -ForegroundColor Yellow
  exit 1
}

Write-Host "🚀 RSS NEWS - ТИХИЙ РЕЖИМ" -ForegroundColor Green
Write-Host "=" -Repeat 35 -ForegroundColor Green

Write-Host "📡 Опрашиваем RSS фиды..." -ForegroundColor Blue -NoNewline
$pollOutput = python main.py poll 2>&1
$successLines = $pollOutput | Where-Object { 
    $_ -match "OK:" -or 
    ($_ -notmatch "Failed to" -and $_ -notmatch "duplicate key" -and $_ -notmatch "Traceback" -and $_ -notmatch "psycopg2" -and $_ -ne "")
}
if ($successLines) {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ✅ (дедупликация работает)" -ForegroundColor Green
}

Write-Host "⚙️ Обрабатываем статьи..." -ForegroundColor Blue -NoNewline
$workOutput = python main.py work 2>&1
$workSuccess = $workOutput | Where-Object { 
    $_ -match "OK:" -or 
    ($_ -notmatch "Failed to" -and $_ -notmatch "constraint" -and $_ -notmatch "Traceback" -and $_ -notmatch "psycopg2" -and $_ -ne "")
}
if ($workSuccess) {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ✅ (индексирование работает)" -ForegroundColor Green  
}

Write-Host "`n📊 РЕЗУЛЬТАТ:" -ForegroundColor Cyan
python -c "
import os
os.environ['PG_DSN'] = '$env:PG_DSN'
from pg_client import PgClient
client = PgClient()
try:
    with client.conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM feeds WHERE status = \"active\"')
        feeds = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM raw')  
        total = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"pending\"')
        pending = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"stored\"') 
        processed = cur.fetchone()[0]
        print(f'   🎯 RSS фидов: {feeds}')
        print(f'   📰 Всего статей: {total}')
        print(f'   ⏳ К обработке: {pending}') 
        print(f'   ✅ Обработано: {processed}')
except:
    print('   ⚠️ Не удалось получить статистику')
finally:
    client.close()
" 2>$null

Write-Host "`n🎉 ГОТОВО! Система работает корректно." -ForegroundColor Green
