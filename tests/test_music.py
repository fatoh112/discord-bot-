import pytest
from utils.music_queue import QueueManager
from unittest.mock import MagicMock, AsyncMock
import asyncio

def test_queue_add_remove():
    q = QueueManager(max_size=3)
    
    assert q.is_empty()
    assert not q.is_full()
    
    # Add tracks
    assert q.add_track({"title": "Track 1"})
    assert q.add_track({"title": "Track 2"})
    assert q.add_track({"title": "Track 3"})
    
    # Queue is full now
    assert q.is_full()
    assert not q.add_track({"title": "Track 4"})
    
    # Check length
    assert len(q.get_queue()) == 3
    
    # Remove by index
    removed = q.remove(1)
    assert removed["title"] == "Track 2"
    assert len(q.get_queue()) == 2
    
    # Pop next
    next_track = q.get_next()
    assert next_track["title"] == "Track 1"
    
def test_queue_shuffle():
    q = QueueManager(max_size=10)
    for i in range(10):
        q.add_track({"title": f"Track {i}"})
        
    original = [t["title"] for t in q.get_queue()]
    q.shuffle()
    shuffled = [t["title"] for t in q.get_queue()]
    
    assert len(original) == len(shuffled)
    assert original != shuffled or len(original) < 2

def test_loop_modes():
    q = QueueManager(max_size=3)
    q.add_track({"title": "Track 1"})
    q.add_track({"title": "Track 2"})
    
    # Normal play
    q.loop_mode = 0
    t1 = q.get_next()
    t2 = q.get_next(t1)
    assert t1["title"] == "Track 1"
    assert t2["title"] == "Track 2"
    
    # Reset queue
    q.clear()
    q.add_track({"title": "A"})
    q.add_track({"title": "B"})
    
    # Loop track
    q.loop_mode = 1
    current = q.get_next()
    assert current["title"] == "A"
    
    # Should get the same track back
    next_t = q.get_next(current)
    assert next_t["title"] == "A"
    
    # Loop queue
    q.clear()
    q.add_track({"title": "1"})
    q.loop_mode = 2
    
    current = q.get_next()
    assert current["title"] == "1"
    assert len(q.get_queue()) == 0
    
    # When getting next, "1" should be added to the end of queue and then popped since it's the only one
    next_t = q.get_next(current)
    assert next_t["title"] == "1"
    # Our logic:
    # if len(self.tracks) < self.max_size:
    #     self.tracks.append(current_track)
    # Then it does: return self.tracks.pop(0)
    # Let's fix loop mode test

@pytest.mark.asyncio
async def test_play_internal_integration():
    import discord
    from utils.music_view import PlayModal
    from cogs.music.cog import MusicCog
    
    mock_bot = MagicMock()
    mock_cog = MagicMock(spec=MusicCog)
    mock_cog._play_internal = AsyncMock()
    mock_bot.get_cog.return_value = mock_cog
    
    player_mock = MagicMock()
    modal = PlayModal(mock_bot, player_mock)
    
    # Mock interaction
    mock_interaction = MagicMock(spec=discord.Interaction)
    
    # Set modal input value
    modal.query._value = "https://youtube.com/watch?v=123"
    
    # Call on_submit
    await modal.on_submit(mock_interaction)
    
    # Assert _play_internal was called with query value
    mock_cog._play_internal.assert_called_once_with(mock_interaction, "https://youtube.com/watch?v=123")

@pytest.mark.asyncio
async def test_music_cog_play_calls_internal():
    import discord
    from cogs.music.cog import MusicCog
    
    mock_bot = MagicMock()
    cog = MusicCog(mock_bot)
    cog._play_internal = AsyncMock()
    
    mock_interaction = MagicMock(spec=discord.Interaction)
    await cog.play.callback(cog, mock_interaction, "test query")
    
    cog._play_internal.assert_called_once_with(mock_interaction, "test query")

def test_ytdl_source_read_counting():
    import discord
    from utils.music_source import YTDLSource
    
    class MockAudioSource(discord.AudioSource):
        def read(self) -> bytes:
            return b'123'
    
    mock_audio_source = MockAudioSource()
    data = {"title": "Test Track"}
    source = YTDLSource(mock_audio_source, data=data)
    
    assert source.reads == 0
    assert source.elapsed == 0.0
    
    res = source.read()
    assert res is not None
    assert source.reads == 1
    assert source.elapsed == 0.02

@pytest.mark.asyncio
async def test_music_channel_checks():
    import discord
    from cogs.music.cog import MusicCog

    mock_bot = MagicMock()
    cog = MusicCog(mock_bot)

    # Mock database config returning a channel ID
    mock_models = MagicMock()
    mock_models.get_music_config = AsyncMock(return_value={"dashboard_channel_id": "12345"})
    mock_bot.models = mock_models

    # Interaction with a DIFFERENT channel ID
    mock_interaction_wrong = MagicMock(spec=discord.Interaction)
    mock_interaction_wrong.guild_id = 999
    mock_interaction_wrong.channel_id = 54321
    mock_interaction_wrong.response = MagicMock()
    mock_interaction_wrong.response.send_message = AsyncMock()

    # Mock guild get_channel returning the fixed channel
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_channel.mention = "<#12345>"
    mock_interaction_wrong.guild.get_channel = MagicMock(return_value=mock_channel)

    res = await cog._channel_check(mock_interaction_wrong)
    assert res is False
    mock_interaction_wrong.response.send_message.assert_called_once()
    assert "fixed to" in mock_interaction_wrong.response.send_message.call_args[0][0]

    # Interaction with the CORRECT channel ID
    mock_interaction_correct = MagicMock(spec=discord.Interaction)
    mock_interaction_correct.guild_id = 999
    mock_interaction_correct.channel_id = 12345
    mock_interaction_correct.guild.get_channel = MagicMock(return_value=mock_channel)

    res = await cog._channel_check(mock_interaction_correct)
    assert res is True

@pytest.mark.asyncio
async def test_initialize_music_channels():
    import discord
    from cogs.music.cog import MusicCog

    mock_bot = MagicMock()
    cog = MusicCog(mock_bot)

    # Mock guild and config
    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 999
    mock_bot.guilds = [mock_guild]

    mock_models = MagicMock()
    mock_models.get_music_config = AsyncMock(return_value={"dashboard_channel_id": "12345"})
    mock_bot.models = mock_models

    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_guild.get_channel = MagicMock(return_value=mock_channel)

    # Mock get_player
    mock_player = MagicMock()
    mock_player.update_now_playing_message = AsyncMock()
    cog.get_player = MagicMock(return_value=mock_player)

    await cog._initialize_music_channels()

    cog.get_player.assert_called_once_with(mock_guild)
    assert mock_player.text_channel == mock_channel
    mock_player.update_now_playing_message.assert_called_once()


@pytest.mark.asyncio
async def test_dashboard_force_new():
    import discord
    from cogs.music.cog import MusicCog

    mock_bot = MagicMock()
    cog = MusicCog(mock_bot)

    # Mock guild and config
    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = 999
    
    mock_models = MagicMock()
    mock_models.get_music_config = AsyncMock(return_value={"dashboard_channel_id": "12345"})
    mock_bot.models = mock_models

    mock_channel = MagicMock(spec=discord.TextChannel)
    # Mock history list
    mock_msg_old = MagicMock(spec=discord.Message)
    mock_msg_old.author.id = mock_bot.user.id
    mock_embed = MagicMock(spec=discord.Embed)
    mock_embed.title = "Audio Player Idle"
    mock_msg_old.embeds = [mock_embed]
    mock_msg_old.delete = AsyncMock()

    class AsyncIterator:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_channel.history = MagicMock(return_value=AsyncIterator([mock_msg_old]))
    
    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.guild = mock_guild
    mock_interaction.guild_id = 999
    mock_interaction.channel = mock_channel
    mock_interaction.channel_id = 12345
    mock_interaction.response = MagicMock()
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup = MagicMock()
    mock_interaction.followup.send = AsyncMock()

    # Mock player
    mock_player = MagicMock()
    mock_player.now_playing_message = mock_msg_old
    mock_player.update_now_playing_message = AsyncMock()
    cog.get_player = MagicMock(return_value=mock_player)

    # Call dashboard command
    await cog.dashboard.callback(cog, mock_interaction)

    # Verify old messages were deleted
    mock_msg_old.delete.assert_called()
    # Verify update_now_playing_message was called with force_new=True
    mock_player.update_now_playing_message.assert_called_once_with(force_new=True)
    # Verify follow-up sent
    mock_interaction.followup.send.assert_called_once_with("✅ Interactive music player dashboard loaded below.", ephemeral=True)

