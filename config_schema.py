import json
import os
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class AutoRoleItem(BaseModel):
    id: str
    priority: int


class AutoRoleConfig(BaseModel):
    enabled: bool = True
    delay_seconds: int = 2
    roles: List[AutoRoleItem] = Field(default_factory=list)
    exclude_bots: bool = True
    require_verification: bool = True
    log_channel_id: Optional[str] = None


class WelcomeConfig(BaseModel):
    enabled: bool = True
    channel_id: Optional[str] = None
    template: str = "Welcome to {server}, {user}! You are member #{member_count}."
    dm_welcome: bool = False
    send_dm: bool = False
    enable_verification_button: bool = True


class VerificationConfig(BaseModel):
    method: str = "button"  # e.g., "button", "math"
    timeout_hours: int = 24
    auto_kick: bool = True
    verified_role_id: Optional[str] = None
    unverified_role_id: Optional[str] = None


class RaidProtectionConfig(BaseModel):
    enabled: bool = False
    join_velocity_threshold: int = 10
    account_age_hours: int = 24


class DatabaseConfig(BaseModel):
    path: str = "bot.db"
    wal_mode: bool = True
    backup_interval_hours: int = 24


class PermissionsConfig(BaseModel):
    admin_role_id: Optional[str] = None
    moderator_role_id: Optional[str] = None


class GuildConfig(BaseModel):
    """Configuration specific to a single Discord guild."""
    autorole: AutoRoleConfig = Field(default_factory=AutoRoleConfig)
    welcome: WelcomeConfig = Field(default_factory=WelcomeConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    raid_protection: RaidProtectionConfig = Field(default_factory=RaidProtectionConfig)


class BotConfig(BaseModel):
    """Pydantic v2 configuration schema for the Discord bot."""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    guilds: Dict[str, GuildConfig] = Field(default_factory=dict)
    
    def get_guild(self, guild_id: str) -> GuildConfig:
        """Get or initialize the configuration for a specific guild."""
        if guild_id not in self.guilds:
            self.guilds[guild_id] = GuildConfig()
        return self.guilds[guild_id]

    # Environmental secrets loaded from env
    discord_token: Optional[str] = None
    admin_user_ids: List[int] = Field(default_factory=list)
    encryption_key: Optional[str] = None
    dashboard_username: str = "admin"
    dashboard_password_hash: Optional[str] = None
    discord_audit_webhook_url: Optional[str] = None
    gdpr_retention_days: int = 365
    
    # Dashboard Settings
    bot_name: str = "Antigravity Bot"
    avatar_url: Optional[str] = None
    prefix: str = "!"
    timezone: str = "UTC"
    language: str = "en"


def load_config(config_path: str = "config.json") -> BotConfig:
    """Loads configuration from config.json and overrides values with env vars.

    Args:
        config_path: Filepath to the config.json.

    Returns:
        BotConfig: The validated configuration object.

    Raises:
        ValidationError: If JSON data fails Pydantic schema validation.
    """
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    config_obj = BotConfig(**data)

    # Apply env overrides
    env_token = os.getenv("DISCORD_TOKEN")
    env_admins = os.getenv("ADMIN_USER_IDS")
    env_key = os.getenv("ENCRYPTION_KEY")
    env_dash_user = os.getenv("DASHBOARD_USERNAME")
    env_dash_pass = os.getenv("DASHBOARD_PASSWORD_HASH")
    env_webhook = os.getenv("DISCORD_AUDIT_WEBHOOK_URL")
    env_gdpr = os.getenv("GDPR_RETENTION_DAYS")

    if env_token:
        config_obj.discord_token = env_token
    if env_admins:
        config_obj.admin_user_ids = [
            int(x.strip()) for x in env_admins.split(",") if x.strip().isdigit()
        ]
    if env_key:
        config_obj.encryption_key = env_key
    if env_dash_user:
        config_obj.dashboard_username = env_dash_user
    if env_dash_pass:
        config_obj.dashboard_password_hash = env_dash_pass
    if env_webhook:
        config_obj.discord_audit_webhook_url = env_webhook
    if env_gdpr and env_gdpr.isdigit():
        config_obj.gdpr_retention_days = int(env_gdpr)

    return config_obj


def save_config(config: BotConfig, config_path: str = "config.json") -> None:
    """Saves the non-sensitive parts of BotConfig back to config.json.

    Args:
        config: The BotConfig object to serialize.
        config_path: Filepath to write the config JSON.
    """
    # Only persist structural config, never secrets
    excluded_keys = {
        "discord_token", "admin_user_ids", "encryption_key",
        "dashboard_username", "dashboard_password_hash",
        "discord_audit_webhook_url", "gdpr_retention_days"
    }
    data = config.model_dump(exclude=excluded_keys)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
