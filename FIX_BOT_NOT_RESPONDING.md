# 🔧 FIX: Bot Not Responding

## Problem Identified ✅

**Root Cause:** `SERVICE_MODE` environment variable is NOT set on Railway

**Result:** Launcher defaults to `openai-migration` instead of starting the bot

---

## Solution: Set SERVICE_MODE=bot

### Option 1: Railway Dashboard (RECOMMENDED)

1. Go to [Railway Dashboard](https://railway.app/)
2. Select project and service `eac4079c-506c-4eab-a6d2-49bd860379de`
3. Click **Variables** tab
4. Add new variable:
   ```
   SERVICE_MODE=bot
   ```
5. Click **Deploy** to restart with new variables

### Option 2: Railway CLI

```bash
# Login to Railway
railway login

# Link to service
railway link -s eac4079c-506c-4eab-a6d2-49bd860379de

# Set variable
railway variables --set SERVICE_MODE=bot

# Verify
railway variables

# Redeploy
railway up --detach
```

### Option 3: GraphQL API (if you have the right IDs)

See `set_railway_service_mode.py` script

---

## Additional Variables to Set (Optional but Recommended)

While you're in Railway variables, also set:

```bash
# Enable simple search service
USE_SIMPLE_SEARCH=true

# Ensure valid OpenAI API key
OPENAI_API_KEY=<use the valid key from .env>

# Verify other critical vars are set:
TELEGRAM_BOT_TOKEN=<should already be set>
PG_DSN=<should already be set>
ANTHROPIC_API_KEY=<for Claude /analyze command>
```

---

## Verify Fix

After setting `SERVICE_MODE=bot` and redeploying:

1. **Check deployment logs:**
   ```bash
   railway logs -s eac4079c-506c-4eab-a6d2-49bd860379de
   ```

   You should see:
   ```
   launcher.py -> executing: python start_telegram_bot.py
   🚀 RSS News Telegram Bot Starter
   🤖 Starting RSS News Telegram Bot...
   ✅ Bot initialized successfully
   ```

2. **Test bot in Telegram:**
   - Send `/start` to @rssnewsusabot
   - Should get welcome message
   - Try `/help` to see all commands

3. **Check bot is polling:**
   ```bash
   python test_bot_alive.py
   ```

   Should show:
   ```
   Pending updates: 0  (not 3!)
   ```

---

## Why This Happened

The `launcher.py` script checks `SERVICE_MODE` env var to decide what to run:

```python
mode = os.getenv("SERVICE_MODE", "openai-migration")  # ← defaults to migration!

if mode == "bot":
    return "python start_telegram_bot.py"  # ← This is what we need
elif mode == "openai-migration":
    return "python services/openai_embedding_migration_service.py ..."  # ← This was running
```

**Without `SERVICE_MODE=bot`, the bot never starts!**

---

## Current Status

- ✅ Bot code is deployed on Railway
- ✅ TELEGRAM_BOT_TOKEN is valid
- ✅ OPENAI_API_KEY is valid (local .env)
- ✅ PG_DSN is configured
- ✅ All bot files present
- ❌ SERVICE_MODE not set → bot not starting
- ⏳ 3 pending Telegram updates waiting

---

## After Fix Checklist

Once `SERVICE_MODE=bot` is set:

- [ ] Railway service redeployed
- [ ] Check logs show "python start_telegram_bot.py"
- [ ] Bot responds to /start
- [ ] Bot responds to /help
- [ ] Test /search command
- [ ] Pending updates cleared (count = 0)

---

**ETA to Fix:** 2 minutes (just set one variable and redeploy)

**Priority:** 🔴 CRITICAL - Bot completely non-functional without this
