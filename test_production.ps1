# Продуктивный тест RSS News с PostgreSQL
# Этот скрипт тестирует полный рабочий цикл

Write-Host "🚀 ПРОДУКТИВНЫЙ ТЕСТ RSS NEWS + POSTGRESQL" -ForegroundColor Green
Write-Host "=" -Repeat 50 -ForegroundColor Green

# Проверяем, установлена ли переменная окружения
if (-not $env:PG_DSN) {
    Write-Host "❌ Переменная окружения PG_DSN не установлена." -ForegroundColor Red
    Write-Host "   Установите ее перед запуском: \$env:PG_DSN='postgresql://...'" -ForegroundColor Yellow
    exit 1
}

Write-Host "🔧 1. Проверяем схему БД..." -ForegroundColor Blue
python main.py ensure
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка инициализации БД" -ForegroundColor Red
    exit 1
}

Write-Host "`n📡 2. Добавляем RSS фиды..." -ForegroundColor Blue
$feeds = @(
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://www.theguardian.com/world/rss"
)

foreach ($feed in $feeds) {
    Write-Host "   Добавляем: $feed" -ForegroundColor Yellow
    python main.py discovery --feed $feed
}

Write-Host "`n📰 3. Опрашиваем RSS фиды..." -ForegroundColor Blue
python main.py poll
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Опрос RSS выполнен успешно" -ForegroundColor Green
} else {
    Write-Host "⚠️ Опрос завершен с предупреждениями (возможны дубликаты)" -ForegroundColor Yellow
}

Write-Host "`n⚙️ 4. Обрабатываем статьи..." -ForegroundColor Blue
python main.py work --worker-id "production-test"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Обработка статей выполнена" -ForegroundColor Green
} else {
    Write-Host "⚠️ Обработка завершена с предупреждениями" -ForegroundColor Yellow
}

Write-Host "`n📊 5. Проверяем статистику..." -ForegroundColor Blue
python -c "
import os
from pg_client import PgClient
client = PgClient()
feeds = client.get_active_feeds()
print(f'✅ Активных фидов: {len(feeds)}')
with client.conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM raw')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"pending\"')
    pending = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM raw WHERE status = \"stored\"')
    processed = cur.fetchone()[0]
    print(f'✅ Всего статей: {total}')
    print(f'✅ Pending: {pending}')
    print(f'✅ Обработано: {processed}')
client.close()
"

Write-Host "`n" -NoNewline
Write-Host "🎉 ТЕСТ ЗАВЕРШЕН!" -ForegroundColor Green
Write-Host "=" -Repeat 50 -ForegroundColor Green

Write-Host "`n💡 Для регулярного использования:" -ForegroundColor Cyan
Write-Host "   python main.py poll    # Каждые 15-30 минут" -ForegroundColor White
Write-Host "   python main.py work    # Каждые 5-10 минут" -ForegroundColor White

Write-Host "`n🔧 Для добавления новых RSS:" -ForegroundColor Cyan  
Write-Host "   python main.py discovery --feed <url>" -ForegroundColor White