import sys
from unittest.mock import MagicMock
# Mock audioop to support discord.py on Python 3.13/3.14 where it has been removed from stdlib
sys.modules['audioop'] = MagicMock()

# Force UTF-8 output on Windows to handle emoji in bot names/messages
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
import json
import signal
import asyncio
import traceback
import psutil
from typing import Set, Dict, Any, List
import discord
from discord.ext import commands
from loguru import logger
from dotenv import load_dotenv

import config_schema
from database import DatabaseManager
from database.models import DatabaseModels
from metrics import MetricsTracker

# Load env variables before doing anything
load_dotenv()

# --- Logging Setup ---
os.makedirs("logs", exist_ok=True)
logger.remove()  # Remove default handler

# Log to console
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

# Log to general log file
logger.add(
    "logs/bot.log",
    rotation="10 MB",
    retention=5,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
)

# Log to errors file
logger.add(
    "logs/errors.log",
    rotation="10 MB",
    retention=5,
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}"
)


class AntigravityBot(commands.Bot):
    """Production-grade Discord Bot with auto-recovery, intent checks, and crash dumps."""

    def __init__(self, bot_config: config_schema.BotConfig, db_manager: DatabaseManager, tracker: MetricsTracker):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        intents.reactions = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        self.bot_config = bot_config
        self.db = db_manager
        self.models = DatabaseModels(self.db)
        self.metrics = tracker

        self.loaded_cogs_list: List[str] = []
        self.is_shutting_down = False
        self.active_tasks: Set[asyncio.Task[Any]] = set()

    async def setup_hook(self) -> None:
        """Executed before connection. Validates gateway intents and loads cogs."""
        from pathlib import Path
        
        # 1. Pre-flight Gateway Intents Check
        logger.info("Performing pre-flight Gateway Intents check...")
        if not self.intents.members or not self.intents.message_content:
            err_msg = (
                "\nCRITICAL ERROR: Required Gateway Intents are missing!\n"
                "Ensure both 'GUILD MEMBERS INTENT' and 'MESSAGE CONTENT INTENT' are enabled in the Discord Developer Portal.\n"
                "Invite Link with correct permissions:\n"
                "https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands\n"
            )
            # Fetch application/client ID if possible or fall back
            client_id = "YOUR_BOT_CLIENT_ID"
            logger.error(err_msg.format(client_id=client_id))
            sys.exit(1)

        logger.info("Gateway Intents verified successfully.")

        # 2. Dynamic Cog Loading System
        # Load all cogs FIRST
        for cog_file in Path("cogs").rglob("cog.py"):
            cog_path = ".".join(cog_file.with_suffix("").parts)
            try:
                await self.load_extension(cog_path)
                self.loaded_cogs_list.append(cog_path)
                logger.info(f"✅ Loaded: {cog_path}")
            except Exception as e:
                logger.error(f"❌ Failed to load {cog_path}: {e}")
                logger.error(traceback.format_exc())
                raise  # Re-raise to stop bot if cog fails

        # Start dashboard background thread task
        from dashboard import start_dashboard
        task = asyncio.create_task(start_dashboard(self))
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

        # THEN sync commands with Discord (MUST be after cog loading)
        logger.info("🔄 Syncing slash commands with Discord...")
        try:
            # Sync globally (takes up to 1 hour to propagate)
            await self.tree.sync()
            logger.info("✅ Commands synced globally!")
            logger.info("⏳ Wait up to 1 hour for Discord to cache, or kick/re-invite bot for instant sync")
            
            # Fast test sync if configured
            test_guild_raw = os.getenv("TEST_GUILD_ID", "0")
            if test_guild_raw.isdigit():
                test_guild_id = int(test_guild_raw)
                if test_guild_id > 0:
                    self.tree.copy_global_to(guild=discord.Object(id=test_guild_id))
                    await self.tree.sync(guild=discord.Object(id=test_guild_id))
                    logger.info(f"✅ Commands synced to test guild {test_guild_id} (INSTANT!)")
            else:
                logger.warning(f"⚠️ TEST_GUILD_ID '{test_guild_raw}' is not a valid number. Skipping instant test guild sync.")
        except Exception as e:
            logger.error(f"❌ Command sync failed: {e}")
            raise

    async def on_ready(self) -> None:
        logger.info(f"Bot connected successfully as {self.user} (ID: {self.user.id})")

    async def shutdown(self) -> None:
        """Initiates a graceful shutdown, flushing metrics and saving state."""
        if self.is_shutting_down:
            return
        self.is_shutting_down = True
        logger.info("Graceful shutdown initiated...")

        # Unload cogs to trigger cleanup/saving queues
        for cog_name in list(self.cogs.keys()):
            cog = self.get_cog(cog_name)
            if cog:
                logger.info(f"Unloading cog: {cog_name}...")
                try:
                    # Let cog clean up/unload
                    if hasattr(cog, "cog_unload"):
                        if asyncio.iscoroutinefunction(cog.cog_unload):
                            await cog.cog_unload()
                        else:
                            cog.cog_unload()
                except Exception as e:
                    logger.error(f"Error unloading cog {cog_name}: {e}")

        # Flush metrics to disk
        logger.info("Flushing metrics to disk...")
        self.metrics.cancel_loop()
        await self.metrics.export_to_json()

        # Close database connection pool
        logger.info("Closing database connection pool...")
        await self.db.disconnect()

        # Close Discord connection
        logger.info("Closing discord gateway client...")
        await self.close()

        logger.info("Shutdown confirmation: Clean exit completed.")

    async def write_crash_dump(self, error: Exception) -> None:
        """Creates a logs/crash_dump.json file for post-mortem debugging."""
        logger.info("Writing crash dump details to logs/crash_dump.json...")
        try:
            # Gather last 100 log entries
            log_entries = []
            if os.path.exists("logs/bot.log"):
                with open("logs/bot.log", "r", encoding="utf-8") as f:
                    log_entries = f.readlines()[-100:]

            # Get system usage details
            process = psutil.Process(os.getpid())
            mem_state = {
                "rss_mb": process.memory_info().rss / (1024 * 1024),
                "cpu_percent": process.cpu_percent(interval=None)
            }

            # Gather DB verification queue depth
            queue_count = 0
            try:
                row = await self.db.fetchone("SELECT COUNT(*) as count FROM verification_queue")
                if row:
                    queue_count = row["count"]
            except Exception:
                pass

            dump_data = {
                "timestamp": discord.utils.utcnow().isoformat(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback": traceback.format_exc(),
                "active_queue_depth": queue_count,
                "memory_state": mem_state,
                "last_logs": log_entries
            }

            with open("logs/crash_dump.json", "w", encoding="utf-8") as f:
                json.dump(dump_data, f, indent=2)

            logger.info("Crash dump successfully written.")

            # Webhook alerting
            webhook_url = self.bot_config.discord_audit_webhook_url
            if webhook_url and webhook_url.startswith("http"):
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "embeds": [{
                            "title": "🚨 Bot Crash Alert",
                            "description": f"The bot encountered an unhandled exception: `{error}`. A crash dump has been created.",
                            "color": 15539236,
                            "timestamp": discord.utils.utcnow().isoformat()
                        }]
                    }
                    async with session.post(webhook_url, json=payload) as resp:
                        pass
        except Exception as e:
            logger.error(f"Failed to create crash dump file: {e}")


async def main() -> None:
    # 1. Load config
    try:
        cfg = config_schema.load_config()
    except Exception as e:
        logger.critical(f"Failed to validate config.json schema: {e}")
        sys.exit(1)

    # 2. Token checks
    if not cfg.discord_token or cfg.discord_token == "MTAxMjM0NTY3ODkwMTIzNDU2Nw.G12345.dummy_token_for_validation_testing" or len(cfg.discord_token) < 20:
        logger.critical("Invalid or empty DISCORD_TOKEN provided. Exiting.")
        sys.exit(1)

    # 3. DB Connect
    db_mgr = DatabaseManager(cfg.database.path)
    try:
        await db_mgr.connect()
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        sys.exit(1)

    # Run database initial table setups
    models = DatabaseModels(db_mgr)
    await models.create_tables()

    # 4. Metrics Setup
    tracker = MetricsTracker()
    tracker.start_loop(asyncio.get_running_loop())

    # 5. Instantiate Bot
    bot = AntigravityBot(cfg, db_mgr, tracker)

    # Bind Signals
    loop = asyncio.get_running_loop()
    def handle_signal():
        logger.warning("System termination signal captured!")
        asyncio.create_task(bot.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass # Windows event loop compatibility

    # 6. Start Bot
    try:
        await bot.start(cfg.discord_token)
    except discord.LoginFailure:
        logger.critical("Login failure: The provided DISCORD_TOKEN is invalid.")
        await bot.shutdown()
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Bot encountered unhandled execution error: {e}")
        await bot.write_crash_dump(e)
        await bot.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution terminated by KeyboardInterrupt.")
