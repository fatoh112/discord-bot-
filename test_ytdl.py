import yt_dlp
import sys
print("yt-dlp version:", yt_dlp.version.__version__)
ytdl_format_options = {'quiet': True, 'default_search': 'auto'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
try:
    info = ytdl.extract_info('ytsearch:marwan pablo flexin', download=False)
    print("Found entries:", len(info.get('entries', [])))
except Exception as e:
    print("Exception:", str(e))
