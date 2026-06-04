import pytest
import time
from unittest.mock import MagicMock, AsyncMock
from cogs.moderation.cog import ModerationCog

@pytest.mark.asyncio
async def test_rbac_restriction():
    bot = MagicMock()
    bot.bot_config = MagicMock()
    bot.bot_config.admin_user_ids = [123]  # Owner
    bot.metrics = AsyncMock()
    
    cog = ModerationCog(bot)
    
    # 1. Non-admin, non-owner interaction
    user_interaction = MagicMock()
    user_interaction.user.id = 456
    user_interaction.user.guild_permissions.administrator = False
    user_interaction.guild.id = 999
    user_interaction.response.send_message = AsyncMock()
    
    allowed = await cog._check_permissions_and_cooldown(user_interaction)
    assert allowed is False
    user_interaction.response.send_message.assert_called_with("❌ Access Denied: Administrator clearance is required.", ephemeral=True)

    # 2. Owner interaction
    owner_interaction = MagicMock()
    owner_interaction.user.id = 123
    owner_interaction.user.guild_permissions.administrator = False
    owner_interaction.guild.id = 999
    owner_interaction.response.send_message = AsyncMock()
    
    allowed = await cog._check_permissions_and_cooldown(owner_interaction)
    assert allowed is True

@pytest.mark.asyncio
async def test_audit_logging(tmp_path):
    import database
    from database.models import DatabaseModels
    
    db_file = tmp_path / "test_audit.db"
    db = database.DatabaseManager(str(db_file), max_connections=1)
    await db.connect()
    
    models = DatabaseModels(db)
    await models.create_tables()
    
    bot = MagicMock()
    bot.db = db
    bot.models = models
    bot.metrics = AsyncMock()
    bot.bot_config = MagicMock()
    bot.bot_config.admin_user_ids = [123]
    
    cog = ModerationCog(bot)
    
    interaction = MagicMock()
    interaction.user.id = 123
    interaction.user.display_name = "AdminUser"
    interaction.guild.id = 999
    
    # Perform an audit log entry
    await cog._audit(interaction, "TEST_ACTION", "target_user", "Reason text")
    
    # Fetch logs
    logs = await models.get_audit_logs("target_user")
    assert len(logs) == 1
    assert logs[0]["action"] == "TEST_ACTION"
    assert logs[0]["reason"] == "Reason text"
    
    await db.disconnect()
