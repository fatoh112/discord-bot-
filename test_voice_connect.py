import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {str(bot.user).encode('ascii', 'ignore').decode()}")
    for guild in bot.guilds:
        print(f"Guild: {guild.name} ({guild.id})")
        for vc in guild.voice_channels:
            print(f"  Voice channel: {vc.name} ({vc.id})")
            try:
                print(f"  Connecting to {vc.name}...")
                voice_client = await vc.connect(timeout=30, reconnect=False)
                print(f"  Connected! is_connected={voice_client.is_connected()}")
                await asyncio.sleep(5)
                print(f"  Still connected? {voice_client.is_connected()}")
                await voice_client.disconnect()
                print(f"  Disconnected cleanly.")
            except Exception as e:
                print(f"  CONNECT FAILED: {type(e).__name__}: {e}")
            break
    await bot.close()

bot.run(os.getenv("DISCORD_TOKEN"))
