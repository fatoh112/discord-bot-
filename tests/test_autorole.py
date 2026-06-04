import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from cogs.autorole.cog import AutoRoleCog
from database.db_manager import DatabaseManager
from database.models import DatabaseModels
from metrics import MetricsTracker

@pytest.mark.asyncio
async def test_priority_queue():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.loop = asyncio.get_running_loop()
    bot.bot_config = MagicMock()
    bot.bot_config.admin_user_ids = [123]
    bot.bot_config.autorole = MagicMock()
    bot.bot_config.autorole.roles = []
    
    cog = AutoRoleCog(bot)
    
    # Enqueue items
    await cog.join_queue.put(("guild_1", "user_1", 0))
    await cog.join_queue.put(("guild_1", "user_2", 0))
    
    assert cog.join_queue.qsize() == 2
    item1 = await cog.join_queue.get()
    item2 = await cog.join_queue.get()
    
    assert item1 == ("guild_1", "user_1", 0)
    assert item2 == ("guild_1", "user_2", 0)
    
    await cog.cog_unload()

@pytest.mark.asyncio
async def test_lock_mechanism():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.loop = asyncio.get_running_loop()
    bot.bot_config = MagicMock()
    cog = AutoRoleCog(bot)
    
    lock1 = await cog._get_guild_lock("guild_1")
    lock2 = await cog._get_guild_lock("guild_1")
    lock3 = await cog._get_guild_lock("guild_2")
    
    assert lock1 is lock2
    assert lock1 is not lock3
    
    await cog.cog_unload()

@pytest.mark.asyncio
async def test_retry_logic(tmp_path):
    # Simulate DB state saving and restoring
    db_file = tmp_path / "test_retry.db"
    db = DatabaseManager(str(db_file), max_connections=1)
    await db.connect()
    
    models = DatabaseModels(db)
    await models.create_tables()
    
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.db = db
    bot.models = models
    bot.metrics = MetricsTracker()
    bot.loop = asyncio.get_running_loop()
    bot.bot_config = MagicMock()
    bot.bot_config.admin_user_ids = [123]
    bot.bot_config.autorole.delay_seconds = 0
    bot.bot_config.autorole.exclude_bots = False
    
    cog = AutoRoleCog(bot)
    
    # Put a failed job
    await db.execute(
        "INSERT INTO verification_queue (user_id, guild_id, joined_at, verified, method, status) VALUES (?, ?, datetime('now'), 0, 'auto', 'pending')",
        ("user_retry", "guild_retry")
    )
    
    # Restore queue
    await cog._restore_queue_from_db()
    assert cog.join_queue.qsize() == 1
    
    await cog.cog_unload()
    await db.disconnect()
