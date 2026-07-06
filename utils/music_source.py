import asyncio
import os
import tempfile
import base64
import discord
import yt_dlp
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

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as temp_file:
        temp_file.write(cookie_content)
        return temp_file.name


# Debug system environment for yt-dlp
try:
    import shutil
    logger.info(f"System Check - Node.js path: {shutil.which('node')}")
    logger.info(f"System Check - FFmpeg path: {shutil.which('ffmpeg')}")
except Exception as e:
    logger.error(f"Error checking node/ffmpeg path: {e}")

try:
    import yt_dlp.version
    logger.info(f"System Check - yt-dlp version: {yt_dlp.version.__version__}")
except AttributeError:
    try:
        logger.info(f"System Check - yt-dlp version: {yt_dlp.__version__}")
    except Exception as e:
        logger.error(f"Error checking yt-dlp version: {e}")
except Exception as e:
    logger.error(f"Error checking yt-dlp version: {e}")

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt',
    'extractor_args': {
        'youtube': {
            'player_client': ['web', 'mweb', 'android'],
            'formats': ['missing_pot']
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
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
    async def from_url(cls, url: str, *, loop: asyncio.AbstractEventLoop = None, stream: bool = True, ffmpeg_path: str = "ffmpeg") -> List[Any]:
        """
        Extracts info from a URL or search query.
        Returns a list of YTDLSource objects (or dicts if not streaming yet).
        For simplicity, we return the data dicts to create sources right before playback,
        so the stream URL doesn't expire.
        """
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
                raise ValueError("Spotify playlists and albums are not supported yet. Please provide a direct track link.")

        # We need to run extract_info in an executor because it's blocking
        try:
            # First, check if it's a playlist or search
            is_search = url.startswith("ytsearch") or not url.startswith("http")
            query = f"ytsearch:{url}" if is_search and not url.startswith("ytsearch") else url
            
            # Fetch info
            logger.info(f"Starting yt-dlp extract_info for query: {query}")
            def extract():
                current_options = ytdl_format_options.copy()
                active_cookie_path = get_cookie_file()
                if active_cookie_path:
                    current_options['cookiefile'] = active_cookie_path
                with yt_dlp.YoutubeDL(current_options) as ydl:
                    return ydl.extract_info(query, download=not stream)
                    
            data = await loop.run_in_executor(None, extract)
            logger.info(f"Finished yt-dlp extract_info for query: {query}")
            
            if 'entries' in data:
                # It's a playlist or search result
                entries = data['entries']
                if is_search:
