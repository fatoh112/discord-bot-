import asyncio
import os
import discord
from unittest.mock import AsyncMock, MagicMock
from cogs.music.cog import MusicCog

async def main():
    bot = MagicMock()
    bot.loop = asyncio.get_event_loop()
    
    cog = MusicCog(bot)
    
    interaction = AsyncMock()
    interaction.guild.id = 123
    interaction.guild.voice_client = None
    interaction.user.voice.channel.connect = AsyncMock()
    
    print("Testing play...")
    
    with patch('cogs.music.cog.YTDLSource.from_url', new_callable=AsyncMock) as mock_from_url:
        mock_from_url.return_value = [{'title': 'Test Song', 'url': 'http://test'}]
        await cog.play.callback(cog, interaction, "ytsearch:Self Aware Temper City")
        
    print("Play finished!")
    
    # Wait for playback loop to do something
    await asyncio.sleep(5)
    
    player = cog.get_player(interaction.guild)
    print("Queue size:", len(player.queue.tracks))
    print("Current track:", player.current_track)
    print("Replies:", str(interaction.followup.send.call_args_list).encode('utf-8'))

if __name__ == "__main__":
    from unittest.mock import patch
    asyncio.run(main())
