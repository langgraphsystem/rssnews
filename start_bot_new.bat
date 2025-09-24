@echo off
echo 🚀 Starting RSS News Bot with 2025 Best Practices...
echo 📱 Bot: @rssnewsusabot
echo.

set TELEGRAM_BOT_TOKEN=7477585710:AAG7iuQRm1EZsKoDzDf5yZtqxkaPU7i2frk
set PG_DSN=postgresql://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway?sslmode=disable

echo ✅ Environment configured
echo 🚦 Rate Limiting: ENABLED
echo 🚨 Error Handling: ENABLED
echo 📊 Structured Logging: ENABLED
echo.
echo 🔄 Starting bot...
echo.
echo 💬 Send messages to @rssnewsusabot to test!
echo ⏹️  Press Ctrl+C to stop bot
echo.

python start_telegram_bot.py

pause