with open("cogs/autorole/cog.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("self.bot.bot_config.autorole.roles", "self.bot.bot_config.get_guild(str(member.guild.id)).autorole.roles")
content = content.replace("self.bot.bot_config.autorole.exclude_bots", "self.bot.bot_config.get_guild(str(member.guild.id if 'member' in locals() else interaction.guild.id if 'interaction' in locals() else list(self.bot.guilds)[0].id)).autorole.exclude_bots")

# It's better to just use string replacements on the specific lines:

# cogs/autorole/cog.py
content = content.replace(
    "cfg_roles = self.bot.bot_config.autorole.roles",
    "cfg_roles = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.roles"
)
content = content.replace(
    "if self.bot.bot_config.autorole.exclude_bots:",
    "if self.bot.bot_config.get_guild(str(member.guild.id)).autorole.exclude_bots:"
)
content = content.replace(
    "log_chan_id = self.bot.bot_config.autorole.log_channel_id",
    "log_chan_id = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.log_channel_id"
)
content = content.replace(
    "await asyncio.sleep(self.bot.bot_config.autorole.delay_seconds)",
    "await asyncio.sleep(self.bot.bot_config.get_guild(str(member.guild.id)).autorole.delay_seconds)"
)
content = content.replace(
    "if member.bot and self.bot.bot_config.autorole.exclude_bots:",
    "if member.bot and self.bot.bot_config.get_guild(str(member.guild.id)).autorole.exclude_bots:"
)
content = content.replace(
    "method = self.bot.bot_config.verification.method",
    "method = self.bot.bot_config.get_guild(str(member.guild.id)).verification.method"
)
content = content.replace(
    "cfg = self.bot.bot_config.autorole",
    "cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).autorole"
)

with open("cogs/autorole/cog.py", "w", encoding="utf-8") as f:
    f.write(content)

# cogs/events/cog.py
with open("cogs/events/cog.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "threshold = self.bot.bot_config.raid_protection.join_velocity_threshold",
    "threshold = self.bot.bot_config.get_guild(str(member.guild.id)).raid_protection.join_velocity_threshold"
)
content = content.replace(
    "account_age_hours = self.bot.bot_config.raid_protection.account_age_hours",
    "account_age_hours = self.bot.bot_config.get_guild(str(member.guild.id)).raid_protection.account_age_hours"
)
content = content.replace(
    "method = self.bot.bot_config.verification.method",
    "method = self.bot.bot_config.get_guild(str(member.guild.id)).verification.method"
)
content = content.replace(
    "unverified_role_id = self.bot.bot_config.verification.unverified_role_id",
    "unverified_role_id = self.bot.bot_config.get_guild(str(member.guild.id)).verification.unverified_role_id"
)
content = content.replace(
    "if unverified_role_id and (is_raid_lockdown or self.bot.bot_config.verification.method != \"none\"):",
    "if unverified_role_id and (is_raid_lockdown or self.bot.bot_config.get_guild(str(member.guild.id)).verification.method != \"none\"):"
)
content = content.replace(
    "welcome_cfg = self.bot.bot_config.welcome",
    "welcome_cfg = self.bot.bot_config.get_guild(str(member.guild.id)).welcome"
)

with open("cogs/events/cog.py", "w", encoding="utf-8") as f:
    f.write(content)

# cogs/utility/cog.py
with open("cogs/utility/cog.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "method = self.cog.bot.bot_config.verification.method",
    "method = self.cog.bot.bot_config.get_guild(str(interaction.guild.id)).verification.method"
)
content = content.replace(
    "cfg = self.bot.bot_config.verification",
    "cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification"
)
content = content.replace(
    "verified_role_id = self.bot.bot_config.verification.verified_role_id or self.bot.bot_config.permissions.admin_role_id # fallback",
    "verified_role_id = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification.verified_role_id or self.bot.bot_config.permissions.admin_role_id # fallback"
)
content = content.replace(
    "unverified_role_id = self.bot.bot_config.verification.unverified_role_id",
    "unverified_role_id = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification.unverified_role_id"
)
content = content.replace(
    "self.bot.bot_config.welcome.template = template_text",
    "self.bot.bot_config.get_guild(str(interaction.guild.id)).welcome.template = template_text"
)
content = content.replace(
    "cfg = self.bot.bot_config.welcome",
    "cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).welcome"
)
content = content.replace(
    "cfg = self.bot.bot_config.raid_protection",
    "cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).raid_protection"
)
content = content.replace(
    "self.bot.bot_config.raid_protection.enabled = enable",
    "self.bot.bot_config.get_guild(str(interaction.guild.id)).raid_protection.enabled = enable"
)

with open("cogs/utility/cog.py", "w", encoding="utf-8") as f:
    f.write(content)

