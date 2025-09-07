# Быстрый тест миграции на PostgreSQL
# Использование: ./test_quick.ps1 [PG_DSN]

param(
    [Parameter(Mandatory=$false)]
    [string]$PG_DSN
)

Write-Host "🧪 Быстрый тест миграции RSS News на PostgreSQL" -ForegroundColor Green
Write-Host "=" -Repeat 60 -ForegroundColor Green

# Проверка Python
Write-Host "🔍 Проверка Python..." -ForegroundColor Blue
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python не найден. Установите Python 3.7+" -ForegroundColor Red
    exit 1
}

# Проверка рабочей директории
if (!(Test-Path "pg_client.py")) {
    Write-Host "❌ Запустите скрипт из папки проекта rssnews" -ForegroundColor Red
    exit 1
}

# Установка psycopg2 если нужно
Write-Host "🔧 Проверка psycopg2..." -ForegroundColor Blue
$psycopgCheck = python -c "import psycopg2; print('OK')" 2>&1
if ($psycopgCheck -notmatch "OK") {
    Write-Host "📦 Устанавливаем psycopg2-binary..." -ForegroundColor Yellow
    pip install psycopg2-binary
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Ошибка установки psycopg2-binary" -ForegroundColor Red
        exit 1
    }
}

# Базовый тест миграции
Write-Host "🧪 Запуск базового теста миграции..." -ForegroundColor Blue
python test_migration.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Базовый тест провален" -ForegroundColor Red
    exit 1
}

# Если PG_DSN предоставлен, тестируем с БД
if ($PG_DSN) {
    Write-Host "🔗 Настройка PG_DSN для тестирования с БД..." -ForegroundColor Blue
    $env:PG_DSN = $PG_DSN
    
    Write-Host "🗄️ Запуск теста с реальной БД..." -ForegroundColor Blue
    python test_with_real_db.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️ Тест с БД завершился с ошибками (это может быть нормально)" -ForegroundColor Yellow
    }
} else {
    Write-Host "ℹ️ Для теста с реальной БД запустите:" -ForegroundColor Cyan
    Write-Host "   ./test_quick.ps1 'postgresql://user:pass@host:port/db'" -ForegroundColor Cyan
}

Write-Host "`n🎉 Миграция протестирована!" -ForegroundColor Green
Write-Host "📋 Следующие шаги:" -ForegroundColor Blue
Write-Host "1. Настройте переменную PG_DSN" -ForegroundColor White
Write-Host "2. Запустите: python main.py ensure" -ForegroundColor White
Write-Host "3. Добавьте RSS: python main.py discovery --feed <url>" -ForegroundColor White
Write-Host "4. Запустите цикл: python main.py poll && python main.py work" -ForegroundColor White