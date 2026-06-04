import os
import time
import gzip
import shutil
import datetime
import asyncio
import aiohttp
import psutil
import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger
import dashboard

class CircuitBreaker:
    """Circuit Breaker pattern implementation for external webhook requests."""
    
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 300):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_state_change = 0.0

    def can_attempt(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_state_change > self.cooldown_seconds:
                self.state = "HALF_OPEN"
                logger.info("Circuit Breaker transitioned to HALF_OPEN. Retrying webhook.")
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self) -> None:
        if self.state != "CLOSED":
            logger.info("Circuit Breaker transitioned to CLOSED. Webhook communication restored.")
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and self.state != "OPEN":
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.warning(f"Circuit Breaker transitioned to OPEN. Disabling webhooks for {self.cooldown_seconds}s.")


class HealthCog(commands.Cog):
    """Cog monitoring system metrics, pings, heartbeat, and database health, with daily cleanups."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.models = bot.models
        self.metrics = bot.metrics
        self.start_time = time.time()
        
        self.circuit_breaker = CircuitBreaker()
        self.cpu_high_ticks = 0  # To track CPU > 80% for 5+ minutes
        
        # Start loops
        self.health_check_loop.start()
        self.heartbeat_loop.start()
        self.cleanup_loop.start()

    def cog_unload(self) -> None:
        self.health_check_loop.cancel()
        self.heartbeat_loop.cancel()
        self.cleanup_loop.cancel()

    async def send_alert_webhook(self, title: str, description: str, severity: str) -> None:
        """Sends an alert embed to the configured Discord audit webhook URL, protected by a circuit breaker."""
        webhook_url = self.bot.bot_config.discord_audit_webhook_url
        if not webhook_url or not webhook_url.startswith("http"):
            return

        if not self.circuit_breaker.can_attempt():
            logger.warning("Alert webhook skipped: Circuit Breaker is OPEN.")
            return

        color = 15539236 if severity == "critical" else 16102155  # Red or Gold
        payload = {
            "embeds": [{
                "title": f"🚨 System Health Alert: {title}",
                "description": description,
                "color": color,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=10) as resp:
                    if resp.status == 200 or resp.status == 204:
                        self.circuit_breaker.record_success()
                    else:
                        logger.error(f"Webhook failed with status {resp.status}")
                        self.circuit_breaker.record_failure()
        except Exception as e:
            logger.error(f"Failed to transmit alert webhook: {e}")
            self.circuit_breaker.record_failure()

    @tasks.loop(minutes=5)
    async def health_check_loop(self) -> None:
        """Runs periodic system resource checks every 5 minutes."""
        await self.bot.wait_until_ready()
        await self.perform_health_checks()

    async def perform_health_checks(self) -> dict:
        """Executes disk space, memory utilization, cpu overhead and db integrity checks."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_alerts = []
        status_report = {}

        # 1. Disk Space check
        try:
            free_gb = psutil.disk_usage('.').free / (1024 ** 3)
            status_report["disk_free_gb"] = free_gb
            if free_gb < 1.0:
                alert = {
                    "type": "DiskSpaceLow",
                    "severity": "critical",
                    "message": f"Disk space is low: {free_gb:.2f} GB free.",
                    "timestamp": now_ts
                }
                current_alerts.append(alert)
                await self.send_alert_webhook("Low Disk Space", alert["message"], "critical")
        except Exception as e:
            status_report["disk_check_error"] = str(e)

        # 2. Memory RSS check
        try:
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            status_report["memory_rss_mb"] = mem_mb
            uptime = time.time() - self.start_time
            if mem_mb > 500.0 and uptime > 86400: # Over 24h
                alert = {
                    "type": "MemoryHigh",
                    "severity": "warning",
                    "message": f"Memory footprint exceeds 500MB: {mem_mb:.2f} MB RSS after 24h runtime.",
                    "timestamp": now_ts
                }
                current_alerts.append(alert)
                await self.send_alert_webhook("High Memory Footprint", alert["message"], "warning")
        except Exception as e:
            status_report["memory_check_error"] = str(e)

        # 3. CPU Overload check (>80% for 5+ minutes/consecutive checks)
        try:
            cpu_usage = psutil.cpu_percent(interval=None)
            status_report["cpu_percent"] = cpu_usage
            if cpu_usage > 80.0:
                self.cpu_high_ticks += 1
                if self.cpu_high_ticks >= 2: # Exceeded 80% for 5+ minutes
                    alert = {
                        "type": "CpuOverload",
                        "severity": "warning",
                        "message": f"High CPU utilization: {cpu_usage:.2f}% sustained for 5+ minutes.",
                        "timestamp": now_ts
                    }
                    current_alerts.append(alert)
                    await self.send_alert_webhook("Sustained CPU Overload", alert["message"], "warning")
            else:
                self.cpu_high_ticks = 0
        except Exception as e:
            status_report["cpu_check_error"] = str(e)

        # 4. Database Integrity Check
        try:
            row = await self.db.fetchone("PRAGMA integrity_check;")
            db_status = row["integrity_check"] if row else "failed"
            status_report["db_integrity"] = db_status
            if db_status != "ok":
                alert = {
                    "type": "DatabaseCorruption",
                    "severity": "critical",
                    "message": f"Database integrity check failed: status is '{db_status}'.",
                    "timestamp": now_ts
                }
                current_alerts.append(alert)
                await self.send_alert_webhook("Database Corruption Alert", alert["message"], "critical")
        except Exception as e:
            status_report["db_check_error"] = str(e)

        # 5. Error rate metrics
        try:
            guild_id = "SYSTEM"
            err_count = await self.metrics.get("error_count_24h", guild_id) or 0
            status_report["errors_24h"] = err_count
            if err_count > 10:
                alert = {
                    "type": "HighErrorRate",
                    "severity": "warning",
                    "message": f"High error count in rolling 24h: {err_count} errors.",
                    "timestamp": now_ts
                }
                current_alerts.append(alert)
                await self.send_alert_webhook("High Error Rate Alert", alert["message"], "warning")
        except Exception:
            pass

        # Update Dashboard alert cache
        dashboard._active_alerts = current_alerts
        status_report["alerts_active"] = len(current_alerts)
        return status_report

    @tasks.loop(seconds=60)
    async def heartbeat_loop(self) -> None:
        """Monitors Discord Gateway heartbeat connection latency every 60 seconds."""
        await self.bot.wait_until_ready()
        
        latency_ms = self.bot.latency * 1000.0
        # Alert if latency > 5000ms
        if latency_ms > 5000.0:
            now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            alert = {
                "type": "HighLatency",
                "severity": "warning",
                "message": f"Discord WebSocket connection latency is extremely high: {latency_ms:.2f} ms.",
                "timestamp": now_ts
            }
            # Append to active dashboard alerts if not already present
            if not any(a["type"] == "HighLatency" for a in dashboard._active_alerts):
                dashboard._active_alerts.append(alert)
                await self.send_alert_webhook("High Gateway Latency", alert["message"], "warning")
        else:
            # Clean up high latency alert if resolved
            dashboard._active_alerts = [a for a in dashboard._active_alerts if a["type"] != "HighLatency"]

    @tasks.loop(hours=24)
    async def cleanup_loop(self) -> None:
        """Performs daily cleanup of old rotated logs, gz compression, and backup retention rules."""
        await self.bot.wait_until_ready()
        
        logger.info("Starting daily health log cleanup and backup retention checks...")
        now = time.time()
        thirty_days = 30 * 86400
        retention_days = self.bot.bot_config.gdpr_retention_days
        retention_seconds = retention_days * 86400

        # 1. Logs compression and deletion
        logs_dir = "logs"
        if os.path.exists(logs_dir):
            for file_name in os.listdir(logs_dir):
                file_path = os.path.join(logs_dir, file_name)
                if not os.path.isfile(file_path):
                    continue

                # Delete logs older than 30 days
                file_age = now - os.path.getmtime(file_path)
                if file_age > thirty_days:
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted old log file: {file_name}")
                    except Exception as e:
                        logger.error(f"Failed to delete old log {file_name}: {e}")
                    continue

                # Compress rotated logs (.log.1, .log.2, etc.) that are not already compressed (.gz)
                if (".log." in file_name or file_name.endswith(".log.old")) and not file_name.endswith(".gz"):
                    gz_path = f"{file_path}.gz"
                    try:
                        with open(file_path, 'rb') as f_in:
                            with gzip.open(gz_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(file_path)
                        logger.info(f"Compressed and removed rotated log file: {file_name}")
                    except Exception as e:
                        logger.error(f"Failed to compress log file {file_name}: {e}")

        # 2. Database backup retention pruning
        backups_base = "backups"
        if os.path.exists(backups_base):
            for category in ["daily", "weekly", "monthly"]:
                cat_path = os.path.join(backups_base, category)
                if os.path.exists(cat_path):
                    for file_name in os.listdir(cat_path):
                        file_path = os.path.join(cat_path, file_name)
                        if os.path.isfile(file_path) and file_name.endswith(".db"):
                            file_age = now - os.path.getmtime(file_path)
                            if file_age > retention_seconds:
                                try:
                                    os.remove(file_path)
                                    logger.info(f"Pruned backup {file_name} exceeding retention period ({retention_days} days).")
                                except Exception as e:
                                    logger.error(f"Failed to prune old backup {file_name}: {e}")

    # --- Slash Commands ---
    health = app_commands.Group(name="health", description="System health status commands")

    @health.command(name="status", description="Exposes current resource footprints, WebSocket metrics, and DB checks.")
    async def health_status(self, interaction: discord.Interaction) -> None:
        """Returns details on disk space, memory RSS, CPU, gateway latency and active alerts."""
        if interaction.user.id not in self.bot.bot_config.admin_user_ids and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return

        await interaction.response.defer()
        
        # Calculate stats
        uptime_sec = int(time.time() - self.start_time)
        days = uptime_sec // 86400
        hours = (uptime_sec % 86400) // 3600
        minutes = (uptime_sec % 3600) // 60
        uptime_str = f"{days}d, {hours}h, {minutes}m"

        try:
            free_gb = psutil.disk_usage('.').free / (1024 ** 3)
            mem_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            cpu_usage = psutil.cpu_percent(interval=None)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to fetch system parameters: {e}")
            return

        latency_ms = self.bot.latency * 1000.0
        alerts_count = len(dashboard._active_alerts)

        embed = discord.Embed(
            title="System Health Overview",
            color=discord.Color.green() if alerts_count == 0 else discord.Color.red()
        )
        embed.add_field(name="Bot Status", value="🟢 ONLINE" if not self.bot.is_closed() else "🔴 OFFLINE", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="WS Latency", value=f"{latency_ms:.1f} ms", inline=True)
        embed.add_field(name="CPU Overhead", value=f"{cpu_usage:.1f}%", inline=True)
        embed.add_field(name="Memory Footprint", value=f"{mem_mb:.2f} MB RSS", inline=True)
        embed.add_field(name="Disk Space Free", value=f"{free_gb:.2f} GB", inline=True)
        embed.add_field(name="Active Alerts", value=str(alerts_count), inline=False)

        await interaction.followup.send(embed=embed)

    @health.command(name="check", description="Manually execute all resource and database checks immediately.")
    async def health_check(self, interaction: discord.Interaction) -> None:
        """Forces immediate execution of resource, db and latency sweeps, updating metrics."""
        if interaction.user.id not in self.bot.bot_config.admin_user_ids and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        report = await self.perform_health_checks()
        
        lines = []
        for k, v in report.items():
            lines.append(f"• **{k}**: `{v}`")
        
        embed = discord.Embed(
            title="Manual Health Check Completed",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HealthCog(bot))
