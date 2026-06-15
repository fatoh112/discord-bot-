import os
import sys
import time
import socket
import secrets
import bcrypt
import psutil
from threading import Thread
from typing import Dict, Any, Optional, List
from flask import Flask, jsonify, request, render_template, render_template_string, make_response, redirect, url_for, flash, session
from loguru import logger

# Helper to check if a port is in use
def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# Flask App Initialization
app = Flask("AntigravityDashboard", template_folder="templates")
from routes.music import music_bp
app.register_blueprint(music_bp)

@app.context_processor
def inject_global_vars():
    global _bot_ref
    if _bot_ref and hasattr(_bot_ref, "bot_config"):
        from flask import session
        guild_id = session.get('current_guild_id')
        current_guild = None
        if guild_id:
            current_guild = _bot_ref.get_guild(int(guild_id))
        elif _bot_ref.guilds:
            current_guild = _bot_ref.guilds[0]
            
        return {
            "bot_name": _bot_ref.bot_config.bot_name,
            "bot_avatar": _bot_ref.bot_config.avatar_url,
            "current_guild": current_guild,
            "all_guilds": _bot_ref.guilds
        }
    return {"bot_name": "Antigravity", "bot_avatar": None}

# Global variables/caches
_bot_ref: Any = None
_start_time = time.time()
_sessions: Dict[str, float] = {}  # token -> expiry_timestamp
_ip_rate_limits: Dict[str, List[float]] = {}  # ip -> request timestamps
_cached_metrics: Dict[str, Any] = {}
_active_alerts: List[Dict[str, Any]] = []

# Secret Key for Flask sessions / signatures
app.secret_key = secrets.token_hex(24)

# Removed inline STATUS_HTML and LOGIN_HTML since we use templates

# Custom Rate Limiter Middleware
@app.before_request
def check_rate_limit():
    ip = request.remote_addr
    now = time.time()
    
    timestamps = _ip_rate_limits.get(ip, [])
    timestamps = [t for t in timestamps if now - t < 60]
    _ip_rate_limits[ip] = timestamps

    if len(timestamps) >= 100:  # 100 req/min
        return make_response(jsonify({"error": "Rate limit exceeded. Max 100 requests per minute."}), 429)
    
    _ip_rate_limits[ip].append(now)

# CORS Header Injector
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin and ("localhost" in origin or "127.0.0.1" in origin):
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Shutdown-Token"
    
    # Log request to audit.log
    logger.bind(audit=True).info(f"DASHBOARD | IP: {request.remote_addr} | Request: {request.method} {request.path} | Status: {response.status_code}")
    return response

# Session Helper
def get_session_token() -> Optional[str]:
    return request.cookies.get("session_token")

def is_authenticated() -> bool:
    token = get_session_token()
    if not token or token not in _sessions:
        return False
    if time.time() > _sessions[token]:
        _sessions.pop(token, None)
        return False
    # Extend session
    _sessions[token] = time.time() + 1800
    return True


def get_current_guild():
    guild_id = session.get('current_guild_id')
    if guild_id:
        guild = _bot_ref.get_guild(int(guild_id))
        if guild:
            return guild
            
    if _bot_ref and _bot_ref.guilds:
        session['current_guild_id'] = str(_bot_ref.guilds[0].id)
        return _bot_ref.guilds[0]
    return None

# Root redirect
@app.route("/", methods=["GET"])
def index():
    if is_authenticated():
        if "current_guild_id" not in session and _bot_ref.guilds:
            session["current_guild_id"] = str(_bot_ref.guilds[0].id)
        return redirect(url_for("status"))
    return redirect(url_for("login"))

# Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        if "current_guild_id" not in session and _bot_ref.guilds:
            session["current_guild_id"] = str(_bot_ref.guilds[0].id)
        return redirect(url_for("status"))
        
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        expected_user = _bot_ref.bot_config.dashboard_username if _bot_ref else "admin"
        hashed_pass = _bot_ref.bot_config.dashboard_password_hash if _bot_ref else ""

        if username == expected_user and hashed_pass and bcrypt.checkpw(password.encode(), hashed_pass.encode()):
            token = secrets.token_hex(32)
            _sessions[token] = time.time() + 1800 # 30 min expiry
            resp = make_response(redirect(url_for("status")))
            resp.set_cookie("session_token", token, httponly=True, samesite="Strict")
            return resp
        else:
            error = "Invalid credentials."

    return render_template("login.html", error=error)

# Logout Route
@app.route("/logout", methods=["GET", "POST"])
def logout():
    token = get_session_token()
    if token:
        _sessions.pop(token, None)
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("session_token")
    return resp

# Health Check Router
@app.route("/health", methods=["GET"])
def health():
    if _bot_ref and _bot_ref.is_closed():
        return jsonify({"status": "unhealthy", "message": "Bot is disconnected"}), 503

    # Check for basic auth if provided, but don't force it (fallback)
    auth = request.authorization
    if auth:
        expected_user = _bot_ref.bot_config.dashboard_username if _bot_ref else "admin"
        hashed_pass = _bot_ref.bot_config.dashboard_password_hash if _bot_ref else ""
        if not (auth.username == expected_user and hashed_pass and bcrypt.checkpw(auth.password.encode(), hashed_pass.encode())):
            return make_response("Invalid Basic Auth", 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    uptime = int(time.time() - _start_time)
    status_data = {
        "status": "healthy" if (_bot_ref and not _bot_ref.is_closed()) else "unhealthy",
        "uptime_seconds": uptime,
        "version": "1.0.0"
    }
    return jsonify(status_data)

# HTML Status Route
@app.route("/status", methods=["GET"])
def status():
    if not is_authenticated():
        return redirect(url_for("login"))

    uptime_sec = int(time.time() - _start_time)
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    uptime_str = f"{days}d, {hours}h, {minutes}m"

    mem_usage = int(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    cpu_usage = psutil.cpu_percent(interval=None)
    
    ws_latency = int(_bot_ref.latency * 1000) if _bot_ref else 0
    guilds_count = len(_bot_ref.guilds) if _bot_ref else 0
    members_count = sum(len(g.members) for g in _bot_ref.guilds) if _bot_ref else 0
    
    # Fetch queue depth from AutoRole cog join_queue
    queue_depth = 0
    if _bot_ref:
        autorole_cog = _bot_ref.get_cog("AutoRoleCog")
        if autorole_cog:
            queue_depth = autorole_cog.join_queue.qsize()

    err_count = 0
    if _bot_ref:
        import asyncio
        try:
            err_count = asyncio.run_coroutine_threadsafe(
                _bot_ref.metrics.get("error_count_24h", "SYSTEM"), _bot_ref.loop
            ).result() or 0
        except Exception:
            err_count = 0

    logs_text = ""
    import glob
    log_files = glob.glob("logs/bot_*.log")
    if os.path.exists("logs/bot.log"):
        log_files.append("logs/bot.log")
    
    if log_files:
        latest_log = max(log_files, key=os.path.getmtime)
        try:
            with open(latest_log, "r", encoding="utf-8") as f:
                logs_text = "".join(f.readlines()[-20:])
        except Exception:
            logs_text = "Error reading log output."

    return render_template(
        "status.html",
        uptime=uptime_str,
        mem_usage=mem_usage,
        cpu_usage=cpu_usage,
        ws_latency=ws_latency,
        guilds_count=guilds_count,
        members_count=members_count,
        queue_depth=queue_depth,
        err_count=err_count,
        logs=logs_text
    )

# --- Admin Routes ---
@app.route("/admin/music")
def admin_music():
    if not is_authenticated(): return redirect(url_for("login"))
    from flask import send_from_directory
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'dashboard-ui', 'dist'), 'index.html')

@app.route('/assets/<path:path>')
def serve_react_assets(path):
    from flask import send_from_directory
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'dashboard-ui', 'dist', 'assets'), path)

@app.route('/favicon.svg')
def serve_favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'dashboard-ui', 'dist'), 'favicon.svg')

@app.route('/icons.svg')
def serve_icons():
    from flask import send_from_directory
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'dashboard-ui', 'dist'), 'icons.svg')

@app.route("/admin/autorole", methods=["GET", "POST"])
def admin_autorole():
    if not is_authenticated(): return redirect(url_for("login"))
    
    guild = get_current_guild()
    if not guild: return "No guilds found", 400
    cfg = _bot_ref.bot_config.get_guild(str(guild.id))
    if request.method == "POST":
        action = request.form.get("action")
        import config_schema
        
        if action == "toggle_enable":
            cfg.autorole.enabled = not cfg.autorole.enabled
        elif action == "update_settings":
            cfg.autorole.delay_seconds = int(request.form.get("delay_seconds", 2))
            cfg.autorole.exclude_bots = "exclude_bots" in request.form
            cfg.autorole.require_verification = "require_verification" in request.form
        elif action == "add_role":
            role_id = request.form.get("role_id")
            priority = int(request.form.get("priority", 0))
            if role_id and not any(r.id == role_id for r in cfg.autorole.roles):
                cfg.autorole.roles.append(config_schema.AutoRoleItem(id=role_id, priority=priority))
        elif action == "remove_role":
            role_id = request.form.get("role_id")
            cfg.autorole.roles = [r for r in cfg.autorole.roles if r.id != role_id]

        config_schema.save_config(cfg)
        return redirect(url_for("admin_autorole"))

    return render_template("admin/autorole.html", config=cfg.autorole)

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if not is_authenticated(): return redirect(url_for("login"))
    
    guild = get_current_guild()
    if not guild: return "No guilds found", 400
    cfg = _bot_ref.bot_config.get_guild(str(guild.id))
    if request.method == "POST":
        import config_schema
        cfg.bot_name = request.form.get("bot_name", cfg.bot_name)
        cfg.prefix = request.form.get("prefix", cfg.prefix)
        cfg.timezone = request.form.get("timezone", cfg.timezone)
        cfg.language = request.form.get("language", cfg.language)
        cfg.gdpr_retention_days = int(request.form.get("gdpr_retention_days", cfg.gdpr_retention_days))
        
        config_schema.save_config(cfg)
        return redirect(url_for("admin_settings"))

    return render_template("admin/settings.html", config=cfg)

# Temporary stubs for remaining admin pages
@app.route("/admin/welcome", methods=["GET", "POST"])
def admin_welcome():
    if not is_authenticated(): return redirect(url_for("login"))
    
    guild = get_current_guild()
    if not guild: return "No guilds found", 400
    cfg = _bot_ref.bot_config.get_guild(str(guild.id))
    if request.method == "POST":
        action = request.form.get("action")
        import config_schema
        
        if action == "toggle_enable":
            cfg.welcome.enabled = not cfg.welcome.enabled
        elif action == "update_settings":
            cfg.welcome.channel_id = request.form.get("channel_id") or None
            cfg.welcome.template = request.form.get("template", cfg.welcome.template)
            cfg.welcome.send_dm = "send_dm" in request.form
            cfg.welcome.enable_verification_button = "enable_verification_button" in request.form
            
        config_schema.save_config(cfg)
        return redirect(url_for("admin_welcome"))

    return render_template("admin/welcome.html", config=cfg.welcome)

@app.route("/admin/verification", methods=["GET", "POST"])
def admin_verification():
    if not is_authenticated(): return redirect(url_for("login"))
    
    guild = get_current_guild()
    if not guild: return "No guilds found", 400
    cfg = _bot_ref.bot_config.get_guild(str(guild.id))
    if request.method == "POST":
        import config_schema
        # If method was changed via radio buttons, it submits automatically
        if "method" in request.form:
            cfg.verification.method = request.form.get("method")
            
        if request.form.get("action") == "save":
            cfg.verification.unverified_role_id = request.form.get("unverified_role_id") or None
            cfg.verification.verified_role_id = request.form.get("verified_role_id") or None
            cfg.verification.timeout_hours = int(request.form.get("timeout_hours", 24))
            cfg.verification.auto_kick = "auto_kick" in request.form
            
        config_schema.save_config(cfg)
        return redirect(url_for("admin_verification"))
        
    return render_template("admin/verification.html", config=cfg.verification)

@app.route("/admin/reaction-roles", methods=["GET", "POST"])
def admin_reaction_roles():
    if not is_authenticated(): return redirect(url_for("login"))
    return render_template("admin/reaction-roles.html")

@app.route("/admin/raid-protection", methods=["GET", "POST"])
def admin_raid_protection():
    if not is_authenticated(): return redirect(url_for("login"))
    
    guild = get_current_guild()
    if not guild: return "No guilds found", 400
    cfg = _bot_ref.bot_config.get_guild(str(guild.id))
    if request.method == "POST":
        action = request.form.get("action")
        import config_schema
        
        if action == "toggle_enable":
            cfg.raid_protection.enabled = not cfg.raid_protection.enabled
            config_schema.save_config(cfg)
        elif action == "update_settings":
            cfg.raid_protection.join_velocity_threshold = int(request.form.get("join_velocity_threshold", 10))
            cfg.raid_protection.account_age_hours = int(request.form.get("account_age_hours", 24))
            config_schema.save_config(cfg)
        elif action == "force_lockdown":
            state = request.form.get("lockdown_state")
            # In a real scenario, this would notify the bot to enable its internal memory lockdown state
            # For now we'll simulate by calling the cog if it exists
            health_cog = _bot_ref.get_cog("HealthCog") # Example cog that might manage state
            if health_cog and hasattr(health_cog, "force_lockdown"):
                import asyncio
                asyncio.run_coroutine_threadsafe(health_cog.force_lockdown(state == "on"), _bot_ref.loop)
                
        return redirect(url_for("admin_raid_protection"))

    # Check if currently in lockdown
    lockdown_active = False # Default state unless retrieved from bot memory
    return render_template("admin/raid-protection.html", config=cfg.raid_protection, lockdown_active=lockdown_active)

@app.route("/admin/members", methods=["GET", "POST"])
def admin_members():
    if not is_authenticated(): return redirect(url_for("login"))
    return render_template("admin/members.html")

# --- API Endpoints for Dashboard ---
@app.route("/api/guilds", methods=["GET"])
def api_get_guilds():
    if not is_authenticated() or not _bot_ref:
        return jsonify([])
    
    guilds_data = []
    for g in _bot_ref.guilds:
        guilds_data.append({
            "id": str(g.id),
            "name": g.name,
            "icon": g.icon.url if g.icon else None,
            "member_count": g.member_count
        })
    return jsonify(guilds_data)

@app.route("/api/guilds/<int:guild_id>/members", methods=["GET"])
def api_get_members(guild_id):
    if not is_authenticated() or not _bot_ref:
        return jsonify([])
        
    guild = _bot_ref.get_guild(guild_id)
    if not guild:
        return jsonify({"error": "Guild not found"}), 404
        
    members_data = []
    for m in guild.members:
        # Avoid huge payloads, only send necessary data
        members_data.append({
            "id": str(m.id),
            "name": m.name,
            "bot": m.bot,
            "avatar": m.display_avatar.url if m.display_avatar else None,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            "roles": [{"id": str(r.id), "name": r.name, "color": str(r.color)} for r in m.roles if r.name != "@everyone"]
        })
    return jsonify(members_data)

@app.route("/api/guilds/<int:guild_id>/members/bulk-role", methods=["POST"])
def api_bulk_role(guild_id):
    if not is_authenticated() or not _bot_ref:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    user_ids = data.get("user_ids", [])
    role_id = data.get("role_id")
    action = data.get("action")  # 'add' or 'remove'
    
    if not user_ids or not role_id or action not in ['add', 'remove']:
        return jsonify({"error": "Invalid payload"}), 400
        
    import asyncio
    import discord
    async def process_bulk_role():
        guild = _bot_ref.get_guild(guild_id)
        if not guild: return False
        
        role = guild.get_role(int(role_id))
        if not role: return False
        
        success_count = 0
        failed_count = 0
        errors = []
        for uid in user_ids:
            member = guild.get_member(int(uid))
            if not member:
                try:
                    member = await guild.fetch_member(int(uid))
                except Exception as e:
                    logger.error(f"Failed to fetch member {uid}: {e}")
                    failed_count += 1
                    errors.append(f"Member {uid} not found in guild.")
                    continue
            
            try:
                if action == 'add':
                    await member.add_roles(role, reason="Dashboard Bulk Assignment")
                else:
                    await member.remove_roles(role, reason="Dashboard Bulk Removal")
                success_count += 1
            except discord.Forbidden as e:
                logger.error(f"Bulk role permission error on {uid}: {e}")
                failed_count += 1
                errors.append(f"Missing permissions/hierarchy limit to modify roles for {member.name}.")
            except Exception as e:
                logger.error(f"Bulk role error on {uid}: {e}")
                failed_count += 1
                errors.append(f"Failed to update {member.name}: {e}")
                
        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": list(set(errors))
        }
        
    future = asyncio.run_coroutine_threadsafe(process_bulk_role(), _bot_ref.loop)
    try:
        result = future.result(timeout=15)
        if result is False:
            return jsonify({"error": "Guild or Role not found"}), 404
            
        success_count = result["success_count"]
        failed_count = result["failed_count"]
        errors = result["errors"]
        
        if success_count == 0 and failed_count > 0:
            error_msg = errors[0] if errors else "Failed to modify roles."
            return jsonify({"error": error_msg, "processed": 0, "failed": failed_count}), 400
            
        return jsonify({
            "success": True,
            "processed": success_count,
            "failed": failed_count,
            "errors": errors
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/audit-logs", methods=["GET"])
def admin_audit_logs():
    if not is_authenticated(): return redirect(url_for("login"))
    guild = get_current_guild()
    return render_template("admin/audit-logs.html", guild=guild)

@app.route("/admin/commands", methods=["GET", "POST"])
def admin_commands():
    if not is_authenticated(): return redirect(url_for("login"))
    return render_template("admin/commands.html")

# --- Additional API Endpoints ---

@app.route('/api/guilds/<guild_id>/select', methods=['GET', 'POST'])
def select_guild(guild_id):
    if not is_authenticated(): return redirect(url_for("login"))
    session['current_guild_id'] = guild_id
    return redirect(request.referrer or url_for("status"))



@app.route("/api/audit-logs", methods=["GET"])
def api_audit_logs():
    if not is_authenticated() or not _bot_ref: return jsonify([])
    
    # We will simulate fetching by getting the latest logs from the DB
    # The models get_audit_logs takes target_id, but we probably want a global fetch.
    # For now, we'll execute a direct query.
    import asyncio
    async def fetch_logs():
        search = request.args.get("search", "").lower()
        action_filter = request.args.get("action", "")
        
        query = "SELECT id, timestamp, admin_id, action, target_id, reason FROM audit_logs ORDER BY id DESC LIMIT 50"
        rows = await _bot_ref.models.db.fetchall(query)
        
        results = []
        for r in rows:
            act = r["action"]
            reas = r["reason"] or ""
            tgt = r["target_id"] or ""
            
            if action_filter and action_filter != act:
                continue
            if search and search not in reas.lower() and search not in tgt.lower():
                continue
                
            results.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "admin_id": r["admin_id"],
                "action": act,
                "target_id": tgt,
                "reason": reas
            })
        return results
        
    try:
        future = asyncio.run_coroutine_threadsafe(fetch_logs(), _bot_ref.loop)
        logs = future.result(timeout=5)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/commands", methods=["GET"])
def api_commands():
    if not is_authenticated() or not _bot_ref: return jsonify([])
    
    cmds = []
    # Fetch registered commands from the tree
    for cmd in _bot_ref.tree.get_commands():
        options = []
        if hasattr(cmd, "parameters"):
            options = [p.name for p in cmd.parameters]
            
        cmds.append({
            "name": cmd.name,
            "description": cmd.description or "No description",
            "options": options
        })
    return jsonify(cmds)

@app.route("/api/commands/sync", methods=["POST"])
def api_commands_sync():
    if not is_authenticated() or not _bot_ref: return jsonify({"error": "Unauthorized"}), 401
    import asyncio
    
    async def do_sync():
        await _bot_ref.tree.sync()
        
    try:
        future = asyncio.run_coroutine_threadsafe(do_sync(), _bot_ref.loop)
        future.result(timeout=10)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/guilds/<int:guild_id>/roles", methods=["GET"])
def api_get_roles(guild_id):
    if not is_authenticated() or not _bot_ref: return jsonify([])
    guild = _bot_ref.get_guild(guild_id)
    if not guild: return jsonify({"error": "Guild not found"}), 404
    
    roles_data = [{"id": str(r.id), "name": r.name, "color": str(r.color)} for r in guild.roles if r.name != "@everyone"]
    return jsonify(roles_data)

@app.route("/api/guilds/<int:guild_id>/channels", methods=["GET"])
def api_get_channels(guild_id):
    if not is_authenticated() or not _bot_ref: return jsonify([])
    guild = _bot_ref.get_guild(guild_id)
    if not guild: return jsonify({"error": "Guild not found"}), 404
    
    import discord
    channels_data = [{"id": str(c.id), "name": c.name} for c in guild.channels if isinstance(c, discord.TextChannel)]
    return jsonify(channels_data)

@app.route("/api/reaction-roles", methods=["GET", "POST"])
def api_reaction_roles():
    if not is_authenticated() or not _bot_ref: return jsonify({"error": "Unauthorized"}), 401
    
    import asyncio
    db_models = _bot_ref.models
    
    if request.method == "GET":
        future = asyncio.run_coroutine_threadsafe(db_models.get_reaction_roles(), _bot_ref.loop)
        try:
            roles = future.result(timeout=5)
            return jsonify(roles)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    elif request.method == "POST":
        data = request.json
        channel_id = int(data.get("channel_id"))
        role_id = data.get("role_id")
        emoji = data.get("emoji")
        exclusive_group = data.get("exclusive_group") or None
        msg_text = data.get("message")
        
        # We need to dispatch a task to send the message in the channel and save to DB
        async def create_panel():
            channel = _bot_ref.get_channel(channel_id)
            if not channel: raise ValueError("Channel not found")
            
            msg = await channel.send(msg_text)
            await msg.add_reaction(emoji)
            await db_models.save_reaction_role(str(msg.id), str(channel_id), emoji, role_id, exclusive_group)
            return str(msg.id)
            
        future = asyncio.run_coroutine_threadsafe(create_panel(), _bot_ref.loop)
        try:
            msg_id = future.result(timeout=10)
            return jsonify({"success": True, "message_id": msg_id})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/api/reaction-roles/<message_id>", methods=["DELETE"])
def api_reaction_role_delete(message_id):
    if not is_authenticated() or not _bot_ref: return jsonify({"error": "Unauthorized"}), 401
    import asyncio
    
    async def delete_panel():
        # Optional: try to delete the message if possible
        await _bot_ref.models.delete_reaction_role(message_id)
        
    future = asyncio.run_coroutine_threadsafe(delete_panel(), _bot_ref.loop)
    try:
        future.result(timeout=5)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not is_authenticated(): return redirect(url_for("login"))
    return render_template("base.html")



# Prometheus metrics endpoint
@app.route("/metrics", methods=["GET"])
def metrics():
    if not is_authenticated():
        return redirect(url_for("login"))

    output = []
    if _bot_ref:
        # Loop through metrics data by guild_id
        async def fetch_metrics():
            # Standard metrics formatting
            lines = []
            for guild_id, data in _bot_ref.metrics.data.items():
                for metric_name, value in data.items():
                    # Format as Prometheus gauge/counter
                    lines.append(f"# HELP {metric_name} Metric value of {metric_name}")
                    lines.append(f"# TYPE {metric_name} gauge")
                    lines.append(f'{metric_name}{{guild_id="{guild_id}"}} {value}')
            return "\n".join(lines)
        
        metrics_str = asyncio.run_coroutine_threadsafe(fetch_metrics(), _bot_ref.loop).result()
        output.append(metrics_str)

    return make_response("\n".join(output) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"})

# Alerts endpoint showing active alerts
@app.route("/alerts", methods=["GET"])
def alerts():
    if not is_authenticated():
        return redirect(url_for("login"))
    return jsonify({"alerts": _active_alerts})

# Secure Shutdown endpoint
@app.route("/shutdown", methods=["POST"])
def shutdown():
    token = request.headers.get("X-Shutdown-Token")
    expected_token = _bot_ref.bot_config.encryption_key if _bot_ref else None
    
    if not token or token != expected_token:
        return make_response(jsonify({"error": "Unauthorized"}), 401)
        
    logger.warning("Shutdown command received via Dashboard endpoint!")
    if _bot_ref:
        asyncio.run_coroutine_threadsafe(_bot_ref.shutdown(), _bot_ref.loop)
    return jsonify({"status": "shutdown_initiated"})

# Background Loop Tasks for Dashboard
async def start_dashboard(bot: Any) -> None:
    global _bot_ref
    _bot_ref = bot
    
    ports = [8080, 8081, 8082]
    selected_port = None
    
    for port in ports:
        if not is_port_in_use(port):
            selected_port = port
            break
            
    if selected_port is None:
        logger.error("Failed to find available dashboard port on localhost (8080-8082). Flask dashboard disabled.")
        return

    # Write selected port to .port file
    try:
        with open(".port", "w") as f:
            f.write(str(selected_port))
    except Exception as e:
        logger.error(f"Failed to write .port file: {e}")

    logger.info(f"Starting Flask dashboard server on localhost:{selected_port}...")
    
    # Start Background thread loops for Alert evaluations & cache flushes
    def alert_evaluation_worker():
        while not bot.is_closed():
            try:
                time.sleep(300) # Every 5 minutes
                # Evaluate alerts
                eval_alerts()
            except Exception as e:
                logger.error(f"Alert evaluation worker error: {e}")

    def eval_alerts():
        global _active_alerts
        alerts_list = []
        import datetime
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # 1. Disk Space check
        try:
            free_gb = psutil.disk_usage('.').free / (1024 ** 3)
            if free_gb < 1.0:
                alerts_list.append({
                    "type": "DiskSpaceLow",
                    "severity": "critical",
                    "message": f"Disk space is low: {free_gb:.2f} GB free.",
                    "timestamp": now_ts
                })
        except Exception:
            pass

        # 2. Memory RSS check
        try:
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            if mem_mb > 500:
                alerts_list.append({
                    "type": "MemoryHigh",
                    "severity": "warning",
                    "message": f"Memory footprint exceeds 500MB: {mem_mb:.2f} MB RSS.",
                    "timestamp": now_ts
                })
        except Exception:
            pass

        # 3. High Error Rate check
        if _bot_ref:
            try:
                import asyncio
                err_count = asyncio.run_coroutine_threadsafe(
                    _bot_ref.metrics.get("error_count_24h", "SYSTEM"), _bot_ref.loop
                ).result() or 0
                if err_count > 10:
                    alerts_list.append({
                        "type": "HighErrorRate",
                        "severity": "warning",
                        "message": f"High error count in rolling 24h: {err_count} errors.",
                        "timestamp": now_ts
                    })
            except Exception:
                pass

        _active_alerts = alerts_list

    # Run background thread for alerts
    t_alerts = Thread(target=alert_evaluation_worker, daemon=True)
    t_alerts.start()

    # Run Flask app inside thread
    def run():
        try:
            app.run(host="localhost", port=selected_port, debug=False, use_reloader=False, threaded=True)
        except Exception as e:
            logger.error(f"Flask dashboard runtime crash: {e}")
            
    thread = Thread(target=run, daemon=True)
    thread.start()


