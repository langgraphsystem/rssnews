#!/bin/bash
# Quick setup script for Railway deployment

echo "🚀 Railway OpenAI Embedding Service Setup"
echo "=========================================="
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found!"
    echo "   Install: npm install -g @railway/cli"
    exit 1
fi

echo "✅ Railway CLI found"
echo ""

# Prompt for API key
echo "📝 Please provide your OpenAI API key:"
read -p "OPENAI_API_KEY: " api_key

if [ -z "$api_key" ]; then
    echo "❌ API key is required"
    exit 1
fi

echo ""
echo "🔧 Setting Railway environment variables..."

# Set environment variables
railway vars set OPENAI_API_KEY="$api_key"
railway vars set OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
railway vars set OPENAI_EMBEDDING_SERVICE_ENABLED="true"
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="100"
railway vars set OPENAI_EMBEDDING_MAX_RETRIES="3"
railway vars set ENABLE_LOCAL_EMBEDDINGS="false"
railway vars set EMBEDDING_TIMEOUT="30"

echo "✅ Environment variables set"
echo ""

echo "📊 Current configuration:"
railway vars | grep -E "OPENAI|EMBEDDING"
echo ""

echo "🚀 Deploying to Railway..."
railway up

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Check status: railway status"
echo "   2. View logs: railway logs --service embedding-worker"
echo "   3. Check backlog: railway run python check_backlog.py"
echo ""
echo "🎉 Done!"
