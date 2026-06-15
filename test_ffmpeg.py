import yt_dlp, subprocess, shlex

ytdl = yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True})
data = ytdl.extract_info('ytsearch:Temper City - Self Aware', download=False)['entries'][0]
url = data['url']

headers_str = "".join([f"{k}: {v}\r\n" for k, v in data.get('http_headers', {}).items()])
opts = f'-headers "{headers_str}" -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'

args = [r'E:\discord bot\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'] + shlex.split(opts) + ['-i', url, '-t', '2', '-f', 'null', '-']

print("Args passed to Popen:")
print(args)

p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
out, err = p.communicate()
print('RC:', p.returncode)
print('STDERR:', err.decode())
