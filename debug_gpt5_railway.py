#!/usr/bin/env python3
"""
Debug GPT-5 on Railway - Detailed logging and testing
"""

import os
import sys
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gpt5_railway_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check all environment variables"""
    logger.info("🔍 Checking environment variables...")

    env_vars = [
        'OPENAI_API_KEY',
        'PG_DSN',
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID'
    ]

    for var in env_vars:
        value = os.environ.get(var)
        if value:
            masked_value = value[:8] + '***' + value[-4:] if len(value) > 12 else '***'
            logger.info(f"✅ {var}: {masked_value}")
        else:
            logger.warning(f"❌ {var}: NOT SET")

    return all(os.environ.get(var) for var in env_vars)

async def test_gpt5_service():
    """Test GPT-5 service directly"""
    logger.info("🤖 Testing GPT-5 service...")

    try:
        from gpt5_service_new import GPT5Service
        logger.info("✅ GPT5Service imported successfully")

        service = GPT5Service()
        logger.info("✅ GPT5Service instance created")

        # Test simple prompt
        test_prompt = "Проанализируй: RSS система обрабатывает 1000 статей в день. Как оптимизировать?"
        logger.info(f"📝 Testing with prompt: {test_prompt[:50]}...")

        response = service.send_insights(test_prompt)
        logger.info(f"✅ GPT-5 response received (length: {len(response)})")
        logger.info(f"📄 Response preview: {response[:200]}...")

        return response

    except Exception as e:
        logger.error(f"❌ GPT-5 service test failed: {e}")
        logger.error(f"🔍 Full traceback:\n{traceback.format_exc()}")
        return None

async def test_system_stats_reporter():
    """Test system stats reporter with detailed logging"""
    logger.info("📊 Testing SystemStatsReporter...")

    try:
        # Load environment from .env file first
        try:
            from dotenv import load_dotenv
            load_dotenv()
            logger.info("✅ .env file loaded")
        except ImportError:
            logger.warning("⚠️ dotenv not available, using system env only")

        from system_stats_reporter import SystemStatsReporter
        logger.info("✅ SystemStatsReporter imported successfully")

        reporter = SystemStatsReporter()
        logger.info("✅ SystemStatsReporter instance created")

        # Test LLM insights generation
        mock_stats = {
            'feeds': {'active_feeds': 118, 'total_feeds': 118, 'healthy_feeds': 118},
            'articles': {'total_articles': 15583, 'recent_24h': 1028, 'status_counts': {'True': 13, 'False': 15570}},
            'chunks': {'total_chunks': 175913, 'recent_24h': 5925, 'processing_stages': {'complete': 175822, 'needs_fts': 91}},
            'embeddings': {'embedded_chunks': 175913, 'pending_embeddings': 0, 'completion_rate': 100.0},
            'services': {'service_manager_running': False, 'llm_connectivity': True}
        }

        logger.info("📋 Testing with mock statistics...")
        logger.info(f"🔢 Mock stats: {json.dumps(mock_stats, indent=2)}")

        insights = await reporter.generate_llm_insights(mock_stats)
        logger.info(f"✅ Insights generated (length: {len(insights)})")
        logger.info(f"📄 Insights preview: {insights[:300]}...")

        return insights

    except Exception as e:
        logger.error(f"❌ SystemStatsReporter test failed: {e}")
        logger.error(f"🔍 Full traceback:\n{traceback.format_exc()}")
        return None

async def test_full_report():
    """Test full report generation"""
    logger.info("📈 Testing full report generation...")

    try:
        from system_stats_reporter import SystemStatsReporter
        reporter = SystemStatsReporter()

        logger.info("🔄 Collecting full report...")
        stats = await reporter.collect_full_report()

        logger.info(f"✅ Full report collected")
        logger.info(f"📊 Report keys: {list(stats.keys())}")

        if 'llm_insights' in stats:
            insights = stats['llm_insights']
            logger.info(f"🤖 LLM insights length: {len(insights)}")
            logger.info(f"📄 LLM insights preview: {insights[:200]}...")

            if insights.startswith("GPT-5 анализ недоступен"):
                logger.error("❌ GPT-5 analysis failed in full report")
                logger.error(f"❌ Error: {insights}")
            else:
                logger.info("✅ GPT-5 analysis successful in full report")
        else:
            logger.error("❌ No llm_insights in report")

        return stats

    except Exception as e:
        logger.error(f"❌ Full report test failed: {e}")
        logger.error(f"🔍 Full traceback:\n{traceback.format_exc()}")
        return None

async def main():
    """Main debugging function"""
    logger.info("🚀 Starting GPT-5 Railway Debug Session")
    logger.info(f"⏰ Time: {datetime.now()}")
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"📍 Working directory: {os.getcwd()}")

    # Step 1: Check environment
    logger.info("\n" + "="*50)
    logger.info("STEP 1: Environment Check")
    logger.info("="*50)
    env_ok = check_environment()

    if not env_ok:
        logger.error("❌ Environment variables missing, cannot continue")
        return

    # Step 2: Test GPT-5 service directly
    logger.info("\n" + "="*50)
    logger.info("STEP 2: Direct GPT-5 Service Test")
    logger.info("="*50)
    gpt5_result = await test_gpt5_service()

    if not gpt5_result:
        logger.error("❌ Direct GPT-5 service test failed, cannot continue")
        return

    # Step 3: Test system stats reporter
    logger.info("\n" + "="*50)
    logger.info("STEP 3: SystemStatsReporter Test")
    logger.info("="*50)
    reporter_result = await test_system_stats_reporter()

    # Step 4: Test full report
    logger.info("\n" + "="*50)
    logger.info("STEP 4: Full Report Test")
    logger.info("="*50)
    full_report = await test_full_report()

    # Summary
    logger.info("\n" + "="*50)
    logger.info("SUMMARY")
    logger.info("="*50)

    results = {
        'environment': env_ok,
        'gpt5_direct': bool(gpt5_result),
        'reporter_insights': bool(reporter_result),
        'full_report': bool(full_report and full_report.get('llm_insights', '').strip())
    }

    logger.info(f"📋 Test results: {json.dumps(results, indent=2)}")

    if all(results.values()):
        logger.info("🎉 All tests PASSED - GPT-5 should work on Railway")
    else:
        logger.error("❌ Some tests FAILED - check logs above for details")
        failed_tests = [test for test, result in results.items() if not result]
        logger.error(f"❌ Failed tests: {failed_tests}")

    logger.info("🏁 Debug session completed")
    logger.info(f"📝 Detailed log saved to: gpt5_railway_debug.log")

if __name__ == "__main__":
    asyncio.run(main())