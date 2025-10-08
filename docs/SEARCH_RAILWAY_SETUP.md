# Search API Setup for Railway

## Overview

Добавление Search API к существующему Railway deployment.

**Ваш Railway URL:** `https://rssnews-production-eaa2.up.railway.app`

---

## ✅ Что уже готово

- ✅ `launcher.py` обновлен (добавлен `search-api` mode)
- ✅ `api/search_api.py` создан (FastAPI endpoint)
- ✅ `api/search_openapi.yaml` создан (OpenAPI spec)
- ✅ Railway уже настроен и работает

---

## 🚀 Деплой на Railway

### Вариант 1: Отдельный сервис (Рекомендуется)

Создать отдельный Railway сервис для Search API.

#### Шаг 1: Создать новый сервис

```bash
# В Railway dashboard или через CLI
railway service create search-api
```

#### Шаг 2: Установить переменные окружения

```bash
# Переключиться на новый сервис
railway service search-api

# Установить SERVICE_MODE
railway variables set SERVICE_MODE=search-api

# PORT устанавливается автоматически Railway
# Остальные переменные наследуются от shared variables
```

#### Шаг 3: Deploy

```bash
railway up
```

Railway автоматически:
1. Обнаружит `launcher.py`
2. Запустит `uvicorn api.search_api:app --host 0.0.0.0 --port $PORT`
3. Назначит публичный URL

#### Шаг 4: Получить URL

```bash
railway domain
# Вывод: https://search-api-production-XXXX.up.railway.app
```

---

### Вариант 2: Использовать существующий сервис

Если не хотите создавать отдельный сервис, можно добавить endpoint к существующему боту.

#### Модифицировать `start_telegram_bot.py`

Добавить Search API к bot сервису:

```python
# В start_telegram_bot.py
import asyncio
import uvicorn
from threading import Thread

def run_search_api():
    """Run Search API in separate thread"""
    import os
    port = int(os.getenv("SEARCH_API_PORT", "8001"))

    # Import here to avoid circular dependencies
    from api.search_api import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

async def main():
    # Start Search API in background thread
    search_thread = Thread(target=run_search_api, daemon=True)
    search_thread.start()

    # Start Telegram bot (existing code)
    bot_service = AdvancedBotService(...)
    await bot_service.run()
```

**Проблема:** Railway обычно назначает один PORT, поэтому придется использовать разные пути:
- Bot: `https://rssnews-production-eaa2.up.railway.app/` (WebApp или webhooks)
- Search API: `https://rssnews-production-eaa2.up.railway.app/retrieve`

**Не рекомендуется** — лучше создать отдельный сервис.

---

## 📋 Рекомендуемая конфигурация: Отдельный сервис

### Структура Railway проекта

```
Project: eloquent-recreation
├── Service: rssnews (bot)
│   └── SERVICE_MODE=bot
│       URL: https://rssnews-production-eaa2.up.railway.app
│
└── Service: search-api (NEW)
    └── SERVICE_MODE=search-api
        URL: https://search-api-production-XXXX.up.railway.app
```

### Shared Variables (для обоих сервисов)

```bash
# Database
PG_DSN=postgresql://...
EMBEDDING_MODEL=text-embedding-3-large

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Ranking API
RANKING_SERVICE_URL=http://localhost:8002
```

### Service-Specific Variables

**rssnews (bot):**
```bash
SERVICE_MODE=bot
TELEGRAM_BOT_TOKEN=...
```

**search-api:**
```bash
SERVICE_MODE=search-api
# PORT автоматически устанавливается Railway
```

---

## 🔧 Пошаговая инструкция

### 1. Создать новый сервис в Railway Dashboard

1. Зайти в Railway Dashboard: https://railway.app/
2. Открыть проект: **eloquent-recreation**
3. Нажать **New Service**
4. Выбрать **Deploy from GitHub repo**
5. Выбрать ваш репозиторий
6. Имя сервиса: `search-api`

### 2. Настроить переменные окружения

В настройках сервиса `search-api`:

**Variables:**
```
SERVICE_MODE = search-api
```

**Shared Variables** (автоматически наследуются):
- `PG_DSN`
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL`
- и другие

### 3. Настроить Networking

1. В настройках сервиса `search-api`
2. **Settings** → **Networking**
3. **Generate Domain** → Railway создаст публичный URL
4. Скопировать URL (например, `https://search-api-production-a1b2.up.railway.app`)

### 4. Deploy

Railway автоматически задеплоит после создания сервиса.

Проверить логи:
```bash
railway logs --service search-api
```

Ожидаемый вывод:
```
launcher.py -> executing: uvicorn api.search_api:app --host 0.0.0.0 --port 8080
INFO: Started server process
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8080
```

### 5. Протестировать

```bash
# Health check
curl https://search-api-production-XXXX.up.railway.app/health

# Ожидается:
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-10-06T..."
}
```

```bash
# Test search
curl -X POST https://search-api-production-XXXX.up.railway.app/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "AI regulation",
    "hours": 24,
    "k": 5,
    "filters": {},
    "cursor": null,
    "correlation_id": "test-123"
  }'

# Ожидается JSON с items
```

---

## 🔐 Опциональная защита с Railway Service Token

Railway не имеет встроенного Access Control как Cloudflare, но можно добавить простую API key auth.

### Добавить API Key в environment

```bash
railway variables set SEARCH_API_KEY="your-secret-key-here"
```

### Модифицировать `api/search_api.py`

```python
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key"""
    expected_key = os.getenv("SEARCH_API_KEY")

    if not expected_key:
        # If no key configured, allow all
        return True

    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True

@app.post("/retrieve", dependencies=[Depends(verify_api_key)])
async def retrieve(request: RetrieveRequest):
    # ... existing code ...
```

### Обновить OpenAPI spec

```yaml
# В search_openapi.yaml
components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

security:
  - ApiKeyAuth: []
```

### Настроить в OpenAI GPT Actions

**Auth Type:** API Key

**Header:**
- Name: `X-API-Key`
- Value: `your-secret-key-here`

---

## 📊 Monitoring

### Railway Dashboard

1. **Metrics** → Просмотр CPU/Memory/Network
2. **Logs** → Real-time логи
3. **Deployments** → История деплоев

### Logs

```bash
# Real-time logs
railway logs --service search-api --follow

# Last 100 lines
railway logs --service search-api --lines 100
```

---

## 🔄 Update Deployment

### Automatic (Recommended)

Railway автоматически деплоит при push в GitHub:

```bash
git add launcher.py api/
git commit -m "Add search API"
git push origin main
```

Railway обнаружит изменения и автоматически задеплоит оба сервиса.

### Manual

```bash
# Deploy specific service
railway up --service search-api
```

---

## 🛠️ Troubleshooting

### Issue: Service не запускается

**Проверить:**
```bash
railway logs --service search-api
```

**Частые проблемы:**
1. `uvicorn` не установлен → добавить в `requirements.txt`
2. `fastapi` не установлен → добавить в `requirements.txt`
3. Неверный `SERVICE_MODE` → проверить env variables

### Issue: 503 Service Unavailable

**Причина:** Search API еще стартует

**Решение:** Подождать 30-60 секунд после деплоя

### Issue: Database connection failed

**Проверить:**
```bash
railway variables --service search-api | grep PG_DSN
```

**Решение:** Убедиться что `PG_DSN` правильно установлен в Shared Variables

---

## 📝 Requirements Update

Убедитесь что `requirements.txt` содержит:

```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
```

Или добавить:

```bash
echo "fastapi>=0.104.0" >> requirements.txt
echo "uvicorn[standard]>=0.24.0" >> requirements.txt
```

---

## ✅ Deployment Checklist

### Pre-Deployment
- [x] `launcher.py` обновлен (добавлен `search-api` mode)
- [x] `api/search_api.py` создан
- [x] `api/search_openapi.yaml` создан
- [x] `requirements.txt` содержит `fastapi`, `uvicorn`

### Deployment
- [ ] Создан новый сервис `search-api` в Railway
- [ ] Установлена переменная `SERVICE_MODE=search-api`
- [ ] Сервис задеплоен успешно
- [ ] Логи показывают "Uvicorn running"
- [ ] Health check работает (`/health`)

### Testing
- [ ] `POST /retrieve` возвращает результаты
- [ ] Pagination работает (next_cursor)
- [ ] Ошибки обрабатываются корректно

### OpenAI Integration
- [ ] OpenAPI spec обновлен с Railway URL
- [ ] GPT Action импортирован
- [ ] System prompt добавлен
- [ ] Test search работает

---

## 🎯 Итоговая конфигурация

### Railway Project Structure

```
eloquent-recreation/
├── rssnews (bot)
│   ├── SERVICE_MODE=bot
│   ├── URL: https://rssnews-production-eaa2.up.railway.app
│   └── Command: python start_telegram_bot.py
│
└── search-api (NEW)
    ├── SERVICE_MODE=search-api
    ├── URL: https://search-api-production-XXXX.up.railway.app
    └── Command: uvicorn api.search_api:app --host 0.0.0.0 --port $PORT
```

### OpenAPI Spec Update

В `api/search_openapi.yaml` заменить:

```yaml
servers:
  - url: https://search-api-production-XXXX.up.railway.app
```

### GPT Actions URL

```
https://search-api-production-XXXX.up.railway.app/retrieve
```

---

## 🚀 Quick Start (если всё настроено)

```bash
# 1. Commit изменения
git add launcher.py api/
git commit -m "feat(search): add search API for Railway"
git push origin main

# 2. Создать сервис в Railway Dashboard
# (через UI: New Service → GitHub repo → search-api)

# 3. Установить SERVICE_MODE
railway service search-api
railway variables set SERVICE_MODE=search-api

# 4. Получить URL
railway domain

# 5. Тестировать
curl https://YOUR_URL/health
```

---

## 📚 Next Steps

1. **Deploy на Railway** (следуя инструкции выше)
2. **Получить Railway URL**
3. **Обновить OpenAPI spec** с Railway URL
4. **Настроить OpenAI GPT Actions** (см. `SEARCH_GPT_AGENT_SETUP.md`)
5. **Тестировать** `/search` команду

---

**Готово! Railway deployment для Search API настроен.** 🎉
