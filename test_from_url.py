import asyncio
import sys
from utils.music_source import YTDLSource

async def main():
    print("Starting from_url...")
    try:
        entries = await asyncio.wait_for(
            YTDLSource.from_url('ytsearch:تراك بيبسي بلاك مع ابيوسف و مروان بابلو', stream=True, ffmpeg_path='ffmpeg'),
            timeout=30.0
        )
        print("Success! Entries:", len(entries))
    except Exception as e:
        print("Failed:", type(e).__name__, e)

if __name__ == "__main__":
    asyncio.run(main())
