"""
Phase 4 Schedule Manager
Manages scheduled reports and recurring tasks using APScheduler.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class ScheduleManager:
    """Manages scheduled tasks (reports, alerts, etc.)"""

    def __init__(self, pg_dsn: Optional[str] = None):
        self.pg_dsn = pg_dsn or os.getenv('PG_DSN')
        self._pool: Optional[asyncpg.Pool] = None
        self.scheduler: Optional[AsyncIOScheduler] = None

    async def start(self):
        """Start the scheduler"""
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler()
            self.scheduler.start()
            logger.info("[ScheduleManager] Scheduler started")

            # Load existing schedules from database
            await self._load_schedules_from_db()

    async def stop(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("[ScheduleManager] Scheduler stopped")

        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool"""
        if self._pool is None:
            if not self.pg_dsn:
                raise ValueError("PG_DSN not configured")

            self._pool = await asyncpg.create_pool(
                self.pg_dsn,
                min_size=2,
                max_size=5
            )

        return self._pool

    async def create_report_schedule(
        self,
        user_id: str,
        chat_id: str,
        report_type: str,  # 'weekly', 'monthly', 'daily'
        cron_expression: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Create a new report schedule.

        Args:
            user_id: User ID
            chat_id: Telegram chat ID
            report_type: Report type
            cron_expression: Cron expression (e.g., '0 9 * * 1')
            params: Additional parameters (audience, metrics, lang, etc.)

        Returns:
            Schedule ID if successful
        """
        try:
            pool = await self._get_pool()

            # Calculate next run time
            trigger = CronTrigger.from_crontab(cron_expression)
            next_run = trigger.get_next_fire_time(None, datetime.utcnow())

            async with pool.acquire() as conn:
                schedule_id = await conn.fetchval(
                    """
                    INSERT INTO phase4_schedules
                    (user_id, chat_id, schedule_type, report_type, cron_expression, next_run, params, enabled)
                    VALUES ($1, $2, 'report', $3, $4, $5, $6, TRUE)
                    RETURNING id
                    """,
                    user_id,
                    chat_id,
                    report_type,
                    cron_expression,
                    next_run,
                    params or {}
                )

            # Add job to scheduler
            if self.scheduler:
                job_id = f"report_{schedule_id}"
                self.scheduler.add_job(
                    func=self._execute_report_schedule,
                    trigger=trigger,
                    id=job_id,
                    args=[schedule_id, user_id, chat_id, report_type, params or {}],
                    replace_existing=True
                )

            logger.info(f"[ScheduleManager] Created schedule {schedule_id}: {report_type} report for user {user_id}")
            return schedule_id

        except Exception as e:
            logger.error(f"[ScheduleManager] Failed to create schedule: {e}")
            return None

    async def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE phase4_schedules SET enabled = FALSE WHERE id = $1",
                    schedule_id
                )

            # Remove job from scheduler
            if self.scheduler:
                job_id = f"report_{schedule_id}"
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    pass

            logger.info(f"[ScheduleManager] Deleted schedule {schedule_id}")
            return True

        except Exception as e:
            logger.error(f"[ScheduleManager] Failed to delete schedule {schedule_id}: {e}")
            return False

    async def get_user_schedules(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all schedules for a user"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, schedule_type, report_type, cron_expression, enabled, next_run, last_run, params
                    FROM phase4_schedules
                    WHERE user_id = $1 AND enabled = TRUE
                    ORDER BY next_run
                    """,
                    user_id
                )

            return [
                {
                    "id": row['id'],
                    "schedule_type": row['schedule_type'],
                    "report_type": row['report_type'],
                    "cron_expression": row['cron_expression'],
                    "enabled": row['enabled'],
                    "next_run": row['next_run'].isoformat() + "Z" if row['next_run'] else None,
                    "last_run": row['last_run'].isoformat() + "Z" if row['last_run'] else None,
                    "params": row['params']
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"[ScheduleManager] Failed to get schedules for user {user_id}: {e}")
            return []

    async def _load_schedules_from_db(self):
        """Load existing schedules from database and add to scheduler"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, chat_id, report_type, cron_expression, params
                    FROM phase4_schedules
                    WHERE enabled = TRUE AND schedule_type = 'report'
                    """
                )

            loaded_count = 0
            for row in rows:
                try:
                    schedule_id = row['id']
                    user_id = row['user_id']
                    chat_id = row['chat_id']
                    report_type = row['report_type']
                    cron_expression = row['cron_expression']
                    params = row['params'] or {}

                    trigger = CronTrigger.from_crontab(cron_expression)
                    job_id = f"report_{schedule_id}"

                    self.scheduler.add_job(
                        func=self._execute_report_schedule,
                        trigger=trigger,
                        id=job_id,
                        args=[schedule_id, user_id, chat_id, report_type, params],
                        replace_existing=True
                    )

                    loaded_count += 1

                except Exception as e:
                    logger.error(f"[ScheduleManager] Failed to load schedule {row['id']}: {e}")

            logger.info(f"[ScheduleManager] Loaded {loaded_count} schedules from database")

        except Exception as e:
            logger.error(f"[ScheduleManager] Failed to load schedules: {e}")

    async def _execute_report_schedule(
        self,
        schedule_id: int,
        user_id: str,
        chat_id: str,
        report_type: str,
        params: Dict[str, Any]
    ):
        """Execute a scheduled report (called by APScheduler)"""
        try:
            logger.info(f"[ScheduleManager] Executing schedule {schedule_id}: {report_type} report")

            # Update last_run
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE phase4_schedules SET last_run = NOW() WHERE id = $1",
                    schedule_id
                )

            # Generate and send report
            from services.phase4_handlers import get_phase4_handler_service

            service = get_phase4_handler_service()
            payload = await service.handle_reports_command(
                action="generate",
                period=report_type,
                audience=params.get("audience"),
                window="1w" if report_type == "weekly" else "1m",
                lang=params.get("lang", "ru"),
                correlation_id=f"scheduled-{schedule_id}"
            )

            # Send via bot
            from bot_service.advanced_bot import AdvancedRSSBot
            import os

            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if bot_token:
                bot = AdvancedRSSBot(bot_token)

                text = f"📅 **Scheduled {report_type.capitalize()} Report**\n\n" + payload.get("text", "")

                await bot._send_long_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=None,
                    parse_mode="Markdown"
                )

                logger.info(f"[ScheduleManager] Sent scheduled report {schedule_id} to chat {chat_id}")
            else:
                logger.warning("[ScheduleManager] TELEGRAM_BOT_TOKEN not configured, cannot send scheduled report")

        except Exception as e:
            logger.error(f"[ScheduleManager] Failed to execute schedule {schedule_id}: {e}", exc_info=True)


# Singleton instance
_schedule_manager: Optional[ScheduleManager] = None


def get_schedule_manager() -> ScheduleManager:
    """Get or create ScheduleManager singleton"""
    global _schedule_manager
    if _schedule_manager is None:
        _schedule_manager = ScheduleManager()
    return _schedule_manager


async def start_schedule_manager():
    """Start the global schedule manager"""
    manager = get_schedule_manager()
    await manager.start()


async def stop_schedule_manager():
    """Stop the global schedule manager"""
    manager = get_schedule_manager()
    await manager.stop()
