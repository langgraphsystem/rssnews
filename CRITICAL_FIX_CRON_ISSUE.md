# 🚨 CRITICAL: Bot is a CRON JOB, Not a Running Service!

## ROOT CAUSE FOUND! ✅

**The Problem:** Service is configured as a **CRON JOB** that runs once per day at 12:00 UTC

**Evidence from Railway API:**
```json
"cronSchedule": "0 12 * * *",
"restartPolicyType": "NEVER"
```

**Impact:**
- Bot starts only at 12:00 UTC (once per day)
- Bot is NOT continuously running
- Bot does NOT respond to messages in real-time
- After running, bot stops immediately

**This is why bot doesn't respond!**

---

## THE FIX

### Railway Dashboard (REQUIRED)

1. **Open Railway Dashboard**
   - Go to: https://railway.app/
   - Project: `eloquent-recreation`
   - Service: `rssnews`

2. **Go to Settings Tab**
   - Scroll to **"Deployment"** section

3. **REMOVE Cron Schedule**
   - Find: `Cron Schedule` field
   - Current value: `0 12 * * *`
   - **DELETE THIS VALUE** (leave empty)
   - Click **Save**

4. **Change Restart Policy**
   - Find: `Restart Policy`
   - Change from: `NEVER`
   - Change to: `ON_FAILURE`
   - Click **Save**

5. **Redeploy**
   - Go to Deployments tab
   - Click **Redeploy**
   - Or push new commit to trigger deploy

---

## What Should Happen After Fix

### Before (Current - WRONG):
```
cronSchedule: "0 12 * * *"        ← Runs once per day!
restartPolicyType: "NEVER"        ← Never restarts!
numReplicas: 1                    ← Only when cron triggers
```

**Result:** Bot runs for a few seconds at 12:00 UTC, then stops

### After (Correct):
```
cronSchedule: null                ← No cron, runs continuously
restartPolicyType: "ON_FAILURE"   ← Restarts if crashes
numReplicas: 1                    ← Always running
```

**Result:** Bot runs 24/7, responds immediately

---

## How This Happened

1. **railway.toml is correct** (no cron schedule)
2. **But Railway Dashboard has override settings**
3. Dashboard settings take precedence over railway.toml
4. Someone set cron schedule in Dashboard
5. Bot now runs as scheduled job, not service

---

## Verification After Fix

### 1. Check Railway Deployment Logs

After redeploying, logs should show:
```
launcher.py -> executing: python start_telegram_bot.py
🚀 RSS News Telegram Bot Starter
🤖 Starting RSS News Telegram Bot...
✅ Bot initialized successfully
📱 Bot: @rssnewsusabot
🔄 Starting long polling...
```

**And keep running!** (not stop after a few seconds)

### 2. Check Deployment Meta

In next deployment, should see:
```json
"cronSchedule": null,              ← No cron!
"restartPolicyType": "ON_FAILURE", ← Proper restart
```

### 3. Test Bot Immediately

Send `/start` to @rssnewsusabot
- Should respond within 1-2 seconds
- Not wait until 12:00 UTC tomorrow!

---

## Step-by-Step Visual Guide

### Finding Cron Schedule in Railway:

```
Railway Dashboard
  └─ eloquent-recreation (project)
      └─ rssnews (service)
          └─ Settings (tab)
              └─ Deployment section
                  └─ Cron Schedule: [0 12 * * *]  ← DELETE THIS
                  └─ Restart Policy: [Never]      ← Change to "On Failure"
```

---

## Additional Variables to Set (While You're There)

In **Variables** tab, ensure these are set:

```bash
# CRITICAL
SERVICE_MODE=bot                    # ← Start bot, not migration
TELEGRAM_BOT_TOKEN=<your-token>    # ← Should already be set
PG_DSN=<your-dsn>                  # ← Should already be set
OPENAI_API_KEY=<valid-key>         # ← Use key from .env

# IMPORTANT
USE_SIMPLE_SEARCH=true             # ← Use working search service

# OPTIONAL
PORT=8080                          # ← For health check
LOG_LEVEL=INFO                     # ← Reasonable logging
```

---

## Why Cron Job Was Wrong for Telegram Bot

**Cron jobs are for:**
- Scheduled tasks (backups, reports)
- Batch processing
- One-time scripts

**NOT for:**
- ❌ Telegram bots (need 24/7 polling)
- ❌ Web servers
- ❌ API services
- ❌ Real-time applications

**Telegram bots need:**
- ✅ Continuous running (24/7)
- ✅ Long polling connection
- ✅ Immediate message response
- ✅ Auto-restart on failure

---

## Timeline of Issue

1. **Initial deployment:** Bot as service ✅
2. **Somewhere:** Cron schedule added in Dashboard ❌
3. **Result:** Bot became scheduled job
4. **Impact:** Bot only runs at 12:00 UTC
5. **User reports:** "Bot doesn't respond" ✅ Correct!
6. **Investigation:** Found cron schedule ✅
7. **Fix:** Remove cron, set ON_FAILURE ⏳ PENDING

---

## URGENT ACTIONS REQUIRED

### Priority 1: Remove Cron Schedule
1. Railway Dashboard → Settings
2. Delete cron schedule value
3. Change restart policy to ON_FAILURE
4. Save changes

### Priority 2: Set Variables
1. Railway Dashboard → Variables
2. Add `SERVICE_MODE=bot`
3. Verify `OPENAI_API_KEY` is valid
4. Add `USE_SIMPLE_SEARCH=true`

### Priority 3: Redeploy
1. Railway Dashboard → Deployments
2. Click Redeploy
3. Watch logs for "Starting long polling..."
4. Test bot immediately

---

## Expected Results

### Logs should show (and keep showing):
```
2025-10-04 19:30:00 | INFO | launcher.py -> executing: python start_telegram_bot.py
2025-10-04 19:30:01 | INFO | 🚀 RSS News Telegram Bot Starter
2025-10-04 19:30:02 | INFO | 🤖 Starting RSS News Telegram Bot...
2025-10-04 19:30:05 | INFO | ✅ Bot initialized successfully
2025-10-04 19:30:06 | INFO | 🔄 Starting long polling...
2025-10-04 19:30:07 | INFO | 📡 Polling for updates...
(continues forever, NOT stops!)
```

### Bot should:
- ✅ Respond to `/start` immediately
- ✅ Process all pending updates
- ✅ Stay running 24/7
- ✅ Restart automatically if crashes

---

## Files for Reference

- `railway.toml` - Correct config (no cron)
- `launcher.py` - Starts bot via SERVICE_MODE
- `start_telegram_bot.py` - Bot entry point
- `run_bot.py` - Long polling logic

---

**🎯 ACTION REQUIRED NOW:**

1. ❗ Railway Dashboard → Settings → Delete Cron Schedule
2. ❗ Change Restart Policy → ON_FAILURE
3. ❗ Variables → Add SERVICE_MODE=bot
4. ❗ Redeploy service
5. ✅ Test bot immediately

**ETA:** 3 minutes to fix

**This will make bot work 24/7!** 🚀
