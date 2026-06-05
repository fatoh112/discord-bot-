from flask import Blueprint, jsonify, request, session, Response
import json
import time

music_bp = Blueprint('music', __name__, url_prefix='/music')

def get_bot():
    # Helper to get the bot instance from the dashboard
    import dashboard
    return dashboard._bot_ref

@music_bp.route('/<int:guild_id>', methods=['GET'])
def music_status(guild_id):
    import dashboard
    if not dashboard.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
        
    bot = get_bot()
    if not bot:
        return jsonify({"error": "Bot not ready"}), 503
        
    music_cog = bot.get_cog("Music")
    if not music_cog:
        return jsonify({"error": "Music system offline"}), 503
        
    guild = bot.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404
        
    player = music_cog.players.get(guild.id)
    if not player:
        return jsonify({
            "status": "idle",
            "current_track": None,
            "queue": [],
            "volume": 100,
            "loop_mode": 0
        })
        
    current_track = player.current_track
    queue_tracks = player.queue.get_queue()
    
    return jsonify({
        "status": "playing" if guild.voice_client and guild.voice_client.is_playing() else "paused" if guild.voice_client and guild.voice_client.is_paused() else "idle",
        "current_track": current_track,
        "queue": queue_tracks,
        "volume": int(player.volume * 100),
        "loop_mode": player.queue.loop_mode
    })

@music_bp.route('/<int:guild_id>/play', methods=['POST'])
def play(guild_id):
    import dashboard
    import asyncio
    if not dashboard.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({"error": "Missing query"}), 400
        
    bot = get_bot()
    music_cog = bot.get_cog("Music")
    if not music_cog:
        return jsonify({"error": "Music system offline"}), 503
        
    guild = bot.get_guild(guild_id)
    player = music_cog.get_player(guild)
    
    from utils.music_source import YTDLSource
    try:
        future = asyncio.run_coroutine_threadsafe(
            YTDLSource.from_url(query, loop=bot.loop, stream=True, ffmpeg_path=music_cog.ffmpeg_path),
            bot.loop
        )
        entries = future.result(timeout=20)
    except Exception as e:
        return jsonify({"error": f"Failed to extract info: {str(e)}"}), 400
        
    if not entries:
        return jsonify({"error": "No results found"}), 404
        
    added = 0
    for entry in entries:
        if player.queue.add_track(entry):
            added += 1
            
    if not player.current_track:
        bot.loop.call_soon_threadsafe(player._play_event.set)
        
    return jsonify({"success": True, "added": added})

@music_bp.route('/<int:guild_id>/pause', methods=['POST'])
def pause(guild_id):
    import dashboard
    if not dashboard.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    bot = get_bot()
    guild = bot.get_guild(guild_id)
    if guild and guild.voice_client and guild.voice_client.is_playing():
        guild.voice_client.pause()
        return jsonify({"success": True, "status": "paused"})
    return jsonify({"error": "Cannot pause"}), 400

@music_bp.route('/<int:guild_id>/skip', methods=['POST'])
def skip(guild_id):
    import dashboard
    if not dashboard.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    bot = get_bot()
    guild = bot.get_guild(guild_id)
    if guild and guild.voice_client:
        guild.voice_client.stop()
        return jsonify({"success": True, "status": "skipped"})
    return jsonify({"error": "Nothing playing"}), 400

@music_bp.route('/<int:guild_id>/stream')
def stream(guild_id):
    """Server-Sent Events endpoint for real-time updates without websockets."""
    import dashboard
    if not dashboard.is_authenticated():
        return Response("Unauthorized", status=401)
        
    def generate():
        bot = get_bot()
        music_cog = bot.get_cog("Music")
        while True:
            if not music_cog:
                yield f"data: {json.dumps({'error': 'Music offline'})}\n\n"
            else:
                player = music_cog.players.get(guild_id)
                if player:
                    data = {
                        "current_track": player.current_track,
                        "queue_length": len(player.queue.get_queue())
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            time.sleep(2)  # Poll every 2 seconds
            
    return Response(generate(), mimetype="text/event-stream")
