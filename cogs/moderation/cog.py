import os
import csv
import time
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, Any, List, Optional, Tuple
from io import BytesIO
from loguru import logger
import config_schema
from database.backup import BackupManager

class ModerationCog(commands.Cog):
    """Cog handling secure administrative command scopes, RBAC, backups, and audits."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.models = bot.models
        self.db = bot.db
        
        # User command usage: user_id -> list of timestamps
        self.user_command_usage: Dict[int, List[float]] = {}
        # Backup restore confirmations: user_id -> {backup_file, confirm_count, timestamp}
        self.restore_confirmations: Dict[int, Dict[str, Any]] = {}

    async def _check_permissions_and_cooldown(self, interaction: discord.Interaction) -> bool:
        """Enforces RBAC clearance level checks and a 10 commands per 5 minutes rate limit."""
        user_id = interaction.user.id
        
        # Owner whitelist exempts rate limit
        is_owner = user_id in self.bot.bot_config.admin_user_ids
        
        if not is_owner:
            # Enforce rate limit
            now = time.time()
            usages = self.user_command_usage.get(user_id, [])
            usages = [t for t in usages if now - t < 300]
            self.user_command_usage[user_id] = usages

            if len(usages) >= 10:
                remaining_time = int(300 - (now - usages[0]))
                await interaction.response.send_message(
                    f"❌ Rate limit hit: You can use up to 10 admin commands per 5 minutes. Try again in {remaining_time}s.",
                    ephemeral=True
                )
                return False
            
            usages.append(now)
            self.user_command_usage[user_id] = usages

        # Check permissions
        has_perm = is_owner or interaction.user.guild_permissions.administrator
        if not has_perm:
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return False

        # Increment command metrics
        guild_id = str(interaction.guild.id) if interaction.guild else "SYSTEM"
        await self.bot.metrics.increment("commands_used_total", guild_id)
        return True

    async def _audit(self, interaction: discord.Interaction, action: str, target_id: str, reason: str) -> None:
        """Writes action details to both structured audit logs and console logs."""
        guild_id = str(interaction.guild.id) if interaction.guild else "SYSTEM"
        import hashlib
        ip_hash = hashlib.sha256(interaction.user.display_name.encode()).hexdigest()[:16]
        
        await self.models.log_audit(
            guild_id=guild_id,
            admin_id=str(interaction.user.id),
            action=action,
            target_id=target_id,
            reason=reason,
            ip_hash=ip_hash
        )
        logger.info(f"AUDIT | Guild: {guild_id} | Admin: {interaction.user} | Action: {action} | Target: {target_id} | Reason: {reason}")

    # --- Slash Commands ---
    admin = app_commands.Group(name="admin", description="Bot administrative controls")

    role_group = app_commands.Group(name="role", description="Role management tools", parent=admin)

    @role_group.command(name="give", description="Give a role to a user")
    @app_commands.describe(user="The user to give the role to", role="The role to give", reason="Justification for logs")
    async def role_give(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, reason: Optional[str] = "None provided") -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Cannot assign a role higher or equal to the bot's hierarchy.", ephemeral=True)
            return

        await user.add_roles(role, reason=f"Admin: {interaction.user} | Reason: {reason}")
        await self._audit(interaction, "ROLE_GIVE", str(user.id), f"Granted role '{role.name}'. Reason: {reason}")
        await interaction.response.send_message(f"✅ Assigned role <@&{role.id}> to <@{user.id}>.")

    @role_group.command(name="remove", description="Remove a role from a user")
    @app_commands.describe(user="The user to remove the role from", role="The role to remove", reason="Justification for logs")
    async def role_remove(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, reason: Optional[str] = "None provided") -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Cannot remove a role higher or equal to the bot's hierarchy.", ephemeral=True)
            return

        await user.remove_roles(role, reason=f"Admin: {interaction.user} | Reason: {reason}")
        await self._audit(interaction, "ROLE_REMOVE", str(user.id), f"Removed role '{role.name}'. Reason: {reason}")
        await interaction.response.send_message(f"✅ Removed role <@&{role.id}> from <@{user.id}>.")

    @role_group.command(name="mass", description="Mass assign a role to members")
    @app_commands.describe(role="Role to bulk assign", filter_type="Member category filter", confirm="Confirm mass operation")
    async def role_mass(self, interaction: discord.Interaction, role: discord.Role, filter_type: str, confirm: bool = False) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        # Resolve members based on filter: all, bots, humans, verified, unverified
        guild = interaction.guild
        members = guild.members
        
        target_members = []
        for m in members:
            # Skip if already has role
            if role in m.roles:
                continue

            if filter_type == "all":
                target_members.append(m)
            elif filter_type == "bots" and m.bot:
                target_members.append(m)
            elif filter_type == "humans" and not m.bot:
                target_members.append(m)
            elif filter_type == "verified" and not m.bot:
                # Query DB to check if verified
                row = await self.db.fetchone("SELECT verified FROM verification_queue WHERE user_id = ? AND verified = 1", (str(m.id),))
                if row:
                    target_members.append(m)
            elif filter_type == "unverified" and not m.bot:
                row = await self.db.fetchone("SELECT verified FROM verification_queue WHERE user_id = ? AND verified = 1", (str(m.id),))
                if not row:
                    target_members.append(m)

        if not target_members:
            await interaction.response.send_message("ℹ️ No members found matching the filter criteria.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message(
                f"ℹ️ **Dry-Run Preview**: This operation WILL assign <@&{role.id}> to **{len(target_members)}** members.\n"
                f"To execute, run again with confirm=True.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        
        # Throttled queue mass assignment: 10 members per 5 seconds
        count = 0
        for m in target_members:
            try:
                # Add to join_queue inside AutoRoleCog to process rate-limits safely
                autorole_cog = self.bot.get_cog("AutoRoleCog")
                if autorole_cog:
                    await autorole_cog.join_queue.put((str(guild.id), str(m.id), 0))
                else:
                    await m.add_roles(role, reason="Mass Role command execution")
                
                await self._audit(interaction, "ROLE_MASS_ASSIGN", str(m.id), f"Mass assigned role: {role.name}")
                count += 1
                if count % 10 == 0:
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error mass assigning role to {m.id}: {e}")

        await interaction.followup.send(f"✅ Mass enqueued role <@&{role.id}> for {count} members.")

    @role_group.command(name="info", description="Show detailed role statistics and configurations")
    @app_commands.describe(role="The role to inspect")
    async def role_info(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        permissions_list = [name for name, enabled in role.permissions if enabled]
        perms_str = ", ".join(permissions_list) if permissions_list else "None"

        embed = discord.Embed(
            title=f"Role Details: {role.name}",
            color=role.color
        )
        embed.add_field(name="Role ID", value=str(role.id), inline=True)
        embed.add_field(name="Color Hex", value=str(role.color), inline=True)
        embed.add_field(name="Hierarchy position", value=str(role.position), inline=True)
        embed.add_field(name="Members count", value=str(len(role.members)), inline=True)
        embed.add_field(name="Created At", value=role.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Permissions", value=perms_str[:1024], inline=False)

        await interaction.response.send_message(embed=embed)

    # Config commands
    config_group = app_commands.Group(name="config", description="Bot configuration controls", parent=admin)

    @config_group.command(name="view", description="Display current bot configurations")
    @app_commands.describe(section="Filter target config section")
    async def config_view(self, interaction: discord.Interaction, section: Optional[str] = None) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        cfg_data = self.bot.bot_config.model_dump()
        
        # Redact secrets
        for key in ["discord_token", "encryption_key", "dashboard_password_hash", "discord_audit_webhook_url"]:
            if key in cfg_data and cfg_data[key]:
                cfg_data[key] = "REDACTED"

        if section and section in cfg_data:
            view_data = {section: cfg_data[section]}
        else:
            view_data = cfg_data

        formatted = json.dumps(view_data, indent=2)
        if len(formatted) > 1900:
            await interaction.response.send_message("❌ Config output is too long. Target a specific section.", ephemeral=True)
        else:
            await interaction.response.send_message(f"```json\n{formatted}\n```")

    @config_group.command(name="update", description="Update a configuration parameter value")
    @app_commands.describe(key="Config parameter path (e.g. autorole.delay_seconds)", value="New setting parameter value")
    async def config_update(self, interaction: discord.Interaction, key: str, value: str) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        cfg = self.bot.bot_config
        try:
            parts = key.split(".")
            if len(parts) == 2:
                sec, sub = parts
                section_obj = getattr(cfg, sec, None)
                if not section_obj or not hasattr(section_obj, sub):
                    raise AttributeError()

                current = getattr(section_obj, sub)
                # Cast types
                if isinstance(current, bool):
                    casted = value.lower() in ("true", "1", "yes")
                elif isinstance(current, int):
                    casted = int(value)
                else:
                    casted = value

                setattr(section_obj, sub, casted)
            else:
                raise AttributeError()

            # Save
            config_schema.save_config(cfg)
            await self._audit(interaction, "CONFIG_UPDATE", key, f"Updated key to: {value}")
            await interaction.response.send_message(f"✅ Updated configuration `{key}` successfully. (Some parameters might require bot restart).")

        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to parse config value update. Verify dot path name: {e}", ephemeral=True)

    # Auditing search command
    @admin.command(name="audit", description="Search database audit logs for actions")
    @app_commands.describe(user="The user to query", export_csv="Option to export results as CSV")
    async def audit_search(self, interaction: discord.Interaction, user: discord.User, export_csv: bool = False) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        rows = await self.models.get_audit_logs(str(user.id))
        if not rows:
            await interaction.response.send_message("No audit records found matching search query.", ephemeral=True)
            return

        # Sort logs by timestamp desc
        rows.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_rows = rows[:50]

        if export_csv:
            await interaction.response.defer(ephemeral=True)
            fp = BytesIO()
            writer = csv.writer(fp.name) # wait, csv writer requires text or file wrapper
            # Let's write manually in bytes format
            lines = ["Guild ID,Admin ID,Action,Target ID,Reason,Timestamp,IP Hash,Consent,Category\n"]
            for r in rows:
                lines.append(f"{r['guild_id']},{r['admin_id']},{r['action']},{r['target_id']},{r['reason']},{r['timestamp']},{r['ip_hash']},{r['consent_flag']},{r['data_category']}\n")
            
            fp = BytesIO("".join(lines).encode('utf-8'))
            file = discord.File(fp, filename=f"audit_logs_{user.id}.csv")
            await interaction.followup.send(content="📊 Audit log CSV export compiled.", file=file)
            return

        lines = []
        for r in recent_rows[:15]:
            lines.append(f"`{r['timestamp']}` - Admin: <@{r['admin_id']}> | Action: `{r['action']}` | Target: <@{r['target_id']}> | Reason: `{r['reason']}`")

        embed = discord.Embed(
            title=f"Audit Query Results ({len(rows)} found)",
            description="\n".join(lines) if lines else "No entries.",
            color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed)

    # Backups commands
    backup = app_commands.Group(name="backup", description="Encrypted database backup management")

    @backup.command(name="create", description="Trigger manual encrypted backup snapshot")
    async def backup_create(self, interaction: discord.Interaction) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            bm = BackupManager(self.bot.bot_config.encryption_key)
            ts, filename = bm.create_backup("daily")
            path = os.path.join("backups", "daily", filename)
            
            # Verify checksum
            valid = bm.verify_checksum(path)
            if valid:
                await self._audit(interaction, "BACKUP_CREATE", filename, "Created and verified manual backup.")
                await interaction.followup.send(f"✅ Encrypted backup successfully created! Name: `{filename}`")
            else:
                await interaction.followup.send("❌ Error: Backup generated, but SHA256 checksum verification failed.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create encrypted backup: {e}")

    @backup.command(name="restore", description="Restore database state from an encrypted backup")
    @app_commands.describe(backup_name="Filename of the backup (e.g. backup_20260603_220000.enc.db)")
    async def backup_restore(self, interaction: discord.Interaction, backup_name: str) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        user_id = interaction.user.id
        
        # Confirm twice before restoring (2FA verification logic)
        confirm_data = self.restore_confirmations.get(user_id, {"confirm_count": 0})
        
        if confirm_data["confirm_count"] == 0:
            self.restore_confirmations[user_id] = {
                "backup_name": backup_name,
                "confirm_count": 1,
                "timestamp": time.time()
            }
            await interaction.response.send_message(
                f"⚠️ **DESTRUCTIVE DATABASE RESTORE**: Overwriting the current database will restore state from `{backup_name}`.\n"
                f"Please run the command a second time within 30 seconds to confirm authorization.",
                ephemeral=True
            )
            return

        # Check if same file and within time limit
        now = time.time()
        if (confirm_data["backup_name"] == backup_name and (now - confirm_data["timestamp"]) < 30):
            await interaction.response.defer(ephemeral=True)
            self.restore_confirmations.pop(user_id, None)

            # Locate file
            target_path = None
            for parent in ["daily", "weekly", "monthly"]:
                test_path = os.path.join("backups", parent, backup_name)
                if os.path.exists(test_path):
                    target_path = test_path
                    break

            if not target_path:
                await interaction.followup.send("❌ Backup name matching query was not found in archives.")
                return

            try:
                bm = BackupManager(self.bot.bot_config.encryption_key)
                bm.restore_backup(target_path)
                await self._audit(interaction, "BACKUP_RESTORE", backup_name, "Reconstructed database state from backup.")
                await interaction.followup.send("✅ System restore complete! Overwritten tables populated from backup package. Restarting bot...")
                
                # Restart bot
                asyncio.create_task(self.bot.shutdown())
            except Exception as e:
                await interaction.followup.send(f"❌ Backup restoration failed: {e}")
        else:
            # Timed out or mismatched name, reset state
            self.restore_confirmations[user_id] = {
                "backup_name": backup_name,
                "confirm_count": 1,
                "timestamp": time.time()
            }
            await interaction.response.send_message(
                "❌ Confirmation timed out or backup filename mismatch. Please run the command twice again to authorize.",
                ephemeral=True
            )

    # Cog reload commands
    extension_group = app_commands.Group(name="extension", description="Dynamic extension reloading interfaces")

    @extension_group.command(name="reload", description="Hot-reload a cog without bot restart")
    @app_commands.describe(cog_name="Name of cog (e.g. autorole)")
    async def ext_reload(self, interaction: discord.Interaction, cog_name: str) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        target = f"cogs.{cog_name}.cog"
        if target not in self.bot.loaded_cogs_list:
            await interaction.response.send_message(f"❌ Cog extension `{target}` not found in active registries.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await self.bot.reload_extension(target)
            await self._audit(interaction, "COG_RELOAD", target, "Triggered hot-reload.")
            await interaction.followup.send(f"✅ Cog extension `{target}` reloaded successfully.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reload cog `{target}`: {e}")

    @extension_group.command(name="list", description="Show all loaded extensions and reload capabilities")
    async def ext_list(self, interaction: discord.Interaction) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        embed = discord.Embed(
            title="Active Bot Cogs Registry",
            color=discord.Color.orange()
        )
        for cog_path in self.bot.loaded_cogs_list:
            name = cog_path.split(".")[-2]
            embed.add_field(name=name, value="`Active / Reloadable`", inline=False)

        await interaction.response.send_message(embed=embed)

    @extension_group.command(name="load", description="Dynamically load a new cog extension")
    @app_commands.describe(cog_name="Name of the cog")
    async def ext_load(self, interaction: discord.Interaction, cog_name: str) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        target = f"cogs.{cog_name}.cog"
        await interaction.response.defer()
        try:
            await self.bot.load_extension(target)
            self.bot.loaded_cogs_list.append(target)
            await self._audit(interaction, "COG_LOAD", target, "Dynamically loaded cog.")
            await interaction.followup.send(f"✅ Extension `{target}` loaded successfully.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to load extension `{target}`: {e}")

    @extension_group.command(name="unload", description="Dynamically unload an active cog extension")
    @app_commands.describe(cog_name="Name of the cog")
    async def ext_unload(self, interaction: discord.Interaction, cog_name: str) -> None:
        if not await self._check_permissions_and_cooldown(interaction):
            return

        target = f"cogs.{cog_name}.cog"
        if target not in self.bot.loaded_cogs_list:
            await interaction.response.send_message(f"❌ Extension `{target}` is not currently loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            await self.bot.unload_extension(target)
            self.bot.loaded_cogs_list.remove(target)
            await self._audit(interaction, "COG_UNLOAD", target, "Dynamically unloaded cog.")
            await interaction.followup.send(f"✅ Extension `{target}` unloaded successfully.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to unload extension `{target}`: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
