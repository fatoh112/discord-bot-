import re

with open("dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add session to flask imports
content = re.sub(r'from flask import (.*?)\n', r'from flask import \1, session\n', content, count=1)

# Add get_current_guild function
helper = """
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
"""
content = re.sub(r'# Root redirect', helper + '\n# Root redirect', content, count=1)

# Modify index and login to set default session
content = re.sub(
    r'def login\(\):\n    if is_authenticated\(\):\n        return redirect\(url_for\("status"\)\)',
    r'def login():\n    if is_authenticated():\n        if "current_guild_id" not in session and _bot_ref.guilds:\n            session["current_guild_id"] = str(_bot_ref.guilds[0].id)\n        return redirect(url_for("status"))',
    content
)

content = re.sub(
    r'def index\(\):\n    if is_authenticated\(\):\n        return redirect\(url_for\("status"\)\)',
    r'def index():\n    if is_authenticated():\n        if "current_guild_id" not in session and _bot_ref.guilds:\n            session["current_guild_id"] = str(_bot_ref.guilds[0].id)\n        return redirect(url_for("status"))',
    content
)

# Replace cfg = _bot_ref.bot_config with get_guild
content = re.sub(
    r'    cfg = _bot_ref\.bot_config\n',
    r'    guild = get_current_guild()\n    if not guild: return "No guilds found", 400\n    cfg = _bot_ref.bot_config.get_guild(str(guild.id))\n',
    content
)

# Add all_guilds and current_guild to context_processor
context_target = """        return {
            "bot_name": _bot_ref.bot_config.bot_name,
            "bot_avatar": _bot_ref.bot_config.avatar_url
        }"""
context_replacement = """        from flask import session
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
        }"""
content = content.replace(context_target, context_replacement)

# Add the select_guild API route
select_route = """
@app.route('/api/guilds/<guild_id>/select', methods=['GET', 'POST'])
def select_guild(guild_id):
    if not is_authenticated(): return redirect(url_for("login"))
    session['current_guild_id'] = guild_id
    return redirect(request.referrer or url_for("status"))

"""
content = content.replace("# --- Additional API Endpoints ---", "# --- Additional API Endpoints ---\n" + select_route)

# Update metrics/dashboard routes to use guild
content = re.sub(
    r'total_members = sum\(g\.member_count for g in _bot_ref\.guilds\)\s+total_roles = sum\(len\(g\.roles\) - 1 for g in _bot_ref\.guilds\)\s+total_channels = sum\(len\(g\.channels\) for g in _bot_ref\.guilds\)',
    r'guild = get_current_guild()\n    if not guild: return "No guilds found", 400\n    total_members = guild.member_count\n    total_roles = len(guild.roles) - 1\n    total_channels = len(guild.channels)',
    content
)

# Update Audit logs route
content = re.sub(
    r'    return render_template\("admin/audit-logs\.html"\)',
    r'    guild = get_current_guild()\n    return render_template("admin/audit-logs.html", guild=guild)',
    content
)

with open("dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)
