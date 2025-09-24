@echo off
echo 🚀 Starting RSS News Bot...
echo 📱 Bot: @rssnewsusabot

set TELEGRAM_BOT_TOKEN=7477585710:AAG7iuQRm1EZsKoDzDf5yZtqxkaPU7i2frk
set PG_DSN=postgresql://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway?sslmode=disable

echo ✅ Environment configured
echo 🔄 Starting bot polling...
echo.
echo 💬 Send messages to @rssnewsusabot to test!
echo ⏹️  Press Ctrl+C to stop bot
echo.

python run_bot.py

pause