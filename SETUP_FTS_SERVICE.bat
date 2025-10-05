@echo off
REM Quick setup script for FTS service environment variables (Windows)
REM Service ID: ffe65f79-4dc5-4757-b772-5a99c7ea624f

echo =========================================
echo FTS Service Environment Setup
echo =========================================
echo.

REM Link to FTS service
echo 1. Linking to FTS service...
railway link --service ffe65f79-4dc5-4757-b772-5a99c7ea624f

if %ERRORLEVEL% NEQ 0 (
    echo Failed to link to service. Please check Railway CLI is installed and authenticated.
    exit /b 1
)

echo ✅ Linked to FTS service
echo.

REM Set environment variables
echo 2. Setting environment variables...

railway variables --set SERVICE_MODE=fts-continuous
echo    ✅ SERVICE_MODE=fts-continuous

railway variables --set FTS_CONTINUOUS_INTERVAL=60
echo    ✅ FTS_CONTINUOUS_INTERVAL=60

railway variables --set FTS_BATCH=100000
echo    ✅ FTS_BATCH=100000

echo.
echo 3. Restarting service...
railway restart

echo.
echo =========================================
echo ✅ Setup complete!
echo =========================================
echo.
echo Next steps:
echo 1. Wait 30-60 seconds for service to restart
echo 2. Check logs: railway logs --tail 50
echo 3. Verify mode: Should see 'python services/fts_service.py service...'
echo.
echo To monitor FTS progress:
echo   railway logs --follow
echo.
pause
