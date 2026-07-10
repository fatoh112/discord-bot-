import asyncio
import os
import tempfile
import base64
import discord
import yt_dlp
import shutil
from loguru import logger
from typing import Dict, Any, List, Optional

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

def get_cookie_file():
    raw_cookies = os.getenv("YOUTUBE_COOKIES", "")
    try:
        cookie_content = base64.b64decode(raw_cookies).decode('utf-8')
    except Exception:
        cookie_content = raw_cookies

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as temp_file:
        temp_file.write(cookie_content)
        return temp_file.name

# Debug system environment for yt-dlp
try:
    logger.info(f"System Check - Node.js path: {shutil.which('node')}")
    logger.info(f"System Check - FFmpeg path: /app/ffmpeg")
except Exception as e:
    logger.error(f"Error checking path: {e}")

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0'
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
        self.reads = 0

    def read(self) -> bytes:
        data = super().read()
        if data:
            self.reads += 1
        return data

    @property
    def elapsed(self) -> float:
        return self.reads * 0.02

    @classmethod
    def _get_ffmpeg_path(cls) -> str:
        if os.path.exists("/app/ffmpeg"):
            return "/app/ffmpeg"
        return shutil.which("ffmpeg") or "ffmpeg"

    @classmethod
    async def from_url(cls, url: str, *, loop: asyncio.AbstractEventLoop = None, stream: bool = True) -> List[Any]:
        loop = loop or asyncio.get_event_loop()
        
        # Resolve Spotify track links to search query
        if "spotify.com" in url:
            import aiohttp
            import re
            if "/track/" in url:
                try:
                    logger.info(f"Resolving Spotify track link: {url}")
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
                                logger.info(f"Resolved Spotify link to query: {title}")
                                url = title
                            else:
                                raise ValueError("Could not extract title metadata from Spotify track link")
                except Exception as e:
                    logger.error(f"Failed to resolve spotify link {url}: {e}")
                    raise e
            else:
                raise ValueError("Spotify playlists and albums are not supported yet.")

        # التعديل الحاسم: جعل البحث الافتراضي يعتمد على ساوند كلاود وليس يوتيوب
        is_search = not url.startswith("http")
        query = f"scsearch:{url}" if is_search else url
        
        try:
            logger.info(f"Starting yt-dlp extract_info for query: {query}")
            def extract():
                current_options = ytdl_format_options.copy()
                with yt_dlp.YoutubeDL(current_options) as ydl:
                    return ydl.extract_info(query, download=not stream)
                    
            data = await loop.run_in_executor(None, extract)
            logger.info(f"Finished yt-dlp extract_info for query: {query}")
            
            if 'entries' in data:
                entries = data['entries']
                if is_search:
                    entries = [entries[0]] if entries else []
                return entries
            else:
                return [data]
        except Exception as e:
            logger.error(f"Error extracting info for {url}: {e}")
            raise e

    @classmethod
    async def create_source(cls, data: dict, volume: float = 1.0, loop: asyncio.AbstractEventLoop = None):
        stream_url = data.get('url')
        
        if not stream_url or data.get('is_search') or 'SoundCloud' in data.get('extractor_key', ''):
            loop = loop or asyncio.get_event_loop()
            try:
                webpage_url = data.get('webpage_url') or data.get('url')
                logger.info(f"Refetching stream URL for {webpage_url}")
                def extract():
                    current_options = ytdl_format_options.copy()
                    with yt_dlp.YoutubeDL(current_options) as ydl:
                        return ydl.extract_info(webpage_url, download=False)
                new_data = await loop.run_in_executor(None, extract)
                stream_url = new_data.get('url')
                data['http_headers'] = new_data.get('http_headers', {})
            except Exception as e:
                logger.error(f"Failed to refetch stream url: {e}")

        if not stream_url:
            raise ValueError("Stream URL not found in extracted data")
            
        opts = ffmpeg_options.copy()
        headers = data.get('http_headers', {})
        if headers:
            headers_str = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
            opts['before_options'] = f'-headers "{headers_str}" ' + opts.get('before_options', '')
            
        # استخدام مسار FFmpeg الصحيح ديناميكياً
        resolved_ffmpeg = cls._get_ffmpeg_path()
        source = discord.FFmpegPCMAudio(stream_url, executable=resolved_ffmpeg, **opts)
        return cls(source, data=data, volume=volume)
