import sys
import asyncio
from unittest.mock import MagicMock
sys.modules['audioop'] = MagicMock()
import discord
from discord.ext import commands
from cogs.moderation.cog import ModerationCog

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
print("cog_load is:", ModerationCog.cog_load)
print("type:", type(ModerationCog.cog_load))
