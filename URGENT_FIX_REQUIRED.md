# 🚨 URGENT: Bot Not Working - Fix Required

## Issue Summary

**Status:** ❌ Bot deployed but NOT responding
**Root Cause:** `SERVICE_MODE` environment variable not set on Railway
**Impact:** Bot process never starts (runs migration service instead)
**Priority:** 🔴 CRITICAL
**Fix Time:** 2 minutes

---

## The Problem

Railway launcher checks `SERVICE_MODE` to decide what to run:

```python
# launcher.py (line 27)
mode = os.getenv("SERVICE_MODE", "openai-migration")  # ← Defaults to migration!

if mode == "bot":
    return "python start_telegram_bot.py"  # ← We need THIS
else:
    return "python services/openai_embedding_migration_service.py ..."  # ← This is running
```

**Result:** Bot never starts, migration service runs instead!

---

## Quick Fix (Option 1): Railway Dashboard ⭐ RECOMMENDED

### Step-by-Step:

1. **Open Railway Dashboard**
   - Go to: https://railway.app/
   - Login with your account

2. **Navigate to Service**
   - Project: `eloquent-recreation`
   - Service: `rssnews` (ID: `eac4079c-506c-4eab-a6d2-49bd860379de`)

3. **Add Variable**
   - Click **Variables** tab
   - Click **+ New Variable**
   - Name: `SERVICE_MODE`
   - Value: `bot`
   - Click **Add**

4. **Redeploy**
   - Service will automatically redeploy
   - Wait ~30-60 seconds

5. **Verify**
   - Go to **Deployments** tab
   - Click latest deployment
   - Check logs for:
     ```
     launcher.py -> executing: python start_telegram_bot.py
     🚀 RSS News Telegram Bot Starter
     🤖 Starting RSS News Telegram Bot...
     ```

6. **Test**
   - Open Telegram
   - Send `/start` to @rssnewsusabot
   - Bot should respond!

---

## Alternative Fix (Option 2): Railway CLI

```bash
# 1. Login to Railway
railway login

# 2. Link to service
railway link

# Select project: eloquent-recreation
# Select service: rssnews

# 3. Set variable
railway variables --set SERVICE_MODE=bot

# 4. Verify
railway variables | grep SERVICE_MODE

# Should show:
# SERVICE_MODE=bot

# 5. Check logs
railway logs

# Should see:
# launcher.py -> executing: python start_telegram_bot.py
```

---

## What's Currently Happening

**Current Service Logs:**
```
launcher.py -> executing: python services/openai_embedding_migration_service.py continuous --interval 60 --batch-size 100
```

**Should Be:**
```
launcher.py -> executing: python start_telegram_bot.py
🚀 RSS News Telegram Bot Starter
🤖 Starting RSS News Telegram Bot...
✅ Bot initialized successfully
📱 Bot: @rssnewsusabot
🏥 Health check server running on port 8080
```

---

## Verification Checklist

After setting `SERVICE_MODE=bot`:

### 1. Check Deployment Logs
```bash
railway logs -s eac4079c-506c-4eab-a6d2-49bd860379de
```

✅ Should see:
- `launcher.py -> executing: python start_telegram_bot.py`
- `🤖 Starting RSS News Telegram Bot...`
- `✅ Bot initialized successfully`
- `📱 Bot: @rssnewsusabot`

❌ Should NOT see:
- `openai_embedding_migration_service.py`

### 2. Check Health Endpoint
```bash
curl https://rssnews-production.up.railway.app/health
```

✅ Should return:
```json
{
  "status": "healthy",
  "service": "telegram-bot",
  "checks": {
    "database": "ok"
  }
}
```

### 3. Test Bot Commands

Open Telegram and try:

| Command | Expected Response |
|---------|------------------|
| `/start` | Welcome message with instructions |
| `/help` | List of all available commands |
| `/search Trump` | Search results with 5 articles |
| `/db_stats` | Database statistics |

### 4. Check Pending Updates

```bash
python test_bot_alive.py
```

✅ Should show:
```
Pending updates: 0  (cleared!)
```

---

## Additional Variables to Set (While You're There)

Since you're in Railway Variables, also verify/set:

```bash
# Critical
TELEGRAM_BOT_TOKEN=<should already be set>
PG_DSN=<should already be set>
OPENAI_API_KEY=<use valid key from .env>

# Important
USE_SIMPLE_SEARCH=true
ANTHROPIC_API_KEY=<for Claude /analyze command>

# Optional
PORT=8080
LOG_LEVEL=INFO
```

---

## What Happens After Fix

1. ✅ Launcher starts bot instead of migration
2. ✅ Bot connects to Telegram API (long polling)
3. ✅ Health check server runs on port 8080
4. ✅ Bot processes pending updates (currently 3 waiting)
5. ✅ Bot responds to all commands
6. ✅ Search functionality works perfectly (already tested!)

---

## Why This Wasn't Caught Earlier

- Local testing used different startup method (`python run_bot.py`)
- Railway requires `launcher.py` which checks `SERVICE_MODE`
- Variable was never explicitly set in Railway config
- Default value (`openai-migration`) silently ran wrong service

---

## Files for Reference

- `launcher.py` - Checks SERVICE_MODE (line 27)
- `start_telegram_bot.py` - Bot entry point
- `run_bot.py` - Bot polling logic
- `FIX_BOT_NOT_RESPONDING.md` - Detailed diagnosis
- `diagnose_bot_issue.py` - Diagnostic script

---

## Support

If bot still doesn't work after setting `SERVICE_MODE=bot`:

1. Check Railway logs for errors
2. Run `python diagnose_bot_issue.py` locally
3. Verify all environment variables
4. Check this file: `PHASE2_3_DEPLOYMENT_REPORT.md`

---

**🎯 ACTION REQUIRED NOW:**

1. Go to Railway Dashboard
2. Add variable: `SERVICE_MODE=bot`
3. Wait 60 seconds for redeploy
4. Test bot with `/start`

**That's it!** 🚀
