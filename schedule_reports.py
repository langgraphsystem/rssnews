"""
Scheduler for automatic RSS News system reports
Sends reports to Telegram at specified intervals
"""

import asyncio
import schedule
import time
import logging
from datetime import datetime
import os

# Set environment
os.environ['PG_DSN'] = 'postgres://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway'

from system_stats_reporter import SystemStatsReporter

logger = logging.getLogger(__name__)

class ReportScheduler:
    """Automatic report scheduler"""

    def __init__(self):
        self.reporter = SystemStatsReporter()

    async def send_scheduled_report(self):
        """Send a scheduled report"""
        try:
            print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Generating scheduled report...")

            # Collect and send report
            stats = await self.reporter.collect_full_report()
            bot_message = self.reporter.format_report_for_bot(stats)

            success = await self.reporter.send_to_telegram(bot_message)

            if success:
                print("✅ Scheduled report sent successfully!")
            else:
                print("⚠️ Scheduled report failed to send")

        except Exception as e:
            print(f"❌ Error in scheduled report: {e}")
            logger.error(f"Scheduled report error: {e}")

    def setup_schedule(self):
        """Setup report schedule"""
        # Schedule options - uncomment the one you want:

        # Every 6 hours
        schedule.every(6).hours.do(lambda: asyncio.run(self.send_scheduled_report()))

        # Daily at 9 AM
        # schedule.every().day.at("09:00").do(lambda: asyncio.run(self.send_scheduled_report()))

        # Every 12 hours
        # schedule.every(12).hours.do(lambda: asyncio.run(self.send_scheduled_report()))

        # Custom times - every day at specific hours
        # schedule.every().day.at("06:00").do(lambda: asyncio.run(self.send_scheduled_report()))
        # schedule.every().day.at("12:00").do(lambda: asyncio.run(self.send_scheduled_report()))
        # schedule.every().day.at("18:00").do(lambda: asyncio.run(self.send_scheduled_report()))

        print("📅 Report scheduler configured:")
        print("   • Every 6 hours")
        print("   • Modify schedule_reports.py to change frequency")

    def run_forever(self):
        """Run the scheduler forever"""
        self.setup_schedule()

        print("🚀 Report scheduler started...")
        print("📊 Next report:", schedule.next_run())

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n⏹️ Scheduler stopped by user")

async def send_test_report():
    """Send a test report immediately"""
    scheduler = ReportScheduler()
    await scheduler.send_scheduled_report()

def main():
    """Main function"""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Send test report
        print("🧪 Sending test report...")
        asyncio.run(send_test_report())
    else:
        # Start scheduler
        scheduler = ReportScheduler()
        scheduler.run_forever()

if __name__ == "__main__":
    main()