import asyncio
import discord
import yt_dlp
from loguru import logger
from typing import Dict, Any, List

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True, # We handle playlists manually
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'socket_timeout': 15,
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.webpage_url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url: str, *, loop: asyncio.AbstractEventLoop = None, stream: bool = True, ffmpeg_path: str = "ffmpeg") -> List[Any]:
        """
        Extracts info from a URL or search query.
        Returns a list of YTDLSource objects (or dicts if not streaming yet).
        For simplicity, we return the data dicts to create sources right before playback,
        so the stream URL doesn't expire.
        """
        loop = loop or asyncio.get_event_loop()
        
        # We need to run extract_info in an executor because it's blocking
        try:
            # First, check if it's a playlist or search
            is_search = url.startswith("ytsearch") or not url.startswith("http")
            query = f"ytsearch:{url}" if is_search and not url.startswith("ytsearch") else url
            
            # Fetch info
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=not stream))
            
            if 'entries' in data:
                # It's a playlist or search result
                entries = data['entries']
                if is_search:
                    # Take only the first search result
                    entries = [entries[0]] if entries else []
                return entries
            else:
                return [data]
        except Exception as e:
            logger.error(f"Error extracting info for {url}: {e}")
            raise e

    @classmethod
    def create_source(cls, data: dict, ffmpeg_path: str = "ffmpeg", volume: float = 1.0):
        """Creates an audio source from pre-fetched data."""
        stream_url = data.get('url')
        if not stream_url:
            raise ValueError("Stream URL not found in extracted data")
            
        source = discord.FFmpegPCMAudio(stream_url, executable=ffmpeg_path, **ffmpeg_options)
        # Bypass PCMVolumeTransformer completely to avoid audioop-lts segfault on Win/3.14
        return source
