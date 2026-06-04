import io
import json
import datetime
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

class ComplianceCog(commands.Cog):
    """Cog handling GDPR compliance data exports, user anonymization, consent settings, and retention workers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.models = bot.models
        self.metrics = bot.metrics

        # Start daily data retention worker
        self.retention_worker_loop.start()

    def cog_unload(self) -> None:
        self.retention_worker_loop.cancel()

    async def cog_load(self) -> None:
        """Runs compliance schema migrations if required."""
        try:
            await self.db.execute("ALTER TABLE audit_logs ADD COLUMN legal_hold INTEGER DEFAULT 0;")
            logger.info("Database migration: Added legal_hold column to audit_logs.")
        except Exception:
            pass  # Column already exists

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.bot.bot_config.admin_user_ids:
            return True
        return interaction.user.guild_permissions.administrator

    # --- GDPR Commands ---
    gdpr = app_commands.Group(name="gdpr", description="GDPR compliance and data controls")

    @gdpr.command(name="export", description="Export all database records mapped to a target user.")
    @app_commands.describe(user="The user whose data to export")
    async def gdpr_export(self, interaction: discord.Interaction, user: discord.User) -> None:
        """Gathers and serializes all audit logs, reactions, and verification records for a user into a JSON file."""
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        user_id_str = str(user.id)

        # 1. Gather audit logs (where user is admin OR target)
        audit_rows = await self.db.fetchall(
            "SELECT * FROM audit_logs WHERE admin_id = ? OR target_id = ?",
            (user_id_str, user_id_str)
        )
        audits = [dict(r) for r in audit_rows]

        # 2. Gather user reactions
        reaction_rows = await self.db.fetchall(
            "SELECT * FROM user_reactions WHERE user_id = ?",
            (user_id_str,)
        )
        reactions = [dict(r) for r in reaction_rows]

        # 3. Gather verification records
        verification_rows = await self.db.fetchall(
            "SELECT * FROM verification_queue WHERE user_id = ?",
            (user_id_str,)
        )
        verifications = [dict(r) for r in verification_rows]

        # Assemble JSON structure
        export_data = {
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user_details": {
                "user_id": user.id,
                "username": user.name,
                "discriminator": user.discriminator
            },
            "audit_logs": audits,
            "user_reactions": reactions,
            "verification_queue": verifications
        }

        # Send via DM or direct download file
        json_bytes = json.dumps(export_data, indent=2, default=str).encode('utf-8')
        fp = io.BytesIO(json_bytes)
        discord_file = discord.File(fp, filename=f"gdpr_export_{user.id}.json")

        try:
            # Attempt DM first
            await user.send("Here is the personal data export you requested from the server.", file=discord_file)
            await interaction.followup.send("✅ Export compiled and delivered via DM to the user.")
        except discord.Forbidden:
            # Fallback to local channel attachment (ephemeral)
            fp.seek(0)
            discord_file = discord.File(fp, filename=f"gdpr_export_{user.id}.json")
            await interaction.followup.send("ℹ️ User DMs are closed. Here is the export file directly (ephemeral):", file=discord_file)

    @gdpr.command(name="delete", description="Anonymize user personal data in the database.")
    @app_commands.describe(user="User whose data to anonymize", confirm="Confirm deletion")
    async def gdpr_delete(self, interaction: discord.Interaction, user: discord.User, confirm: bool = False) -> None:
        """Replaces identifying user fields with 'DELETED_USER' in compliance tables."""
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return

        if not confirm:
            await interaction.response.send_message(
                f"⚠️ **GDPR DELETION / ANONYMIZATION**: This will scrub and replace all database instances "
                f"of user <@{user.id}> with `DELETED_USER`. To execute, re-run with `confirm=True`.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        user_id_str = str(user.id)

        async with self.db.begin_transaction() as conn:
            # Update audit logs (admin_id or target_id)
            # Skip rows with legal_hold
            await conn.execute(
                "UPDATE audit_logs SET admin_id = 'DELETED_USER' WHERE admin_id = ? AND (legal_hold = 0 OR legal_hold IS NULL)",
                (user_id_str,)
            )
            await conn.execute(
                "UPDATE audit_logs SET target_id = 'DELETED_USER' WHERE target_id = ? AND (legal_hold = 0 OR legal_hold IS NULL)",
                (user_id_str,)
            )

            # Update user reactions
            await conn.execute(
                "UPDATE user_reactions SET user_id = 'DELETED_USER' WHERE user_id = ?",
                (user_id_str,)
            )

            # Update verification queue
            await conn.execute(
                "UPDATE verification_queue SET user_id = 'DELETED_USER' WHERE user_id = ?",
                (user_id_str,)
            )

        # Log deletion itself to audit
        await self.models.log_audit(
            guild_id=str(interaction.guild.id) if interaction.guild else "SYSTEM",
            admin_id=str(interaction.user.id),
            action="GDPR_ANONYMIZE",
            target_id="DELETED_USER",
            reason=f"Anonymized user ID {user_id_str}",
            ip_hash="SYSTEM"
        )

        await interaction.followup.send(f"✅ Anonymization completed for user {user.name} ({user_id_str}).")

    @gdpr.command(name="consent", description="View or modify gdpr audit log consent settings.")
    @app_commands.describe(user="The user whose consent to view/modify", consent_state="Set consent state (True/False)")
    async def gdpr_consent(self, interaction: discord.Interaction, user: discord.User, consent_state: Optional[bool] = None) -> None:
        """Displays user's current consent flag, or toggles it between active states."""
        if not await self._check_admin(interaction):
            await interaction.response.send_message("❌ Access Denied: Administrator clearance is required.", ephemeral=True)
            return

        user_id_str = str(user.id)
        
        if consent_state is None:
            # Query current state (default to 1 / True)
            row = await self.db.fetchone(
                "SELECT consent_flag FROM audit_logs WHERE target_id = ? ORDER BY id DESC LIMIT 1",
                (user_id_str,)
            )
            current_state = row["consent_flag"] != 0 if row else True
            await interaction.response.send_message(
                f"ℹ️ Consent Status for <@{user.id}>: **{'Granted' if current_state else 'Revoked'}** (consent_flag={1 if current_state else 0}).",
                ephemeral=True
            )
        else:
            new_flag = 1 if consent_state else 0
            # Update all audit logs for the user to match new flag state
            await self.db.execute(
                "UPDATE audit_logs SET consent_flag = ? WHERE target_id = ? OR admin_id = ?",
                (new_flag, user_id_str, user_id_str)
            )

            # Log consent update
            await self.models.log_audit(
                guild_id=str(interaction.guild.id) if interaction.guild else "SYSTEM",
                admin_id=str(interaction.user.id),
                action="CONSENT_UPDATE",
                target_id=user_id_str,
                reason=f"Consent toggled to {consent_state}",
                ip_hash="SYSTEM"
            )
            await interaction.response.send_message(
                f"✅ Updated consent status for <@{user.id}> to **{'Granted' if consent_state else 'Revoked'}**.",
                ephemeral=True
            )

    # --- Retention Worker Task ---
    @tasks.loop(hours=24)
    async def retention_worker_loop(self) -> None:
        """Daily retention worker deleting audit logs older than the configured GDPR_RETENTION_DAYS."""
        await self.bot.wait_until_ready()
        
        retention_days = self.bot.bot_config.gdpr_retention_days
        logger.info(f"Running compliance retention worker: pruning logs older than {retention_days} days...")
        
        # Calculate date threshold
        # SQLITE datetime helper: datetime('now', '-X days')
        try:
            # Perform pruning where legal_hold is 0 (or null)
            count = await self.db.execute(
                "DELETE FROM audit_logs WHERE timestamp < datetime('now', '-' || ? || ' days') AND (legal_hold = 0 OR legal_hold IS NULL)",
                (str(retention_days),)
            )
            if count > 0:
                logger.info(f"Compliance retention: Purged {count} expired audit logs.")
                # Log deletion operation itself to audit
                await self.models.log_audit(
                    guild_id="SYSTEM",
                    admin_id="SYSTEM",
                    action="RETENTION_PRUNE",
                    target_id="SYSTEM",
                    reason=f"Scrubbed {count} audit records older than {retention_days} days.",
                    ip_hash="SYSTEM"
                )
        except Exception as e:
            logger.error(f"Compliance retention pruning failed: {e}")


async def setup(bot: commands.Bot) -> None:
    cog = ComplianceCog(bot)
    await cog.cog_load()
    await bot.add_cog(cog)
