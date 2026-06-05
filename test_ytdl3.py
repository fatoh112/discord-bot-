import yt_dlp
import sys
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
try:
    print("Extracting...")
    info = ytdl.extract_info('ytsearch:تراك بيبسي بلاك مع ابيوسف و مروان بابلو', download=False)
    print("Found entries:", len(info.get('entries', [])))
except Exception as e:
    print("Exception:", str(e))
