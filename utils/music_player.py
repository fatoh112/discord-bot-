import asyncio
import discord
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

    def destroy(self):
        self.playback_task.cancel()
        if self.guild.voice_client:
            self.bot.loop.create_task(self.guild.voice_client.disconnect())

    async def playback_loop(self):
        try:
            while True:
                self._play_event.clear()
                
                # Wait for the next track in the queue, or timeout and disconnect
                try:
                    # Polling the queue if it's empty
                    while self.queue.is_empty() and not self.current_track:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    return

                # Auto disconnect logic handles in cog via event, or we can handle it here if it times out
                # But since we just poll, we can add a timeout
                
                if not self.current_track:
                    track_data = self.queue.get_next()
                    if not track_data:
                        continue
                    self.current_track = track_data
                else:
                    # In loop mode, current_track might be preserved.
                    track_data = self.current_track

                try:
                    self.current_source = YTDLSource.create_source(track_data, self.ffmpeg_path, volume=self.volume)
                except Exception as e:
                    logger.error(f"Failed to create source for {track_data.get('title')}: {e}")
                    if self.text_channel:
                        self.bot.loop.create_task(
                            self.text_channel.send(f"❌ Failed to play **{track_data.get('title')}**: {e}")
                        )
                    self.current_track = None
                    continue

                if not self.guild.voice_client:
                    return

                self.guild.voice_client.play(self.current_source, after=self.toggle_next)
                await self._play_event.wait()
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in playback loop for guild {self.guild.id}: {e}")

    def toggle_next(self, error=None):
        if error:
            logger.error(f"Player error: {error}")
            
        # Get next track based on loop mode
        next_track = self.queue.get_next(self.current_track)
        self.current_track = next_track
        
        self.bot.loop.call_soon_threadsafe(self._play_event.set)

    def set_volume(self, volume: float):
        self.volume = volume
        if self.current_source and isinstance(self.current_source, discord.PCMVolumeTransformer):
            self.current_source.volume = self.volume
