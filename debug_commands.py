"""
Debug script to check registered slash commands
"""

import asyncio
import discord
from dotenv import load_dotenv
import os

load_dotenv()

async def check_commands():
    intents = discord.Intents.all()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        print(f"User ID: {client.user.id}")
        
        # Check registered commands
        commands = await client.tree.fetch_commands()
        print(f"\n📋 Registered Commands ({len(commands)}):")
        for cmd in commands:
            print(f"  - /{cmd.name}: {cmd.description}")
        
        if not commands:
            print("\n❌ NO COMMANDS REGISTERED!")
            print("Possible causes:")
            print("  1. bot.tree.sync() not called")
            print("  2. Commands defined with wrong decorator")
            print("  3. Cogs not loaded before sync")
        
        await client.close()
    
    await client.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(check_commands())
