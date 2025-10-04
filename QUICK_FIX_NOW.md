# ⚡ БЫСТРОЕ ИСПРАВЛЕНИЕ - БОТ НЕ РАБОТАЕТ

## 🔴 ПРОБЛЕМА: Бот настроен как CRON JOB (запускается 1 раз в день)

**Сейчас:** Бот запускается только в 12:00 UTC и сразу останавливается
**Нужно:** Бот должен работать 24/7

---

## ✅ ИСПРАВЛЕНИЕ (3 минуты)

### Шаг 1: Railway Dashboard → Settings

1. Откройте: https://railway.app/
2. Проект: `eloquent-recreation`
3. Сервис: `rssnews`
4. Вкладка: **Settings**

### Шаг 2: Deployment Settings

Найдите секцию **"Deployment"** и измените:

**Удалите Cron Schedule:**
```
Cron Schedule: [0 12 * * *]  ← УДАЛИТЕ ЭТО ЗНАЧЕНИЕ (оставьте пустым)
```

**Измените Restart Policy:**
```
Restart Policy: [Never]  ← Измените на [On Failure]
```

**Нажмите SAVE**

### Шаг 3: Variables (пока там же)

Перейдите на вкладку **Variables** и добавьте:

```
SERVICE_MODE=bot
USE_SIMPLE_SEARCH=true
```

Проверьте что установлены:
```
TELEGRAM_BOT_TOKEN=<должен быть>
PG_DSN=<должен быть>
OPENAI_API_KEY=<должен быть>
```

### Шаг 4: Redeploy

1. Вкладка **Deployments**
2. Кнопка **Redeploy** (справа вверху)
3. Подождите 60 секунд

### Шаг 5: Проверка

Откройте Telegram → @rssnewsusabot → отправьте:
```
/start
```

**Должен ответить сразу!**

---

## 🎯 ЧТО ИЗМЕНИТСЯ

### БЫЛО (неправильно):
- Бот запускается в 12:00 UTC
- Работает 10 секунд и останавливается
- Не отвечает на сообщения

### СТАНЕТ (правильно):
- Бот запускается сразу после deploy
- Работает постоянно 24/7
- Отвечает на сообщения мгновенно

---

## 📋 Checklist

- [ ] Dashboard → Settings → Cron Schedule → УДАЛЕНО
- [ ] Restart Policy → ON_FAILURE
- [ ] Variables → SERVICE_MODE=bot
- [ ] Variables → USE_SIMPLE_SEARCH=true
- [ ] Redeploy нажат
- [ ] Бот отвечает на /start

---

**После этих 3 шагов бот ЗАРАБОТАЕТ!** ✅
