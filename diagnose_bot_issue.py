#!/usr/bin/env python3
"""
Diagnose why bot is not responding
Comprehensive check of all potential issues
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("🔍 Bot Diagnosis - Checking All Potential Issues")
print("=" * 80)
print()

issues = []
warnings = []

# 1. Check TELEGRAM_BOT_TOKEN
print("1️⃣  Checking TELEGRAM_BOT_TOKEN...")
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
if bot_token:
    print(f"   ✅ Set: {bot_token[:20]}...{bot_token[-10:]}")
else:
    print("   ❌ NOT SET")
    issues.append("TELEGRAM_BOT_TOKEN not set in environment")
print()

# 2. Check OPENAI_API_KEY
print("2️⃣  Checking OPENAI_API_KEY...")
openai_key = os.getenv('OPENAI_API_KEY')
if openai_key:
    print(f"   ✅ Set: {openai_key[:20]}...{openai_key[-10:]}")
    # Try to validate
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        # Quick test
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input="test"
        )
        print("   ✅ VALID - API key works")
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Incorrect API key" in error_msg:
            print("   ❌ INVALID - Authentication failed")
            issues.append("OPENAI_API_KEY is invalid/expired")
        else:
            print(f"   ⚠️  Error testing: {error_msg[:100]}")
            warnings.append(f"OPENAI_API_KEY test error: {error_msg[:100]}")
else:
    print("   ❌ NOT SET")
    issues.append("OPENAI_API_KEY not set - GPT5Service will fail")
print()

# 3. Check PG_DSN
print("3️⃣  Checking PG_DSN...")
pg_dsn = os.getenv('PG_DSN')
if pg_dsn:
    print(f"   ✅ Set: {pg_dsn[:30]}...")
else:
    print("   ❌ NOT SET")
    issues.append("PG_DSN not set - database connection will fail")
print()

# 4. Check SERVICE_MODE (should be 'bot' on Railway)
print("4️⃣  Checking SERVICE_MODE...")
service_mode = os.getenv('SERVICE_MODE')
if service_mode:
    print(f"   ℹ️  Set to: {service_mode}")
    if service_mode != 'bot':
        print("   ⚠️  WARNING: Should be 'bot' for Telegram bot service")
        warnings.append(f"SERVICE_MODE is '{service_mode}', should be 'bot'")
else:
    print("   ⚠️  NOT SET (will default to 'openai-migration')")
    warnings.append("SERVICE_MODE not set - launcher won't start bot")
print()

# 5. Check if bot files exist
print("5️⃣  Checking bot files...")
required_files = [
    'start_telegram_bot.py',
    'run_bot.py',
    'bot_service/advanced_bot.py',
    'launcher.py'
]
for file in required_files:
    if os.path.exists(file):
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - MISSING")
        issues.append(f"Required file {file} missing")
print()

# 6. Summary
print("=" * 80)
print("📊 Diagnosis Summary")
print("=" * 80)
print()

if not issues and not warnings:
    print("✅ All checks passed!")
    print()
    print("💡 Bot should be working. Possible issues:")
    print("   - Bot process crashed on Railway (check logs)")
    print("   - Network/firewall blocking Telegram API")
    print("   - Railway service not deployed with latest code")
else:
    if issues:
        print(f"❌ Found {len(issues)} critical issues:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print()

    if warnings:
        print(f"⚠️  Found {len(warnings)} warnings:")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
        print()

print("🔧 Recommended Actions:")
print()

if "OPENAI_API_KEY is invalid/expired" in '\n'.join(issues):
    print("1. Update OPENAI_API_KEY on Railway:")
    print("   - Get valid key from .env")
    print("   - railway variables --set OPENAI_API_KEY='...'")
    print()

if "SERVICE_MODE" in '\n'.join(warnings):
    print("2. Set SERVICE_MODE=bot on Railway:")
    print("   - railway variables --set SERVICE_MODE='bot'")
    print("   - Or set via Railway dashboard")
    print()

if not issues:
    print("3. Check Railway logs for startup errors:")
    print("   - railway logs --service eac4079c-506c-4eab-a6d2-49bd860379de")
    print()

print("4. Restart Railway service after fixing:")
print("   - railway up --detach")
print()

print("=" * 80)
