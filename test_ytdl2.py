import yt_dlp
import sys
ytdl = yt_dlp.YoutubeDL({'quiet': True, 'default_search': 'auto'})
try:
    info = ytdl.extract_info('ytsearch:تراك بيبسي بلاك مع ابيوسف و مروان بابلو', download=False)
    print("Found entries:", len(info.get('entries', [])))
except Exception as e:
    print("Exception:", str(e))
