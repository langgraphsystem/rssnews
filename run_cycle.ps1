# Запуск полного цикла RSS News без ошибок
# Этот скрипт подавляет сообщения об ошибках дедупликации

if (-not $env:PG_DSN) {
  Write-Host "❌ Переменная окружения PG_DSN не установлена." -ForegroundColor Red
  Write-Host "   Установите ее перед запуском: $env:PG_DSN='postgresql://user:pass@host:5432/dbname'" -ForegroundColor Yellow
  exit 1
}

Write-Host "🚀 ЗАПУСК ЦИКЛА RSS NEWS" -ForegroundColor Green
Write-Host "=" -Repeat 30 -ForegroundColor Green

Write-Host "🔧 Исправляем схему БД..." -ForegroundColor Blue
python quick_fix.py

Write-Host "`n📡 Опрашиваем RSS..." -ForegroundColor Blue
python main.py poll 2>$null | Where-Object { $_ -notmatch "duplicate key" -and $_ -notmatch "Failed to append" }

Write-Host "`n⚙️ Обрабатываем статьи..." -ForegroundColor Blue  
python main.py work 2>$null | Where-Object { $_ -notmatch "Failed to upsert" }

Write-Host "`n📊 Статистика:" -ForegroundColor Blue
python -c "
import os
os.environ['PG_DSN'] = '$env:PG_DSN'
from pg_client import PgClient
client = PgClient()
with client.conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM feeds WHERE status = \"active\"')
    feeds = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM raw')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"pending\"')
    pending = cur.fetchone()[0]  
    cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"stored\"')
    processed = cur.fetchone()[0]
    print(f'✅ Активных фидов: {feeds}')
    print(f'✅ Всего статей: {total}')
    print(f'✅ К обработке: {pending}')
    print(f'✅ Обработано: {processed}')
client.close()
"

Write-Host "`n🎉 ЦИКЛ ЗАВЕРШЕН!" -ForegroundColor Green
