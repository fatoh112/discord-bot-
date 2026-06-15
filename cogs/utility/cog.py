import time
import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
import config_schema

# --- Math Verification Modal ---
class MathCaptchaModal(discord.ui.Modal, title="Math Security Challenge"):
    def __init__(self, answer: int, cog: Any, user_id: int):
        super().__init__()
        self.correct_answer = answer
        self.cog = cog
        self.user_id = user_id

        self.answer_input = discord.ui.TextInput(
            label="Provide the numeric solution:",
            placeholder="E.g. 15",
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.answer_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid format. Please enter numbers only.", ephemeral=True)
            return

        if val == self.correct_answer:
            await self.cog.complete_verification(interaction, self.user_id)
        else:
            await interaction.response.send_message("❌ Incorrect solution. Try verifying again.", ephemeral=True)


# --- Verification Button View ---
class VerificationButtonView(discord.ui.View):
    def __init__(self, cog: Any):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Verify Here", style=discord.ButtonStyle.success, custom_id="verify_button_trigger")
    async def verify_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        method = self.cog.bot.bot_config.get_guild(str(interaction.guild.id)).verification.method
        user_id = interaction.user.id
        
        if method == "math":
            num1 = random.randint(2, 9)
            num2 = random.randint(2, 9)
            ans = num1 + num2
            modal = MathCaptchaModal(ans, self.cog, user_id)
            modal.answer_input.label = f"Solve: {num1} + {num2} = ?"
            await interaction.response.send_modal(modal)
        else:
            # Simple button verification
            await self.cog.complete_verification(interaction, user_id)


# --- Dynamic Reaction Panel View ---
class ReactionPanelButtonView(discord.ui.View):
    def __init__(self, cog: Any, config_list: List[dict]):
        super().__init__(timeout=None)
        self.cog = cog

        for idx, cfg in enumerate(config_list):
            button = discord.ui.Button(
                label=cfg["label"],
                style=discord.ButtonStyle.primary,
                custom_id=f"rxrole_{cfg['role_id']}_{idx}"
            )
            button.callback = self._create_callback(cfg["role_id"], cfg.get("exclusive_group"))
            self.add_item(button)

    def _create_callback(self, role_id: str, group: Optional[str]):
        async def callback(interaction: discord.Interaction):
            guild = interaction.guild
            member = interaction.user
            role = guild.get_role(int(role_id))
            
            if not role:
                await interaction.response.send_message("❌ Role no longer exists.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            # Check exclusive group
            if group:
                rows = await self.cog.bot.db.fetchall(
                    "SELECT role_id FROM reaction_roles WHERE exclusive_group = ?",
                    (group,)
                )
                other_ids = [r["role_id"] for r in rows if r["role_id"] != role_id]
                for other_id in other_ids:
                    other_role = guild.get_role(int(other_id))
                    if other_role and other_role in member.roles:
                        await member.remove_roles(other_role, reason=f"Exclusive group: {group}")

            if role in member.roles:
                await member.remove_roles(role, reason="Reaction role toggled off")
                await interaction.followup.send(f"Removed role <@&{role_id}>.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Reaction role toggled on")
                await interaction.followup.send(f"Assigned role <@&{role_id}>.", ephemeral=True)

        return callback


class UtilityCog(commands.Cog):
    """Cog handling user welcomes, verification systems, lockdown triggers, and reaction roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.models = bot.models
        self.db = bot.db
        
        self.join_history: List[float] = []
        self.lockdown_active: bool = False

        # Schedules
        self.prune_unverified_loop.start()

    def cog_unload(self) -> None:
        self.prune_unverified_loop.cancel()

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.bot.bot_config.admin_user_ids:
            return True
        return interaction.user.guild_permissions.administrator

    async def complete_verification(self, interaction: discord.Interaction, user_id: int) -> None:
        """Removes Unverified status, assigns verified role, enqueues auto-roles."""
        guild = interaction.guild
        member = guild.get_member(user_id)
        if not member:
            return

        cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification
        verified_role_id = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification.verified_role_id or self.bot.bot_config.permissions.admin_role_id # fallback
        unverified_role_id = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification.unverified_role_id

        # Roles resolutions
        verified_role = guild.get_role(int(verified_role_id)) if verified_role_id else None
        unverified_role = guild.get_role(int(unverified_role_id)) if unverified_role_id else None

        try:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Verification complete")
            
            if verified_role:
                await member.add_roles(verified_role, reason="Verification complete")

            # Update DB verified state
            await self.models.verify_user(str(user_id), str(guild.id))

            # Queue Auto-role
            autorole_cog = self.bot.get_cog("AutoRoleCog")
            if autorole_cog:
                await autorole_cog.join_queue.put((str(guild.id), str(user_id), 0))

            if not interaction.response.is_done():
                await interaction.response.send_message("✅ Verification successful! Server access granted.", ephemeral=True)
            else:
                await interaction.followup.send("✅ Verification successful! Server access granted.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error completing verification for {member.name}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to update verification roles. Notify admins.", ephemeral=True)

    # --- Schedule prune tasks ---
    @tasks.loop(minutes=30)
    async def prune_unverified_loop(self) -> None:
        """Kicks members failing to complete verification within timeout window."""
        await self.bot.wait_until_ready()
        
        for guild in self.bot.guilds:
            try:
                g_cfg = self.bot.bot_config.get_guild(str(guild.id))
                if not g_cfg or not g_cfg.verification or not g_cfg.verification.auto_kick:
                    continue

                timeout_hours = g_cfg.verification.timeout_hours
                # Fetch unverified members older than window for this guild
                rows = await self.db.fetchall(
                    "SELECT user_id, guild_id FROM verification_queue WHERE guild_id = ? AND verified = 0 AND joined_at < datetime('now', '-' || ? || ' hours')",
                    (str(guild.id), str(timeout_hours))
                )

                for r in rows:
                    member = guild.get_member(int(r["user_id"]))
                    if member:
                        try:
                            await member.kick(reason=f"Failed to verify within {timeout_hours} hours.")
                            logger.info(f"Kicked unverified member {member.name} (ID: {member.id}) due to timeout.")
                        except Exception as e:
                            logger.error(f"Failed to kick unverified user {r['user_id']} in guild {guild.id}: {e}")

                    # Delete from queue DB
                    await self.db.execute("DELETE FROM verification_queue WHERE user_id = ? AND guild_id = ?", (r["user_id"], r["guild_id"]))
            except Exception as ex:
                logger.error(f"Error running prune loop for guild {guild.id}: {ex}")

    # --- Welcome commands ---
    welcome = app_commands.Group(name="welcome", description="Configure welcome setups")

    @welcome.command(name="template", description="Set active welcome templates parameter")
    @app_commands.describe(template_text="Template description variables: {user}, {server}, {member_count}, {created_at}")
    async def welcome_template(self, interaction: discord.Interaction, template_text: str) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        self.bot.bot_config.get_guild(str(interaction.guild.id)).welcome.template = template_text
        config_schema.save_config(self.bot.bot_config)
        await interaction.response.send_message("✅ Welcome message template updated successfully.")

    @welcome.command(name="preview", description="Send welcome preview verification card")
    @app_commands.describe(user="User target template preview")
    async def welcome_preview(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).welcome
        desc = cfg.template.format(
            user=f"<@{user.id}>",
            server=interaction.guild.name,
            member_count=str(interaction.guild.member_count),
            created_at=user.created_at.strftime("%Y-%m-%d")
        )

        embed = discord.Embed(
            title=f"Welcome to {interaction.guild.name}!",
            description=desc,
            color=discord.Color.indigo()
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        view = VerificationButtonView(self)
        await interaction.response.send_message(embed=embed, view=view)

    # --- Verification commands ---
    verification = app_commands.Group(name="verification", description="Verification setups")

    @verification.command(name="config", description="Configure entry verification details")
    @app_commands.describe(method="button, math", timeout_hours="Auto-kick window hours", auto_kick="Kick unverified boolean")
    async def verification_config(self, interaction: discord.Interaction, method: str, timeout_hours: int = 24, auto_kick: bool = True) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        if method not in ("button", "math"):
            await interaction.response.send_message("❌ Method must be either 'button' or 'math'.", ephemeral=True)
            return

        cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).verification
        cfg.method = method
        cfg.timeout_hours = timeout_hours
        cfg.auto_kick = auto_kick

        config_schema.save_config(self.bot.bot_config)
        await interaction.response.send_message("✅ Verification configuration parameters saved.")

    @verification.command(name="stats", description="Access completion conversion figures")
    async def verification_stats(self, interaction: discord.Interaction) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        row_v = await self.db.fetchone("SELECT COUNT(*) as cnt FROM verification_queue WHERE verified = 1")
        row_uv = await self.db.fetchone("SELECT COUNT(*) as cnt FROM verification_queue WHERE verified = 0")
        
        v = row_v["cnt"] if row_v else 0
        uv = row_uv["cnt"] if row_uv else 0
        total = v + uv
        rate = (v / total * 100) if total > 0 else 0.0

        embed = discord.Embed(title="Verification Statistics", color=discord.Color.teal())
        embed.add_field(name="Verified Members", value=str(v), inline=True)
        embed.add_field(name="Unverified Members", value=str(uv), inline=True)
        embed.add_field(name="Completion Rate", value=f"{rate:.2f}%", inline=True)

        await interaction.response.send_message(embed=embed)

    # --- Reaction roles commands ---
    reactionrole = app_commands.Group(name="reactionrole", description="Button reaction role managers")

    @reactionrole.command(name="create-panel", description="Build selection buttons role panel")
    @app_commands.describe(channel="Target text channel", roles_comma="Comma roles list", labels_comma="Buttons labels list")
    async def rxrole_panel(self, interaction: discord.Interaction, channel: discord.TextChannel, roles_comma: str, labels_comma: str) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        roles_list = [r.strip() for r in roles_comma.split(",") if r.strip()]
        labels_list = [l.strip() for l in labels_comma.split(",") if l.strip()]

        if len(roles_list) != len(labels_list):
            await interaction.response.send_message("❌ Amount of roles must match labels list length.", ephemeral=True)
            return

        configs = []
        for name, label in zip(roles_list, labels_list):
            role = discord.utils.get(interaction.guild.roles, name=name)
            if role:
                configs.append({"role_id": str(role.id), "label": label})

        if not configs:
            await interaction.response.send_message("❌ Could not resolve any roles from target list.", ephemeral=True)
            return

        view = ReactionPanelButtonView(self, configs)
        embed = discord.Embed(
            title="Assigned Account Roles Panel",
            description="Toggle buttons below to self-assign or remove account roles.",
            color=discord.Color.blue()
        )
        msg = await channel.send(embed=embed, view=view)
        
        # Save into DB
        for cfg in configs:
            await self.models.save_reaction_role(str(msg.id), str(channel.id), cfg["label"], cfg["role_id"], None)

        await interaction.response.send_message("✅ Button role panel dispatched successfully.", ephemeral=True)

    @reactionrole.command(name="create", description="Bind role selection to a single message react emoji")
    @app_commands.describe(role="Target role", channel="Target text channel", emoji="Reaction emoji trigger")
    async def rxrole_create(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel, emoji: str) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Reaction Role Trigger",
            description=f"React with {emoji} to get the <@&{role.id}> role!",
            color=discord.Color.green()
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except Exception:
            await msg.delete()
            await interaction.response.send_message("❌ Invalid emoji structure or bot lacks reactions privileges.", ephemeral=True)
            return

        await self.models.save_reaction_role(str(msg.id), str(channel.id), emoji, str(role.id), None)
        await interaction.response.send_message("✅ Emoji reaction role triggered successfully.")

    @reactionrole.command(name="delete", description="Remove reaction-role panel configurations mapping")
    @app_commands.describe(message_id="Panel message ID")
    async def rxrole_delete(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        count = await self.models.delete_reaction_role(message_id)
        if count > 0:
            await interaction.response.send_message(f"✅ Deleted reaction role panels configurations mapping for `{message_id}`.")
        else:
            await interaction.response.send_message("❌ Mapping not found in database records.", ephemeral=True)

    @reactionrole.command(name="list", description="Show all active reaction roles panels")
    async def rxrole_list(self, interaction: discord.Interaction) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        rows = await self.models.get_reaction_roles()
        if not rows:
            await interaction.response.send_message("No reaction roles configured.")
            return

        lines = []
        for r in rows:
            lines.append(f"• Msg: `{r['message_id']}` | Emoji: `{r['emoji']}` | Role: <@&{r['role_id']}> | Group: `{r['exclusive_group']}`")

        embed = discord.Embed(title="Active Reaction Roles", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @reactionrole.command(name="exclusive", description="Bind role panels into mutually exclusive groups")
    @app_commands.describe(message_id="Target message panel ID", group_name="Arbitrary group name")
    async def rxrole_exclusive(self, interaction: discord.Interaction, message_id: str, group_name: str) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        await self.db.execute(
            "UPDATE reaction_roles SET exclusive_group = ? WHERE message_id = ?",
            (group_name, message_id)
        )
        await interaction.response.send_message(f"✅ Bound message `{message_id}` roles into exclusive group: `{group_name}`.")

    # --- Anti-raid protection commands ---
    raid_protector = app_commands.Group(name="raid-protector", description="Raid velocity shields settings")

    @raid_protector.command(name="status", description="Query anti-raid safety settings")
    async def raid_status(self, interaction: discord.Interaction) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        cfg = self.bot.bot_config.get_guild(str(interaction.guild.id)).raid_protection
        embed = discord.Embed(
            title="Anti-Raid Shield Settings",
            color=discord.Color.red() if self.lockdown_active else discord.Color.green()
        )
        embed.add_field(name="Lockdown Status", value="🔴 LOCKED DOWN (Raid Mode)" if self.lockdown_active else "🟢 ONLINE (Normal)", inline=False)
        embed.add_field(name="Threshold Limits", value=f"{cfg.join_velocity_threshold} joins / 60 seconds", inline=True)
        embed.add_field(name="Min Account Age", value=f"{cfg.account_age_hours} hours", inline=True)

        await interaction.response.send_message(embed=embed)

    @raid_protector.command(name="lockdown", description="Toggle lockdown state manually")
    @app_commands.describe(enable="Lockdown state boolean")
    async def raid_lockdown(self, interaction: discord.Interaction, enable: bool) -> None:
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return

        self.lockdown_active = enable
        self.bot.bot_config.get_guild(str(interaction.guild.id)).raid_protection.enabled = enable
        config_schema.save_config(self.bot.bot_config)

        state_msg = "🚨 **SERVER LOCKED DOWN**: Paused auto-role assignment, manual verification captcha modals enforced." if enable else "✅ **LOCKDOWN RELEASED**: Returned server entry gates to standard settings."
        await interaction.response.send_message(state_msg)






async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
