import discord
from discord.ext import commands
from discord import app_commands
from loguru import logger
from utils.music_player import AudioPlayer
from utils.music_source import YTDLSource
import json
import aiohttp
import re
from typing import Optional, Union


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        # Load config to get FFMPEG_PATH
        try:
            with open("config.json", "r") as f:
                self.config = json.load(f)
        except Exception as e:
            logger.error(f"Could not load config.json for MusicCog: {e}")
            self.config = {}
            
        try:
            import imageio_ffmpeg
            self.ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            self.ffmpeg_path = self.config.get("ffmpeg_path", "ffmpeg")

    async def _resolve_spotify_track(self, url: str) -> str:
        """Attempts to scrape the track name from a Spotify URL for searching on YouTube."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    html = await response.text()
                    title_match = re.search(r'<title>(.*?)</title>', html)
                    if title_match:
                        title = title_match.group(1)
                        title = title.replace(" - song and lyrics by ", " ")
                        title = title.replace(" - Single by ", " ")
                        title = title.replace(" - song by ", " ")
                        title = title.replace(" | Spotify", "")
                        return title
        except Exception as e:
            logger.error(f"Failed to resolve spotify link {url}: {e}")
        return None

    def get_player(self, guild: discord.Guild):
        """Retrieve the guild player, or create one."""
        if guild.id not in self.players:
            self.players[guild.id] = AudioPlayer(self.bot, guild, self.config, self.ffmpeg_path)
        return self.players[guild.id]

    async def _check_dj(self, interaction: discord.Interaction) -> bool:
        """Check if user has DJ role or is Admin."""
        if interaction.user.guild_permissions.administrator:
            return True
            
        config = await self.bot.models.get_music_config(str(interaction.guild_id))
        if config and config.get('dj_role_id'):
            dj_role_id = int(config['dj_role_id'])
            if any(r.id == dj_role_id for r in interaction.user.roles):
                return True
        return False

    async def _voice_check(self, interaction: discord.Interaction) -> bool:
        """Confirm the user is connected to the same voice channel as the bot (if active)."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You need to be in a voice channel first.", ephemeral=True)
            return False
            
        vc = interaction.guild.voice_client
        if vc and interaction.user.voice.channel != vc.channel:
            await interaction.response.send_message("❌ You must be in the same voice channel as the bot to run this command.", ephemeral=True)
            return False
            
        return True

    async def _channel_check(self, interaction: discord.Interaction) -> bool:
        """Checks if the command is being executed in the fixed channel if one is configured."""
        config = await self.bot.models.get_music_config(str(interaction.guild_id))
        if config and config.get("dashboard_channel_id"):
            fixed_channel_id = int(config["dashboard_channel_id"])
            fixed_channel = interaction.guild.get_channel(fixed_channel_id)
            if fixed_channel:
                if interaction.channel_id != fixed_channel_id:
                    await interaction.response.send_message(
                        f"❌ The music dashboard is fixed to {fixed_channel.mention}. Please run music commands there.",
                        ephemeral=True
                    )
                    return False
        return True

    async def _play_internal(self, interaction: discord.Interaction, query: str):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
            
        await interaction.response.defer(thinking=True)
        
        channel = interaction.user.voice.channel
        
        logger.info(f"=== PLAY COMMAND START ===")
        logger.info(f"Guild: {interaction.guild.id} | User: {interaction.user} | Voice: {channel}")
        
        if "spotify.com" in query:
            if "/track/" in query:
                track_name = await self._resolve_spotify_track(query)
                if track_name:
                    query = track_name
                else:
                    return await interaction.followup.send("❌ I couldn't fetch track metadata from that Spotify link. Please search for the song name instead.", ephemeral=True)
            else:
                return await interaction.followup.send("❌ I cannot play Spotify playlists or albums yet. Please provide a direct track link or search by name.", ephemeral=True)
            
        try:
            entries = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, ffmpeg_path=self.ffmpeg_path)
        except Exception as e:
            return await interaction.followup.send(f"❌ I couldn't find any results for that query.", ephemeral=True)
            
        if not entries:
            return await interaction.followup.send(f"❌ I couldn't find any results for that query.", ephemeral=True)

        # Connect to voice ONLY AFTER extraction is complete
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_connected():
            try:
                if vc:
                    await vc.disconnect(force=True)
                    import asyncio
                    await asyncio.sleep(1)
                logger.info(f"Attempting to connect to {channel.name} ({channel.id})")
                await channel.connect()
                logger.info(f"Successfully connected to {channel.name}")
            except Exception as e:
                logger.error(f"Failed to connect: {e}")
                return await interaction.followup.send("❌ I couldn't join your voice channel. Check permissions.", ephemeral=True)
        elif vc.channel != channel:
            return await interaction.followup.send("❌ I am already in another voice channel.", ephemeral=True)
                
        # Get player AFTER connection and extraction
        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel
        
        # Ensure playback loop is running
        if player.playback_task is None or player.playback_task.cancelled() or player.playback_task.done():
            player.playback_task = self.bot.loop.create_task(player.playback_loop())

        added_count = 0
        for track_data in entries:
            # Inject requester metadata
            track_data['requester_id'] = interaction.user.id
            track_data['requester_name'] = interaction.user.display_name
            track_data['requester_mention'] = interaction.user.mention
            
            if player.queue.add_track(track_data):
                added_count += 1
            else:
                if added_count > 0:
                    break
                else:
                    return await interaction.followup.send("❌ Queue is full (max 100 tracks)", ephemeral=True)
        
        if added_count > 1:
            await interaction.followup.send(f"✅ Added {added_count} tracks to the queue.", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Added **{entries[0].get('title')}** to the queue.", ephemeral=True)
            
        # Trigger dynamic embed update
        await player.update_now_playing_message()

        if not player.current_track:
            # Kickstart the playback if it's not playing
            self.bot.loop.call_soon_threadsafe(player._play_event.set)

    @app_commands.command(name="play", description="Join voice channel and play song/playlist")
    @app_commands.describe(query="YouTube URL, search term, or playlist link")
    async def play(self, interaction: discord.Interaction, query: str):
        await self._play_internal(interaction, query)

    @app_commands.command(name="pause", description="Pause current playback")
    async def pause(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
            
        player = self.get_player(interaction.guild)
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            player.paused_at = self.bot.loop.time()
            await player.update_now_playing_message()
            await interaction.response.send_message("⏸️ Paused playback.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume paused playback")
    async def resume(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
            
        player = self.get_player(interaction.guild)
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            if player.paused_at and player.play_start_time:
                now = self.bot.loop.time()
                player.play_start_time += (now - player.paused_at)
                player.paused_at = None
            await player.update_now_playing_message()
            await interaction.response.send_message("▶️ Resumed playback.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is paused.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to skip.", ephemeral=True)
            
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped current track.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is playing. Use /play to start!", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear queue")
    async def stop(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to stop.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.clear()
        
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            
        await player.update_now_playing_message()
        await interaction.response.send_message("⏹️ Stopped playback and cleared the queue.", ephemeral=True)

    @app_commands.command(name="queue", description="Show current queue")
    async def queue(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        player = self.get_player(interaction.guild)
        if player.queue.is_empty() and not player.current_track:
            return await interaction.response.send_message("❌ Nothing is playing. Use /play to start!", ephemeral=True)
            
        from utils.music_view import QueuePaginationView
        paginator = QueuePaginationView(player.queue.get_queue(), player.current_track, interaction.user)
        embed = paginator.make_embed()
        await interaction.response.send_message(embed=embed, view=paginator, ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show currently playing track")
    async def nowplaying(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        player = self.get_player(interaction.guild)
        if not player.current_track:
            return await interaction.response.send_message("❌ Nothing is playing. Use /play to start!", ephemeral=True)
            
        # Post (or re-send) active interactive player UI
        player.text_channel = interaction.channel
        await player.update_now_playing_message()
        await interaction.response.send_message("✅ Embed player UI refreshed.", ephemeral=True)

    @app_commands.command(name="volume", description="Set playback volume (0-200%)")
    @app_commands.describe(volume="Volume level from 0 to 200")
    async def volume(self, interaction: discord.Interaction, volume: int):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to change volume.", ephemeral=True)
            
        if not 0 <= volume <= 200:
            return await interaction.response.send_message("❌ Volume must be between 0 and 200.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.set_volume(volume / 100.0)
        await player.update_now_playing_message()
        await interaction.response.send_message(f"🔊 Volume set to {volume}%", ephemeral=True)

    @app_commands.command(name="leave", description="Disconnect from voice channel")
    async def leave(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to disconnect.", ephemeral=True)
            
        if interaction.guild.voice_client:
            player = self.get_player(interaction.guild)
            player.destroy()
            if interaction.guild.id in self.players:
                del self.players[interaction.guild.id]
            await interaction.response.send_message("👋 Disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Not in a voice channel.", ephemeral=True)

    @app_commands.command(name="loop", description="Toggle loop mode")
    @app_commands.describe(mode="Mode: 0=off, 1=track, 2=queue")
    async def loop(self, interaction: discord.Interaction, mode: int):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to loop.", ephemeral=True)
            
        if mode not in [0, 1, 2]:
            return await interaction.response.send_message("❌ Mode must be 0 (off), 1 (track), or 2 (queue).", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.loop_mode = mode
        await player.update_now_playing_message()
        modes = ["Off", "Track", "Queue"]
        await interaction.response.send_message(f"🔁 Loop mode set to: {modes[mode]}", ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to shuffle.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.shuffle()
        await player.update_now_playing_message()
        await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)

    @app_commands.command(name="remove", description="Remove a track from the queue")
    @app_commands.describe(position="Position of the track to remove (1-based)")
    async def remove(self, interaction: discord.Interaction, position: int):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to remove tracks.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        track = player.queue.remove(position - 1)
        if track:
            await player.update_now_playing_message()
            await interaction.response.send_message(f"🗑️ Removed **{track.get('title')}** from the queue.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid position.", ephemeral=True)

    @app_commands.command(name="clearqueue", description="Clear all tracks from the queue")
    async def clearqueue(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
        if not await self._voice_check(interaction):
            return
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to clear the queue.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.clear()
        await player.update_now_playing_message()
        await interaction.response.send_message("🗑️ Queue cleared.", ephemeral=True)

    @app_commands.command(name="seek", description="Seek to a specific timestamp (Not fully supported by FFmpegPCMAudio natively)")
    @app_commands.describe(timestamp="Timestamp in seconds")
    async def seek(self, interaction: discord.Interaction, timestamp: int):
        await interaction.response.send_message("❌ Seek is not currently supported in this version.", ephemeral=True)

    @app_commands.command(name="dashboard", description="Display the interactive in-Discord music player control panel")
    async def dashboard(self, interaction: discord.Interaction):
        if not await self._channel_check(interaction):
            return
            
        config = await self.bot.models.get_music_config(str(interaction.guild_id))
        fixed_channel_id = int(config["dashboard_channel_id"]) if config and config.get("dashboard_channel_id") else None
        
        # If not fixed to another channel, perform the voice check
        if not fixed_channel_id:
            if not await self._voice_check(interaction):
                return
            
        await interaction.response.defer(ephemeral=True)
        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel
        
        # If there's an existing player dashboard message reference, try to delete it first
        if player.now_playing_message:
            try:
                await player.now_playing_message.delete()
            except Exception:
                pass
            player.now_playing_message = None
            
        # Also scan the last 30 messages in history to find and delete any other bot dashboard messages
        try:
            async for msg in interaction.channel.history(limit=30):
                if msg.author.id == self.bot.user.id and msg.embeds:
                    emb = msg.embeds[0]
                    if emb.title and ("Playing" in emb.title or "Player" in emb.title or "Idle" in emb.title):
                        try:
                            await msg.delete()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Failed to scan and clean history in dashboard command: {e}")

        await player.update_now_playing_message(force_new=True)
        await interaction.followup.send("✅ Interactive music player dashboard loaded below.", ephemeral=True)

    @app_commands.command(name="setmusicchannel", description="Set or clear the fixed channel for the interactive music dashboard")
    @app_commands.describe(channel="Text channel to lock the dashboard to, or omit to clear the fixed channel")
    async def setmusicchannel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ You must be an administrator to run this command.", ephemeral=True)
            
        config = await self.bot.models.get_music_config(str(interaction.guild_id))
        dj_role_id = config.get("dj_role_id") if config else None
        max_queue = config.get("max_queue_size", 100) if config else 100
        auto_disconnect = config.get("auto_disconnect_minutes", 5) if config else 5
        
        channel_id = str(channel.id) if channel else None
        
        await self.bot.models.save_music_config(
            str(interaction.guild_id),
            dj_role_id=dj_role_id,
            max_queue_size=max_queue,
            auto_disconnect_minutes=auto_disconnect,
            dashboard_channel_id=channel_id
        )
        
        if channel:
            await interaction.response.send_message(f"✅ Music dashboard has been fixed to: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Fixed music dashboard channel has been cleared.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Only care about the bot itself
        if member.id != self.bot.user.id:
            return
            
        # Bot disconnected or was moved
        if before.channel and not after.channel:
            import asyncio
            await asyncio.sleep(3)  # wait to see if it's just reconnecting
            vc = member.guild.voice_client
            if vc is None or not vc.is_connected():
                logger.info(f"Bot was disconnected from channel {before.channel.id} in guild {member.guild.id}")
                
                # Cleanup player
                if member.guild.id in self.players:
                    logger.info(f"Destroying player for guild {member.guild.id}")
                    self.players[member.guild.id].destroy()
                    del self.players[member.guild.id]

    async def cog_load(self):
        if self.bot.is_ready():
            self.bot.loop.create_task(self._initialize_music_channels())

    @commands.Cog.listener()
    async def on_ready(self):
        await self._initialize_music_channels()

    async def _initialize_music_channels(self):
        logger.info("MusicCog: Initializing dashboard for configured music channels...")
        for guild in self.bot.guilds:
            try:
                config = await self.bot.models.get_music_config(str(guild.id))
                if config and config.get("dashboard_channel_id"):
                    fixed_channel_id = int(config["dashboard_channel_id"])
                    channel = guild.get_channel(fixed_channel_id)
                    if channel:
                        logger.info(f"MusicCog: Pre-initializing dashboard for guild {guild.id} in channel {fixed_channel_id}")
                        player = self.get_player(guild)
                        player.text_channel = channel
                        await player.update_now_playing_message()
            except Exception as e:
                logger.error(f"Error pre-initializing player for guild {guild.id}: {e}")

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
