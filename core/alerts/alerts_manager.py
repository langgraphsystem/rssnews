"""
Phase 4 Alerts Manager
Monitors metrics and triggers alerts based on conditions.
"""

import logging
import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import asyncpg

logger = logging.getLogger(__name__)


class AlertsManager:
    """Manages alert rules and monitoring"""

    def __init__(self, pg_dsn: Optional[str] = None):
        self.pg_dsn = pg_dsn or os.getenv('PG_DSN')
        self._pool: Optional[asyncpg.Pool] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the alert monitoring background worker"""
        if not self._running:
            self._running = True
            self._monitor_task = asyncio.create_task(self._monitor_alerts_loop())
            logger.info("[AlertsManager] Alert monitoring started")

    async def stop(self):
        """Stop the alert monitoring"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("[AlertsManager] Alert monitoring stopped")

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

    async def create_alert(
        self,
        user_id: str,
        chat_id: str,
        name: str,
        condition: str,  # e.g., "roi < 200", "ctr > 0.05"
        time_window: str = "5m",
        severity: str = "P2",
        action: str = "notify",
        cooldown_minutes: int = 60
    ) -> Optional[int]:
        """
        Create a new alert rule.

        Args:
            user_id: User ID
            chat_id: Telegram chat ID
            name: Alert name
            condition: Condition string (e.g., "roi < 200")
            time_window: Time window to evaluate
            severity: Alert severity ('P1', 'P2', 'P3')
            action: Alert action ('notify', 'page', 'throttle')
            cooldown_minutes: Cooldown period before re-triggering

        Returns:
            Alert ID if successful
        """
        try:
            # Parse condition
            metric, operator, threshold = self._parse_condition(condition)

            if not metric or not operator or threshold is None:
                logger.error(f"[AlertsManager] Invalid condition: {condition}")
                return None

            pool = await self._get_pool()

            async with pool.acquire() as conn:
                alert_id = await conn.fetchval(
                    """
                    INSERT INTO phase4_alerts
                    (user_id, chat_id, name, condition, metric, threshold, operator, time_window, severity, action, cooldown_minutes, enabled)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, TRUE)
                    RETURNING id
                    """,
                    user_id,
                    chat_id,
                    name,
                    condition,
                    metric,
                    threshold,
                    operator,
                    time_window,
                    severity,
                    action,
                    cooldown_minutes
                )

            logger.info(f"[AlertsManager] Created alert {alert_id}: {name} ({condition})")
            return alert_id

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to create alert: {e}")
            return None

    async def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE phase4_alerts SET enabled = FALSE WHERE id = $1",
                    alert_id
                )

            logger.info(f"[AlertsManager] Deleted alert {alert_id}")
            return True

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to delete alert {alert_id}: {e}")
            return False

    async def get_user_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all alerts for a user"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, name, condition, metric, threshold, operator, time_window, severity, action, enabled, last_triggered, trigger_count
                    FROM phase4_alerts
                    WHERE user_id = $1 AND enabled = TRUE
                    ORDER BY severity, name
                    """,
                    user_id
                )

            return [
                {
                    "id": row['id'],
                    "name": row['name'],
                    "condition": row['condition'],
                    "metric": row['metric'],
                    "threshold": float(row['threshold']),
                    "operator": row['operator'],
                    "time_window": row['time_window'],
                    "severity": row['severity'],
                    "action": row['action'],
                    "enabled": row['enabled'],
                    "last_triggered": row['last_triggered'].isoformat() + "Z" if row['last_triggered'] else None,
                    "trigger_count": row['trigger_count']
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to get alerts for user {user_id}: {e}")
            return []

    async def _monitor_alerts_loop(self):
        """Background loop to check alerts every minute"""
        while self._running:
            try:
                await self._check_all_alerts()
                await asyncio.sleep(60)  # Check every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AlertsManager] Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _check_all_alerts(self):
        """Check all enabled alerts"""
        try:
            pool = await self._get_pool()

            async with pool.acquire() as conn:
                alerts = await conn.fetch(
                    """
                    SELECT id, user_id, chat_id, name, metric, threshold, operator, time_window, severity, action, cooldown_minutes, last_triggered
                    FROM phase4_alerts
                    WHERE enabled = TRUE
                    """
                )

            for alert in alerts:
                try:
                    await self._check_alert(alert)
                except Exception as e:
                    logger.error(f"[AlertsManager] Failed to check alert {alert['id']}: {e}")

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to fetch alerts: {e}")

    async def _check_alert(self, alert: asyncpg.Record):
        """Check if a single alert should trigger"""
        alert_id = alert['id']
        metric = alert['metric']
        threshold = float(alert['threshold'])
        operator = alert['operator']
        time_window = alert['time_window']
        cooldown_minutes = alert['cooldown_minutes']
        last_triggered = alert['last_triggered']

        # Check cooldown
        if last_triggered:
            cooldown_expires = last_triggered + timedelta(minutes=cooldown_minutes)
            if datetime.utcnow() < cooldown_expires:
                return  # Still in cooldown

        # Fetch current metric value
        from core.history.phase4_history_service import get_phase4_history_service

        history_service = get_phase4_history_service()

        # Parse time_window to hours
        hours_map = {
            '1m': 0.0166, '5m': 0.083, '10m': 0.166, '30m': 0.5,
            '1h': 1, '6h': 6, '12h': 12, '24h': 24
        }
        hours_back = hours_map.get(time_window, 0.083)  # default 5m

        agg = await history_service.get_metric_aggregate(
            metric=metric,
            user_id=alert['user_id'],
            hours_back=hours_back
        )

        if not agg:
            return  # No data available

        current_value = agg['latest']

        # Evaluate condition
        triggered = self._evaluate_condition(current_value, operator, threshold)

        if triggered:
            await self._trigger_alert(alert, current_value)

    def _evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Evaluate if condition is met"""
        if operator == '<':
            return value < threshold
        elif operator == '<=':
            return value <= threshold
        elif operator == '>':
            return value > threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '==':
            return abs(value - threshold) < 0.0001
        elif operator == '!=':
            return abs(value - threshold) >= 0.0001
        else:
            return False

    async def _trigger_alert(self, alert: asyncpg.Record, current_value: float):
        """Trigger an alert and send notification"""
        try:
            alert_id = alert['id']
            user_id = alert['user_id']
            chat_id = alert['chat_id']
            name = alert['name']
            metric = alert['metric']
            threshold = float(alert['threshold'])
            operator = alert['operator']
            severity = alert['severity']
            action = alert['action']

            logger.warning(f"[AlertsManager] 🚨 Alert triggered: {name} ({metric} {operator} {threshold}, current: {current_value})")

            # Update alert record
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE phase4_alerts
                    SET last_triggered = NOW(), trigger_count = trigger_count + 1
                    WHERE id = $1
                    """,
                    alert_id
                )

                # Log alert history
                await conn.execute(
                    """
                    INSERT INTO phase4_alert_history (alert_id, triggered_at, metric_value, threshold, condition, notification_sent)
                    VALUES ($1, NOW(), $2, $3, $4, FALSE)
                    """,
                    alert_id,
                    current_value,
                    threshold,
                    f"{metric} {operator} {threshold}"
                )

            # Send notification
            await self._send_alert_notification(
                chat_id=chat_id,
                name=name,
                metric=metric,
                current_value=current_value,
                threshold=threshold,
                operator=operator,
                severity=severity,
                action=action
            )

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to trigger alert {alert['id']}: {e}", exc_info=True)

    async def _send_alert_notification(
        self,
        chat_id: str,
        name: str,
        metric: str,
        current_value: float,
        threshold: float,
        operator: str,
        severity: str,
        action: str
    ):
        """Send alert notification to Telegram"""
        try:
            from bot_service.advanced_bot import AdvancedRSSBot
            import os

            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                logger.warning("[AlertsManager] TELEGRAM_BOT_TOKEN not configured")
                return

            bot = AdvancedRSSBot(bot_token)

            # Format message
            severity_emoji = "🔴" if severity == "P1" else "🟡" if severity == "P2" else "🟢"

            text = f"""🚨 **Alert Triggered: {name}**

{severity_emoji} **Severity:** {severity}
📊 **Metric:** {metric}
📈 **Current Value:** {current_value:.4f}
🎯 **Threshold:** {operator} {threshold:.4f}
⚙️ **Action:** {action}

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

            await bot._send_message(chat_id, text)

            logger.info(f"[AlertsManager] Sent alert notification to chat {chat_id}")

        except Exception as e:
            logger.error(f"[AlertsManager] Failed to send alert notification: {e}", exc_info=True)

    def _parse_condition(self, condition: str) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Parse condition string like "roi < 200" or "ctr > 0.05".

        Returns:
            Tuple of (metric, operator, threshold)
        """
        try:
            # Match patterns like: metric operator number
            pattern = r'^(\w+)\s*([<>!=]+)\s*([\d.]+)$'
            match = re.match(pattern, condition.strip())

            if not match:
                return None, None, None

            metric = match.group(1)
            operator = match.group(2)
            threshold = float(match.group(3))

            # Validate operator
            if operator not in ('<', '<=', '>', '>=', '==', '!='):
                return None, None, None

            return metric, operator, threshold

        except Exception:
            return None, None, None


# Singleton instance
_alerts_manager: Optional[AlertsManager] = None


def get_alerts_manager() -> AlertsManager:
    """Get or create AlertsManager singleton"""
    global _alerts_manager
    if _alerts_manager is None:
        _alerts_manager = AlertsManager()
    return _alerts_manager


async def start_alerts_manager():
    """Start the global alerts manager"""
    manager = get_alerts_manager()
    await manager.start()


async def stop_alerts_manager():
    """Stop the global alerts manager"""
    manager = get_alerts_manager()
    await manager.stop()
