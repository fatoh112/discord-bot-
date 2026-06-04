import asyncio
import discord
from discord.ext import commands
import config_schema

# We just want to load the cogs and see what's in the tree
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

async def main():
    bot.bot_config = config_schema.load_config()
    # Mock db and metrics
    class MockDb: pass
    class MockMetrics: pass
    class MockModels: pass
    bot.db = MockDb()
    bot.metrics = MockMetrics()
    bot.models = MockModels()

    await bot.load_extension("cogs.autorole.cog")
    await bot.load_extension("cogs.moderation.cog")
    await bot.load_extension("cogs.utility.cog")
    await bot.load_extension("cogs.health.cog")
    await bot.load_extension("cogs.compliance.cog")

    cmds = bot.tree.get_commands()
    print("Commands in tree:", [c.name for c in cmds])

asyncio.run(main())
