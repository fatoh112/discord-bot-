import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
import config_schema

class AutoRoleCog(commands.Cog):
    """Cog managing auto-role assignments, join queues, and admin configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.models = bot.models
        self.metrics = bot.metrics
        
        self.join_queue: asyncio.Queue[Tuple[str, str, int]] = asyncio.Queue()  # (guild_id, user_id, retry_count)
        self.guild_locks: Dict[str, asyncio.Lock] = {}
        
        # Start worker task
        self.worker_task = self.bot.loop.create_task(self._queue_worker())

    async def cog_unload(self) -> None:
        """Called when cog is unloaded. Saves pending queue to database."""
        self.worker_task.cancel()
        await self._save_queue_to_db()

    async def _save_queue_to_db(self) -> None:
        """Saves current memory queue items to the database for persistence."""
        logger.info("Saving active auto-role queue state to database...")
        items = []
        while not self.join_queue.empty():
            items.append(self.join_queue.get_nowait())

        # Save to verification_queue with status='pending'
        # Run ALTER TABLE to ensure status column is present if not already added
        try:
            await self.db.execute("ALTER TABLE verification_queue ADD COLUMN status TEXT DEFAULT 'pending';")
        except Exception:
            pass # Column already exists

        async with self.db.begin_transaction() as conn:
            for guild_id, user_id, retries in items:
                # Store retries / state in queue table
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO verification_queue (user_id, guild_id, joined_at, verified, method, status)
                    VALUES (?, ?, datetime('now'), 0, 'auto', 'pending')
                    """,
                    (user_id, guild_id)
                )

    async def _restore_queue_from_db(self) -> None:
        """Restores pending queue items from database verification_queue table."""
        try:
            await self.db.execute("ALTER TABLE verification_queue ADD COLUMN status TEXT DEFAULT 'pending';")
        except Exception:
            pass

        rows = await self.db.fetchall("SELECT user_id, guild_id FROM verification_queue WHERE verified = 0 AND status = 'pending'")
        count = 0
        for r in rows:
            await self.join_queue.put((r["guild_id"], r["user_id"], 0))
            count += 1
        logger.info(f"Restored {count} pending queue entries from database verification_queue.")

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Verifies if the user is administrator or whitelisted."""
        if interaction.user.id in self.bot.bot_config.admin_user_ids:
            return True
        return interaction.user.guild_permissions.administrator

    async def _get_guild_lock(self, guild_id: str) -> asyncio.Lock:
        """Retrieves or instantiates a lock per guild to prevent concurrent role conflicts."""
        if guild_id not in self.guild_locks:
            self.guild_locks[guild_id] = asyncio.Lock()
        return self.guild_locks[guild_id]

    async def _queue_worker(self) -> None:
        """Background loop continuously processing the asyncio join queue."""
        await self.bot.wait_until_ready()
        # Restore state on load
        await self._restore_queue_from_db()

        while True:
            try:
                # Wait for next item
                guild_id, user_id, retries = await self.join_queue.get()
                
                # Check batch processing: if queue has 10+ members, process in batches
                q_size = self.join_queue.qsize()
                batch_size = 5 if q_size >= 10 else 1
                
                batch = [(guild_id, user_id, retries)]
                for _ in range(batch_size - 1):
                    if not self.join_queue.empty():
                        batch.append(self.join_queue.get_nowait())

                # Process batch
                tasks = []
                for g_id, u_id, ret_count in batch:
                    lock = await self._get_guild_lock(g_id)
                    tasks.append(self._process_single_assignment(g_id, u_id, ret_count, lock))

                await asyncio.gather(*tasks)
                
                # Track queue metrics
                current_depth = self.join_queue.qsize()
                for g_id, _, _ in batch:
                    await self.metrics.set("queue_depth_current", g_id, current_depth)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-role queue worker loop: {e}")
                await asyncio.sleep(5)

    async def _process_single_assignment(self, guild_id: str, user_id: str, retries: int, lock: asyncio.Lock) -> None:
        """Handles a single member's role assignment with lock controls and retry logic."""
        async with lock:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return

            member = guild.get_member(int(user_id))
            if not member:
                # Member left mid-process, discard
                return

            # Fetch roles configuration
            role_configs = await self.models.get_autoroles(guild_id)
            if not role_configs:
                # Fallback to loading from memory config if DB has none yet
                cfg_roles = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.roles
                role_configs = [{"role_id": r.id, "priority": r.priority} for r in cfg_roles]

            # Priority sorting: verified members > unverified > bots (excluded)
            if member.bot:
                # Exclude if config excludes bots
                if self.bot.bot_config.get_guild(str(member.guild.id if 'member' in locals() else interaction.guild.id if 'interaction' in locals() else list(self.bot.guilds)[0].id)).autorole.exclude_bots:
                    return

            # Prioritize role list sorting
            role_configs.sort(key=lambda x: x["priority"])

            start_time = time.time()

            for r_cfg in role_configs:
                role_id = r_cfg["role_id"]
                role = guild.get_role(int(role_id))

                if not role:
                    # Role not found (deleted): remove from configs, notify admins
                    logger.warning(f"Role ID {role_id} no longer exists. Removing from configuration.")
                    await self.models.remove_autorole(guild_id, role_id)
                    
                    # Notify admin channel
                    log_chan_id = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.log_channel_id
                    if log_chan_id:
                        chan = guild.get_channel(int(log_chan_id))
                        if isinstance(chan, discord.TextChannel):
                            try:
                                await chan.send(f"⚠️ **Auto-Role Configuration Alert**: Role ID `{role_id}` was deleted from the server and has been removed from settings.")
                            except Exception:
                                pass
                    continue

                # Verify bot has permission to assign it
                if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
                    logger.error(f"Bot lacks role management permissions to assign role '{role.name}' in {guild.name}")
                    # Notify logs
                    await self.models.log_audit(
                        guild_id=guild_id,
                        admin_id=str(self.bot.user.id),
                        action="ROLE_ASSIGN_FAIL",
                        target_id=user_id,
                        reason="Lacking bot permission to assign role hierarchy",
                        ip_hash="SYSTEM"
                    )
                    continue

                # Rate limiting delay: 2s between assignments
                await asyncio.sleep(self.bot.bot_config.get_guild(str(member.guild.id)).autorole.delay_seconds)

                try:
                    await member.add_roles(role, reason="Auto-Role Cog system assignment")
                    await self.models.log_audit(
                        guild_id=guild_id,
                        admin_id=str(self.bot.user.id),
                        action="ROLE_ASSIGN_SUCCESS",
                        target_id=user_id,
                        reason=f"Assigned role: {role.name}",
                        ip_hash="SYSTEM"
                    )
                    await self.metrics.increment("roles_assigned_total", guild_id)
                    
                    # Log wait times
                    duration = time.time() - start_time
                    await self.metrics.set("avg_assignment_time_seconds", guild_id, duration)

                except discord.Forbidden:
                    logger.error(f"Forbidden error trying to assign role '{role.name}' to user {member.name}")
                    await self.metrics.increment("role_assignments_failed", guild_id)
                    # Notify admin log channel
                    log_chan_id = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.log_channel_id
                    if log_chan_id:
                        chan = guild.get_channel(int(log_chan_id))
                        if isinstance(chan, discord.TextChannel):
                            try:
                                await chan.send(f"❌ **Auto-Role Assignment Error**: Lacking permissions to assign <@&{role_id}> to <@{user_id}>.")
                            except Exception:
                                pass

                except discord.HTTPException as e:
                    # Retry with exponential backoff: 5s, 10s, 20s delays
                    if retries < 3:
                        backoff = 5 * (2 ** retries) # 5s, 10s, 20s
                        logger.warning(f"HTTPException encountered. Retrying role assignment in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        await self.join_queue.put((guild_id, user_id, retries + 1))
                    else:
                        # Dead letter queue: fail and store
                        logger.error(f"Failed to assign role {role.name} to {member.name} after 3 retries.")
                        await self.metrics.increment("role_assignments_failed", guild_id)
                        await self.db.execute(
                            """
                            UPDATE verification_queue
                            SET status = 'failed'
                            WHERE user_id = ? AND guild_id = ?
                            """,
                            (user_id, guild_id)
                        )
                    return

            # Mark verification queue item completed if no retries remain
            await self.db.execute(
                """
                UPDATE verification_queue
                SET status = 'completed', verified = 1
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id)
            )

    # --- Event Listeners ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Listens for guild joins, enqueues roles, and logs parameters."""
        if member.bot and self.bot.bot_config.get_guild(str(member.guild.id if 'member' in locals() else interaction.guild.id if 'interaction' in locals() else list(self.bot.guilds)[0].id)).autorole.exclude_bots:
            return

        guild_id = str(member.guild.id)
        user_id = str(member.id)

        # Log join
        await self.models.log_audit(
            guild_id=guild_id,
            admin_id=str(self.bot.user.id),
            action="MEMBER_JOIN",
            target_id=user_id,
            reason="User joined the server",
            ip_hash="SYSTEM"
        )
        await self.metrics.increment("member_joins_24h", guild_id)

        # Add to verification_queue DB
        method = self.bot.bot_config.get_guild(str(member.guild.id)).verification.method
        await self.models.add_to_verification(user_id, guild_id, method)

        # Enqueue in join queue
        await self.join_queue.put((guild_id, user_id, 0))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Triggered when role gets deleted, cleaning entries and alert admins."""
        guild_id = str(role.guild.id)
        role_id = str(role.id)

        # Check if in autorole configs
        roles = await self.models.get_autoroles(guild_id)
        if any(r["role_id"] == role_id for r in roles):
            await self.models.remove_autorole(guild_id, role_id)
            
            # Notify admins
            log_chan_id = self.bot.bot_config.get_guild(str(member.guild.id)).autorole.log_channel_id
            if log_chan_id:
                chan = role.guild.get_channel(int(log_chan_id))
                if isinstance(chan, discord.TextChannel):
                    try:
                        await chan.send(f"🚨 **Auto-Role Configuration Alert**: Role ID `{role_id}` was deleted from the server and has been removed from configurations.")
                    except Exception:
                        pass

    # --- Slash Commands ---
    autorole = app_commands.Group(name="autorole", description="Auto-role configuration commands")

    @autorole.command(name="view", description="Display current auto-role configuration settings")
    async def config_view(self, interaction: discord.Interaction) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        roles = await self.models.get_autoroles(guild_id)
        
        lines = []
        for r in roles:
            lines.append(f"• <@&{r['role_id']}> | Priority: `{r['priority']}`")

        roles_str = "\n".join(lines) if lines else "None configured."

        cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).autorole
        embed = discord.Embed(
            title="Auto-Role System Configurations",
            color=discord.Color.indigo()
        )
        embed.add_field(name="Auto-Role Enabled", value=str(cfg.enabled), inline=True)
        embed.add_field(name="Exclude Bots", value=str(cfg.exclude_bots), inline=True)
        embed.add_field(name="Delay Seconds", value=f"{cfg.delay_seconds}s", inline=True)
        embed.add_field(name="Assigned Roles", value=roles_str, inline=False)

        await interaction.response.send_message(embed=embed)

    @autorole.command(name="add", description="Add role to the auto-assignment sequence")
    @app_commands.describe(role="Role to auto-assign", priority="Assignment priority (lower number = assigned first)")
    async def config_add(self, interaction: discord.Interaction, role: discord.Role, priority: int = 1) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        # Validate Bot position hierarchy
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Cannot add a role that is higher or equal to the bot's highest role.", ephemeral=True)
            return

        await self.models.add_autorole(guild_id, str(role.id), priority)
        await self.models.log_audit(
            guild_id=guild_id,
            admin_id=str(interaction.user.id),
            action="AUTOROLE_ADD",
            target_id=str(role.id),
            reason=f"Added role to auto-assignment sequence (Priority: {priority})",
            ip_hash="SYSTEM"
        )

        await interaction.response.send_message(f"✅ Added <@&{role.id}> to auto-role configuration with priority {priority}.")

    @autorole.command(name="remove", description="Remove role from the auto-assignment sequence")
    @app_commands.describe(role="Role to remove")
    async def config_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        removed = await self.models.remove_autorole(guild_id, str(role.id))

        if removed > 0:
            await self.models.log_audit(
                guild_id=guild_id,
                admin_id=str(interaction.user.id),
                action="AUTOROLE_REMOVE",
                target_id=str(role.id),
                reason="Removed role from auto-assignment sequence",
                ip_hash="SYSTEM"
            )
            await interaction.response.send_message(f"✅ Removed <@&{role.id}> from auto-role configuration.")
        else:
            await interaction.response.send_message(f"❌ Role <@&{role.id}> was not configured in auto-role configurations.", ephemeral=True)

    @autorole.command(name="test", description="Simulate role assignment for a user without modifying roles")
    @app_commands.describe(user="The target user to simulate on")
    async def simulate_test(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        roles = await self.models.get_autoroles(guild_id)
        
        if not roles:
            await interaction.response.send_message("❌ No auto-roles are currently configured.", ephemeral=True)
            return

        roles.sort(key=lambda x: x["priority"])
        lines = []
        for r in roles:
            lines.append(f"• <@&{r['role_id']}> (Priority: `{r['priority']}`)")

        await interaction.response.send_message(
            f"ℹ️ **Auto-Role Simulation Preview for <@{user.id}>**:\n"
            f"Would attempt to assign the following {len(roles)} role(s) in order:\n" + "\n".join(lines)
        )

    @autorole.command(name="mass-assign", description="Assign auto-roles to all existing unverified members")
    @app_commands.describe(confirm="Select True to confirm mass modification")
    async def mass_assign(self, interaction: discord.Interaction, confirm: bool) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message("❌ Operation aborted. Please select confirm=True to authorize.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        roles = await self.models.get_autoroles(guild_id)
        if not roles:
            await interaction.response.send_message("❌ No auto-roles are currently configured.", ephemeral=True)
            return

        # Defer and run background task for mass assignment to keep command snappy
        await interaction.response.defer()
        
        # Pull members who don't have the highest priority role
        target_members = [
            m for m in interaction.guild.members 
            if not m.bot and not any(str(r.id) == roles[0]["role_id"] for r in m.roles)
        ]

        if not target_members:
            await interaction.followup.send("ℹ️ No unassigned members were found matching criteria.")
            return

        await interaction.followup.send(f"⌛ Starting mass assignment for {len(target_members)} members. (Throttled: 5 members / 10s)...")
        
        # Run throttled loop
        count = 0
        for m in target_members:
            for r_cfg in roles:
                await self.join_queue.put((guild_id, str(m.id), 0))
            count += 1
            if count % 5 == 0:
                await asyncio.sleep(10) # 5 members per 10 seconds limit

        logger.info(f"Mass assignment enqueued for {count} members.")

    @autorole.command(name="stats", description="Access queue depth and error performance metrics")
    async def stats(self, interaction: discord.Interaction) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied. Administrative clearance required.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        g_metrics = await self.metrics.get_all(guild_id)

        embed = discord.Embed(
            title="Auto-Role System Performance Metrics",
            color=discord.Color.indigo()
        )
        embed.add_field(name="Roles Assigned (Total)", value=str(g_metrics.get("roles_assigned_total", 0)), inline=True)
        embed.add_field(name="Role Failures (Total)", value=str(g_metrics.get("role_assignments_failed", 0)), inline=True)
        embed.add_field(name="Uptime Joins (24h)", value=str(g_metrics.get("member_joins_24h", 0)), inline=True)
        embed.add_field(name="Last Wait Duration (Sec)", value=f"{g_metrics.get('avg_assignment_time_seconds', 0.0):.2f}s", inline=True)
        embed.add_field(name="Current Queue Depth", value=str(g_metrics.get("queue_depth_current", 0)), inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoleCog(bot))
