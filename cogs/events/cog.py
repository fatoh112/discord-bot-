import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger
import config_schema

class EventsCog(commands.Cog):
    """Cog handling all global Discord gateway event listeners and integration triggers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.models = bot.models
        self.metrics = bot.metrics

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Fires when a new member joins. Handles anti-raid logs, verification checks, and triggers welcomes."""
        guild = member.guild
        guild_id = str(guild.id)
        user_id = str(member.id)

        # 1. Audit Log & Metrics
        await self.models.log_audit(
            guild_id=guild_id,
            admin_id=str(self.bot.user.id),
            action="MEMBER_JOIN",
            target_id=user_id,
            reason=f"User {member} joined the server.",
            ip_hash="SYSTEM"
        )
        await self.metrics.increment("member_joins_24h", guild_id)

        # 2. Raid-Velocity Check & Age Check
        utility_cog = self.bot.get_cog("UtilityCog")
        is_raid_lockdown = False
        if utility_cog:
            now = time.time()
            utility_cog.join_history.append(now)
            # Filter history to last 60 seconds
            utility_cog.join_history = [t for t in utility_cog.join_history if now - t < 60]

            threshold = self.bot.bot_config.raid_protection.join_velocity_threshold
            if len(utility_cog.join_history) > threshold:
                if not utility_cog.lockdown_active:
                    utility_cog.lockdown_active = True
                    logger.warning(f"Raid detected in {guild.name}! Activating lockdown mode.")
                    await self.models.log_audit(
                        guild_id=guild_id,
                        admin_id=str(self.bot.user.id),
                        action="RAID_LOCKDOWN_ON",
                        target_id="SYSTEM",
                        reason=f"Join velocity {len(utility_cog.join_history)} exceeded threshold of {threshold}/min.",
                        ip_hash="SYSTEM"
                    )
            
            is_raid_lockdown = utility_cog.lockdown_active

            # Account Age Check
            account_age_hours = self.bot.bot_config.raid_protection.account_age_hours
            if account_age_hours > 0:
                age_seconds = (discord.utils.utcnow() - member.created_at).total_seconds()
                if age_seconds < (account_age_hours * 3600):
                    try:
                        await member.kick(reason=f"Anti-Raid: Account age ({age_seconds / 3600:.1f}h) less than required {account_age_hours}h.")
                        logger.warning(f"Kicked {member} (ID: {member.id}) due to account age filter.")
                        await self.models.log_audit(
                            guild_id=guild_id,
                            admin_id=str(self.bot.user.id),
                            action="ANTI_RAID_KICK",
                            target_id=user_id,
                            reason=f"Account age is too low ({age_seconds / 3600:.1f} hours).",
                            ip_hash="SYSTEM"
                        )
                        return
                    except Exception as e:
                        logger.error(f"Failed to kick underage user {member}: {e}")

        # 3. Add to Verification Queue DB
        method = self.bot.bot_config.verification.method
        await self.models.add_to_verification(user_id, guild_id, method)

        # 4. If in lockdown, pause auto-roles, require manual verification.
        # Otherwise, if verification is disabled or simple button is skipped:
        # Wait, if verification unverified_role_id is set, assign it.
        unverified_role_id = self.bot.bot_config.verification.unverified_role_id
        if unverified_role_id and (is_raid_lockdown or self.bot.bot_config.verification.method != "none"):
            unverified_role = guild.get_role(int(unverified_role_id))
            if unverified_role:
                try:
                    await member.add_roles(unverified_role, reason="Assigned unverified role on join.")
                except Exception as e:
                    logger.error(f"Failed to assign unverified role to {member}: {e}")
        else:
            # No verification role required, directly enqueue for auto-role
            autorole_cog = self.bot.get_cog("AutoRoleCog")
            if autorole_cog and not is_raid_lockdown:
                await autorole_cog.join_queue.put((guild_id, user_id, 0))

        # 5. Send Welcome message
        welcome_cfg = self.bot.bot_config.welcome
        if welcome_cfg.enabled and welcome_cfg.channel_id:
            welcome_channel = guild.get_channel(int(welcome_cfg.channel_id))
            if welcome_channel:
                desc = welcome_cfg.template.format(
                    user=f"<@{member.id}>",
                    server=guild.name,
                    member_count=str(guild.member_count),
                    created_at=member.created_at.strftime("%Y-%m-%d")
                )
                embed = discord.Embed(
                    title=f"Welcome to {guild.name}!",
                    description=desc,
                    color=discord.Color.indigo()
                )
                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)

                view = None
                if utility_cog and welcome_cfg.enable_verification_button:
                    from cogs.utility.cog import VerificationButtonView
                    view = VerificationButtonView(utility_cog)

                try:
                    await welcome_channel.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Failed to send welcome message: {e}")

        # 6. Optional Welcome DM
        if welcome_cfg.send_dm:
            try:
                desc_dm = welcome_cfg.template.format(
                    user=member.name,
                    server=guild.name,
                    member_count=str(guild.member_count),
                    created_at=member.created_at.strftime("%Y-%m-%d")
                )
                await member.send(f"Welcome to **{guild.name}**!\n{desc_dm}")
            except discord.Forbidden:
                # Respect DM privacy settings
                pass
            except Exception as e:
                logger.error(f"Failed to send welcome DM to {member}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Triggered when a member leaves. Cleans up pending verification records and logs departure."""
        guild_id = str(member.guild.id)
        user_id = str(member.id)

        await self.models.log_audit(
            guild_id=guild_id,
            admin_id=str(self.bot.user.id),
            action="MEMBER_REMOVE",
            target_id=user_id,
            reason=f"User {member} left the server.",
            ip_hash="SYSTEM"
        )

        # Cleanup verification queue
        await self.db.execute(
            "DELETE FROM verification_queue WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Triggered when a role is deleted. Cleans up auto-role configuration references."""
        guild_id = str(role.guild.id)
        role_id = str(role.id)

        # Check if in autorole configs
        roles = await self.models.get_autoroles(guild_id)
        if any(r["role_id"] == role_id for r in roles):
            await self.models.remove_autorole(guild_id, role_id)
            logger.info(f"Cleaned up deleted role {role.name} ({role_id}) from auto-role configs.")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Triggered when a channel is deleted. Updates welcome channel references if applicable."""
        welcome_cfg = self.bot.bot_config.welcome
        if welcome_cfg.channel_id == str(channel.id):
            welcome_cfg.channel_id = ""
            config_schema.save_config(self.bot.bot_config)
            logger.info("Cleared welcome channel reference as the channel was deleted.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Raw listener to handle reaction role assignments when message is not cached."""
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        emoji_str = str(payload.emoji)
        rows = await self.db.fetchall(
            "SELECT role_id, exclusive_group FROM reaction_roles WHERE message_id = ? AND emoji = ?",
            (str(payload.message_id), emoji_str)
        )

        if not rows:
            return

        for row in rows:
            role_id = row["role_id"]
            exclusive_group = row["exclusive_group"]

            role = guild.get_role(int(role_id))
            if not role:
                continue

            try:
                # Handle exclusive groups
                if exclusive_group:
                    other_rows = await self.db.fetchall(
                        "SELECT role_id FROM reaction_roles WHERE exclusive_group = ?",
                        (exclusive_group,)
                    )
                    other_role_ids = [r["role_id"] for r in other_rows if r["role_id"] != role_id]
                    for other_id in other_role_ids:
                        other_role = guild.get_role(int(other_id))
                        if other_role and other_role in member.roles:
                            await member.remove_roles(other_role, reason=f"Mutually exclusive group: {exclusive_group}")

                if role not in member.roles:
                    await member.add_roles(role, reason="Reaction Role toggle")
                    await self.models.record_user_reaction(str(payload.user_id), str(payload.message_id), role_id)
                    logger.info(f"Reaction Role: Granted role {role.name} to {member} via reaction.")
            except discord.Forbidden:
                logger.error(f"Lacking permission to assign reaction role {role.name} to {member}.")
            except Exception as e:
                logger.error(f"Error handling raw reaction role add: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Raw listener to handle reaction role removals when message is not cached."""
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        emoji_str = str(payload.emoji)
        rows = await self.db.fetchall(
            "SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?",
            (str(payload.message_id), emoji_str)
        )

        if not rows:
            return

        for row in rows:
            role_id = row["role_id"]
            role = guild.get_role(int(role_id))
            if not role:
                continue

            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Reaction Role toggle")
                    await self.models.remove_user_reaction(str(payload.user_id), str(payload.message_id), role_id)
                    logger.info(f"Reaction Role: Removed role {role.name} from {member} via reaction.")
            except discord.Forbidden:
                logger.error(f"Lacking permission to remove reaction role {role.name} from {member}.")
            except Exception as e:
                logger.error(f"Error handling raw reaction role remove: {e}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Gracefully catches errors, logs issues, and dispatches user notifications."""
        if isinstance(error, commands.CommandNotFound):
            return

        # Check for slash commands/app command errors vs prefix command errors
        guild_id = str(ctx.guild.id) if ctx.guild else "DM"
        logger.error(f"Command Error in {ctx.command}: {error}")

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You do not have the required permissions to run this command.", delete_after=10)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Command is on cooldown. Try again in {error.retry_after:.1f}s.", delete_after=10)
        else:
            await ctx.send(f"❌ An error occurred while executing the command: {error}", delete_after=15)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
