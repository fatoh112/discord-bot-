import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
from cogs.autorole.cog import AutoRoleCog
from database.db_manager import DatabaseManager
from database.models import DatabaseModels
from metrics import MetricsTracker

@pytest.mark.asyncio
async def test_concurrent_joins(tmp_path):
    db = MagicMock()
    db.execute = AsyncMock(return_value=1)
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)
    
    models = MagicMock()
    models.add_autorole = AsyncMock()
    models.get_autoroles = AsyncMock(return_value=[{"role_id": "111", "priority": 1}])
    models.log_audit = AsyncMock()
    
    tracker = MetricsTracker()
    
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.db = db
    bot.models = models
    bot.metrics = tracker
    bot.loop = asyncio.get_running_loop()
    bot.bot_config = MagicMock()
    bot.bot_config.admin_user_ids = [123]
    bot.bot_config.autorole.delay_seconds = 0.0  # Zero delay for load testing
    bot.bot_config.autorole.exclude_bots = False
    
    cog = AutoRoleCog(bot)
    
    # Pre-populate some roles
    await models.add_autorole("987654321", "111", 1)
    
    # Mock bot.get_guild
    guild = MagicMock()
    role = MagicMock()
    role.id = 111
    role.name = "role_load"
    role.position = 1
    role.__ge__ = MagicMock(return_value=False)
    guild.get_role.return_value = role
    guild.me.guild_permissions.manage_roles = True
    guild.me.top_role.position = 10
    
    member = MagicMock()
    member.bot = False
    member.roles = []
    member.add_roles = AsyncMock()
    guild.get_member.return_value = member
    
    bot.get_guild.return_value = guild
    
    # Simulate 500 concurrent joins
    start_time = time.time()
    for i in range(500):
        await cog.join_queue.put(("987654321", str(1000 + i), 0))
        
    # Wait for the queue to drain (or poll qsize)
    timeout = 30.0
    while cog.join_queue.qsize() > 0 and (time.time() - start_time) < timeout:
        await asyncio.sleep(0.1)
        
    duration = time.time() - start_time
    print(f"Processed 500 concurrent joins in {duration:.2f} seconds.")
    
    assert cog.join_queue.qsize() == 0
    await cog.cog_unload()
