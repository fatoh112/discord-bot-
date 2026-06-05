import discord
from discord.ext import commands
from discord import app_commands
from loguru import logger
from utils.music_player import AudioPlayer
from utils.music_source import YTDLSource
import json

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
            
        self.ffmpeg_path = self.config.get("ffmpeg_path", "ffmpeg")

    def get_player(self, guild: discord.Guild):
        """Retrieve the guild player, or create one."""
        if guild.id not in self.players:
            # We can fetch specific guild config from DB here if needed
            self.players[guild.id] = AudioPlayer(self.bot, guild, self.config, self.ffmpeg_path)
        return self.players[guild.id]

    async def _check_dj(self, interaction: discord.Interaction) -> bool:
        """Check if user has DJ role or is Admin."""
        if interaction.user.guild_permissions.administrator:
            return True
            
        config = await self.bot.db_models.get_music_config(str(interaction.guild_id))
        if config and config.get('dj_role_id'):
            dj_role_id = int(config['dj_role_id'])
            if any(r.id == dj_role_id for r in interaction.user.roles):
                return True
        return False

    @app_commands.command(name="play", description="Join voice channel and play song/playlist")
    @app_commands.describe(query="YouTube URL, search term, or playlist link")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You need to be in a voice channel first", ephemeral=True)
            
        await interaction.response.defer(thinking=True)
        
        channel = interaction.user.voice.channel
        
        logger.info(f"=== PLAY COMMAND START ===")
        logger.info(f"Guild: {interaction.guild.id} | User: {interaction.user} | Voice: {channel}")
        
        if interaction.guild.voice_client is None:
            try:
                logger.info(f"Attempting to connect to {channel.name} ({channel.id})")
                await channel.connect()
                logger.info(f"Successfully connected to {channel.name}")
            except Exception as e:
                logger.error(f"Failed to connect: {type(e).__name__}: {e}")
                return await interaction.followup.send("❌ I couldn't join your voice channel. Check permissions.")
        elif interaction.guild.voice_client.channel != channel:
            return await interaction.followup.send("❌ I am already in another voice channel.", ephemeral=True)

        player = self.get_player(interaction.guild)
        player.text_channel = interaction.channel
        
        try:
            entries = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, ffmpeg_path=self.ffmpeg_path)
        except Exception as e:
            return await interaction.followup.send(f"❌ I couldn't find any results for that query.")
            
        if not entries:
            return await interaction.followup.send(f"❌ I couldn't find any results for that query.")

        added_count = 0
        for track_data in entries:
            if player.queue.add_track(track_data):
                added_count += 1
            else:
                if added_count > 0:
                    break
                else:
                    return await interaction.followup.send("❌ Queue is full (max 100 tracks)")
        
        if added_count > 1:
            await interaction.followup.send(f"✅ Added {added_count} tracks to the queue.")
        else:
            await interaction.followup.send(f"✅ Added **{entries[0].get('title')}** to the queue.")
            
        if not player.current_track:
            # Kickstart the playback if it's not playing
            self.bot.loop.call_soon_threadsafe(player._play_event.set)

    @app_commands.command(name="pause", description="Pause current playback")
    async def pause(self, interaction: discord.Interaction):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Paused playback.")
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume paused playback")
    async def resume(self, interaction: discord.Interaction):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Resumed playback.")
        else:
            await interaction.response.send_message("❌ Nothing is paused.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to skip.", ephemeral=True)
            
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped.")
        else:
            await interaction.response.send_message("❌ Nothing is playing. Use /play to start!", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear queue")
    async def stop(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to stop.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.clear()
        
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            
        await interaction.response.send_message("⏹️ Stopped playback and cleared the queue.")

    @app_commands.command(name="queue", description="Show current queue")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.queue.is_empty() and not player.current_track:
            return await interaction.response.send_message("❌ Nothing is playing. Use /play to start!")
            
        embed = discord.Embed(title="Current Queue", color=discord.Color.blurple())
        
        if player.current_track:
            embed.add_field(name="Now Playing", value=player.current_track.get('title', 'Unknown'), inline=False)
            
        tracks = player.queue.get_queue()
        if tracks:
            q_list = ""
            for i, track in enumerate(tracks[:10]):
                q_list += f"{i+1}. {track.get('title', 'Unknown')}\n"
            if len(tracks) > 10:
                q_list += f"... and {len(tracks) - 10} more"
            embed.add_field(name="Up Next", value=q_list, inline=False)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show currently playing track")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.current_track:
            return await interaction.response.send_message("❌ Nothing is playing. Use /play to start!", ephemeral=True)
            
        embed = discord.Embed(title="Now Playing", description=player.current_track.get('title', 'Unknown'), color=discord.Color.blurple())
        if player.current_track.get('thumbnail'):
            embed.set_thumbnail(url=player.current_track.get('thumbnail'))
        if player.current_track.get('duration'):
            mins, secs = divmod(player.current_track.get('duration'), 60)
            embed.add_field(name="Duration", value=f"{mins}:{secs:02d}")
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set playback volume (0-200%)")
    @app_commands.describe(volume="Volume level from 0 to 200")
    async def volume(self, interaction: discord.Interaction, volume: int):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to change volume.", ephemeral=True)
            
        if not 0 <= volume <= 200:
            return await interaction.response.send_message("❌ Volume must be between 0 and 200.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.set_volume(volume / 100.0)
        await interaction.response.send_message(f"🔊 Volume set to {volume}%")

    @app_commands.command(name="leave", description="Disconnect from voice channel")
    async def leave(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to disconnect.", ephemeral=True)
            
        if interaction.guild.voice_client:
            player = self.get_player(interaction.guild)
            player.destroy()
            del self.players[interaction.guild.id]
            await interaction.response.send_message("👋 Disconnected.")
        else:
            await interaction.response.send_message("❌ Not in a voice channel.", ephemeral=True)

    @app_commands.command(name="loop", description="Toggle loop mode")
    @app_commands.describe(mode="Mode: 0=off, 1=track, 2=queue")
    async def loop(self, interaction: discord.Interaction, mode: int):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to loop.", ephemeral=True)
            
        if mode not in [0, 1, 2]:
            return await interaction.response.send_message("❌ Mode must be 0 (off), 1 (track), or 2 (queue).", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.loop_mode = mode
        modes = ["Off", "Track", "Queue"]
        await interaction.response.send_message(f"🔁 Loop mode set to: {modes[mode]}")

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to shuffle.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.shuffle()
        await interaction.response.send_message("🔀 Queue shuffled.")

    @app_commands.command(name="remove", description="Remove a track from the queue")
    @app_commands.describe(position="Position of the track to remove (1-based)")
    async def remove(self, interaction: discord.Interaction, position: int):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to remove tracks.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        track = player.queue.remove(position - 1)
        if track:
            await interaction.response.send_message(f"🗑️ Removed **{track.get('title')}** from the queue.")
        else:
            await interaction.response.send_message("❌ Invalid position.", ephemeral=True)

    @app_commands.command(name="clearqueue", description="Clear all tracks from the queue")
    async def clearqueue(self, interaction: discord.Interaction):
        if not await self._check_dj(interaction):
            return await interaction.response.send_message("❌ You need DJ permissions to clear the queue.", ephemeral=True)
            
        player = self.get_player(interaction.guild)
        player.queue.clear()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @app_commands.command(name="seek", description="Seek to a specific timestamp (Not fully supported by FFmpegPCMAudio natively)")
    @app_commands.describe(timestamp="Timestamp in seconds")
    async def seek(self, interaction: discord.Interaction, timestamp: int):
        await interaction.response.send_message("❌ Seek is not currently supported in this version.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.id == self.bot.user.id:
            return
            
        # If bot was disconnected manually
        if before.channel and not after.channel:
            if member.guild.id in self.players:
                self.players[member.guild.id].destroy()
                del self.players[member.guild.id]

async def setup(bot):
    # Registration is done here, wait, user said "Remove ALL Manual Command Registration"
    # But this is a regular extension, we just add the cog.
    await bot.add_cog(MusicCog(bot))
