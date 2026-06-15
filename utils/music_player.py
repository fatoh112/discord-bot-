# music_player.py - Player state coordination and background embed updater loops
import asyncio
import discord
import time
from loguru import logger
from utils.music_queue import QueueManager
from utils.music_source import YTDLSource

class AudioPlayer:
    def __init__(self, bot, guild: discord.Guild, config: dict, ffmpeg_path: str):
        self.bot = bot
        self.guild = guild
        self.config = config
        self.ffmpeg_path = ffmpeg_path
        
        max_q = config.get("max_queue_size", 100)
        self.queue = QueueManager(max_size=max_q)
        
        self.current_track = None
        self.current_source: discord.AudioSource = None
        
        self._play_event = asyncio.Event()
        self.playback_task = bot.loop.create_task(self.playback_loop())
        
        self.volume = 1.0
        self.auto_disconnect_minutes = config.get("auto_disconnect_minutes", 5)
        self.text_channel = None
        
        # UI & Time progress attributes
        self.play_start_time = None
        self.accumulated_elapsed = 0
        self.paused_at = None
        self.now_playing_message = None
        self.update_task = None
        self.is_skipping_backward = False

    def destroy(self):
        logger.info(f"Destroying AudioPlayer for guild {self.guild.id}")
        self.playback_task.cancel()
        if self.update_task:
            self.update_task.cancel()
        
        # Clean up embed message
        if self.now_playing_message and self.text_channel:
            async def delete_msg():
                try:
                    await self.now_playing_message.delete()
                except Exception:
                    pass
            self.bot.loop.create_task(delete_msg())

        if self.guild.voice_client:
            self.bot.loop.create_task(self.guild.voice_client.disconnect())

    def get_elapsed_time(self) -> int:
        """Calculate active playback seconds, accounting for pause periods."""
        if self.current_source and hasattr(self.current_source, 'elapsed'):
            return int(self.current_source.elapsed)
        if self.paused_at:
            return int(self.accumulated_elapsed + (self.paused_at - self.play_start_time))
        elif self.play_start_time:
            now = self.bot.loop.time()
            return int(self.accumulated_elapsed + (now - self.play_start_time))
        return 0

    def skip_backward(self) -> bool:
        """Skip to the previous track in history if available."""
        if not self.queue.history:
            return False
        prev_track = self.queue.history.pop()
        if self.current_track:
            # Insert current track back to the beginning of the queue
            self.queue.tracks.insert(0, self.current_track)
        
        self.current_track = prev_track
        self.is_skipping_backward = True
        
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop() # triggers toggle_next in playback_loop
        else:
            # If not active, kickstart play
            self.bot.loop.call_soon_threadsafe(self._play_event.set)
        return True

    async def update_embed_loop(self):
        """Periodically update the timeline progress bar on the active Embed."""
        try:
            while self.guild.voice_client and (self.guild.voice_client.is_playing() or self.guild.voice_client.is_paused()):
                await asyncio.sleep(4)  # Update progress bar every 4 seconds for smoother slider
                await self.update_now_playing_message()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in update_embed_loop: {e}")

    async def update_now_playing_message(self, force_new: bool = False):
        """Constructs and updates the Now Playing embed message."""
        # Resolve fixed dashboard channel if configured
        config = await self.bot.models.get_music_config(str(self.guild.id))
        if config and config.get("dashboard_channel_id"):
            channel_id = int(config["dashboard_channel_id"])
            fixed_channel = self.guild.get_channel(channel_id)
            if fixed_channel:
                self.text_channel = fixed_channel

        if not self.text_channel:
            return

        if force_new:
            if self.now_playing_message:
                try:
                    await self.now_playing_message.delete()
                except Exception:
                    pass
                self.now_playing_message = None
        else:
            # Try to find and adopt the last existing dashboard message in the channel history
            if not self.now_playing_message:
                try:
                    async for msg in self.text_channel.history(limit=30):
                        if msg.author.id == self.bot.user.id and msg.embeds:
                            emb = msg.embeds[0]
                            if emb.title and ("Playing" in emb.title or "Player" in emb.title or "Idle" in emb.title):
                                self.now_playing_message = msg
                                break
                except Exception as e:
                    logger.error(f"Failed to scan text channel history for dashboard: {e}")

        # Display the Queue automatically inside the same window
        upcoming = self.queue.get_queue()
        if upcoming:
            queue_lines = []
            for i, track in enumerate(upcoming[:5], start=1):
                dur_str = ""
                if track.get('duration'):
                    m, s = divmod(track.get('duration'), 60)
                    dur_str = f" `[{m}:{s:02d}]`"
                queue_lines.append(f"`{i}.` **{track.get('title')}**{dur_str}")
            
            if len(upcoming) > 5:
                queue_lines.append(f"*... and {len(upcoming) - 5} more in queue*")
            
            queue_text = "\n".join(queue_lines)
        else:
            queue_text = "*Queue is empty*"

        if not self.current_track:
            # Player is idle or stopped
            embed = discord.Embed(
                title="🎧 Audio Player Idle",
                description="The player is currently idle.\n\nUse `/play` or click **🔗 Play URL** below to start playing music!",
                color=discord.Color.from_str("#2f3136")
            )
            progress_bar = "▬" * 15
            embed.add_field(name="Timeline Position", value=f"{progress_bar} `[0:00 / 0:00]`", inline=False)
            embed.add_field(name="📋 Upcoming Queue", value=queue_text, inline=False)
            
            # Import view lazily to avoid circular imports
            from utils.music_view import MusicControlView
            view = MusicControlView(self.bot, self)
            
            if self.now_playing_message:
                try:
                    await self.now_playing_message.edit(embed=embed, view=view)
                    return
                except discord.NotFound:
                    self.now_playing_message = None
                except Exception as e:
                    logger.error(f"Failed to edit now_playing_message: {e}")
                    self.now_playing_message = None

            if not self.now_playing_message:
                try:
                    msg = await self.text_channel.send(embed=embed, view=view)
                    self.now_playing_message = msg
                except Exception as e:
                    logger.error(f"Failed to send now_playing_message: {e}")
            return

        # Build Unicode Progress Bar
        elapsed = self.get_elapsed_time()
        duration = self.current_track.get('duration', 0)
        
        def format_time(secs):
            m, s = divmod(int(secs), 60)
            return f"{m}:{s:02d}"

        bar_len = 15
        if duration > 0:
            pct = min(1.0, elapsed / duration)
            position = int(pct * bar_len)
        else:
            pct = 0
            position = 0
            
        bar = ["▬"] * bar_len
        if 0 <= position < bar_len:
            bar[position] = "🔘"
        progress_bar = "".join(bar)
        time_display = f"`[{format_time(elapsed)} / {format_time(duration)}]`"
        progress_line = f"{progress_bar} {time_display}"

        # Build Embed Card
        embed = discord.Embed(
            title="⚡ Now Playing",
            description=f"### **[{self.current_track.get('title')}]({self.current_track.get('webpage_url')})**",
            color=discord.Color.from_str("#00f0ff") # Neon Cyan
        )
        
        # Thumbnail
        if self.current_track.get('thumbnail'):
            embed.set_thumbnail(url=self.current_track.get('thumbnail'))

        # Track fields
        uploader = self.current_track.get('uploader') or self.current_track.get('artist') or 'Unknown'
        requester = self.current_track.get('requester_mention') or self.current_track.get('requester_name') or 'Unknown'
        loop_modes = ["Off", "Track", "Queue"]
        loop_status = loop_modes[self.queue.loop_mode]
        vc = self.guild.voice_client
        vc_name = vc.channel.name if vc and vc.channel else 'None'

        metadata_value = (
            f"👤 **Artist:** `{uploader}`\n"
            f"📥 **Requested by:** {requester}\n"
            f"🔊 **Volume:** `{int(self.volume * 100)}%` │ 🔁 **Loop:** `{loop_status}` │ 📡 **Voice:** `{vc_name}`"
        )
        embed.add_field(name="Track Details", value=metadata_value, inline=False)
        embed.add_field(name="Progress", value=progress_line, inline=False)
        embed.add_field(name="📋 Upcoming Queue", value=queue_text, inline=False)

        # Import view lazily to avoid circular imports
        from utils.music_view import MusicControlView
        view = MusicControlView(self.bot, self)

        # Send or Edit message
        if self.now_playing_message:
            try:
                await self.now_playing_message.edit(embed=embed, view=view)
                return
            except discord.NotFound:
                # Message was deleted, send a new one
                self.now_playing_message = None
            except Exception as e:
                logger.error(f"Failed to edit now_playing_message: {e}")
                self.now_playing_message = None

        if not self.now_playing_message:
            try:
                msg = await self.text_channel.send(embed=embed, view=view)
                self.now_playing_message = msg
            except Exception as e:
                logger.error(f"Failed to send now_playing_message: {e}")

    async def playback_loop(self):
        logger.info(f"Playback loop started for guild {self.guild.id}")
        try:
            while True:
                self._play_event.clear()
                
                # Wait for the next track in the queue, or timeout and disconnect
                try:
                    idle_time = 0
                    while self.queue.is_empty() and not self.current_track:
                        await asyncio.sleep(1)
                        idle_time += 1
                        if idle_time > self.auto_disconnect_minutes * 60:
                            logger.info(f"Idle timeout reached for guild {self.guild.id}, disconnecting.")
                            if self.guild.voice_client:
                                self.bot.loop.create_task(self.guild.voice_client.disconnect())
                            return
                except asyncio.CancelledError:
                    return
                
                if not self.current_track:
                    track_data = self.queue.get_next()
                    if not track_data:
                        continue
                    self.current_track = track_data
                else:
                    # In loop mode, current_track might be preserved.
                    track_data = self.current_track

                try:
                    logger.info(f"Playback loop: creating source for {track_data.get('title')}")
                    self.current_source = await YTDLSource.create_source(track_data, self.ffmpeg_path, volume=self.volume, loop=self.bot.loop)
                    logger.info(f"Playback loop: successfully created source")
                except Exception as e:
                    logger.error(f"Failed to create source for {track_data.get('title')}: {e}")
                    if self.text_channel:
                        self.bot.loop.create_task(
                            self.text_channel.send(f"❌ Failed to play **{track_data.get('title')}**: {e}")
                        )
                    self.current_track = None
                    continue

                def after_playing(error):
                    if error:
                        logger.error(f"Player error: {error}")
                    self.bot.loop.call_soon_threadsafe(self.toggle_next)
                    
                vc = self.guild.voice_client
                if vc and not vc.is_connected():
                    logger.info(f"Playback loop: voice client exists but not connected yet. Waiting...")
                    for _ in range(5):
                        await asyncio.sleep(1)
                        if vc.is_connected():
                            break

                if vc and vc.is_connected():
                    try:
                        # Reset progress variables before play start
                        self.play_start_time = self.bot.loop.time()
                        self.accumulated_elapsed = 0
                        self.paused_at = None
                        
                        # Stop existing progress bars update loop
                        if self.update_task:
                            self.update_task.cancel()

                        # Clear the play event so we block on wait()
                        self._play_event.clear()
                        
                        # Play audio
                        vc.play(self.current_source, after=after_playing)
                        logger.info(f"Playback loop: playing {self.current_track.get('title')}")
                        
                        # Trigger embed posts and start periodic ticks
                        self.bot.loop.create_task(self.update_now_playing_message())
                        self.update_task = self.bot.loop.create_task(self.update_embed_loop())
                    except discord.errors.ClientException as e:
                        logger.warning(f"Voice not ready, retrying in 2s: {e}")
                        await asyncio.sleep(2)
                        self._play_event.set()
                        continue
                else:
                    logger.error(f"Error in playback loop for guild {self.guild.id}: Not connected to voice.")
                    return

                await self._play_event.wait()
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in playback loop for guild {self.guild.id}: {e}")

    def toggle_next(self, error=None):
        if error:
            logger.error(f"Player error: {error}")
            
        if self.update_task:
            self.update_task.cancel()
            
        if self.is_skipping_backward:
            self.is_skipping_backward = False
            # self.current_track was already set in skip_backward!
        else:
            # Get next track based on loop mode
            next_track = self.queue.get_next(self.current_track)
            self.current_track = next_track
            
        if not self.current_track:
            # Display player idle Embed
            self.bot.loop.create_task(self.update_now_playing_message())

        self.bot.loop.call_soon_threadsafe(self._play_event.set)

    def set_volume(self, volume: float):
        self.volume = volume
        if self.current_source and isinstance(self.current_source, discord.PCMVolumeTransformer):
            self.current_source.volume = self.volume
