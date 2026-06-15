from typing import List, Dict, Any, Optional, Tuple
import sqlite3
from loguru import logger
from database import DatabaseManager

# --- SQL Table Initialization Constants ---
CREATE_AUTOROLE_CONFIGS = """
CREATE TABLE IF NOT EXISTS autorole_configs (
    guild_id TEXT,
    role_id TEXT,
    priority INTEGER,
    PRIMARY KEY (guild_id, role_id)
);
"""

CREATE_REACTION_ROLES = """
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id TEXT PRIMARY KEY,
    channel_id TEXT,
    emoji TEXT,
    role_id TEXT,
    exclusive_group TEXT
);
"""

CREATE_USER_REACTIONS = """
CREATE TABLE IF NOT EXISTS user_reactions (
    user_id TEXT,
    message_id TEXT,
    role_id TEXT,
    PRIMARY KEY (user_id, message_id, role_id)
);
"""

CREATE_AUDIT_LOGS = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT,
    admin_id TEXT,
    action TEXT,
    target_id TEXT,
    reason TEXT,
    timestamp TEXT,
    ip_hash TEXT,
    consent_flag INTEGER DEFAULT 1,
    data_category TEXT
);
"""

CREATE_VERIFICATION_QUEUE = """
CREATE TABLE IF NOT EXISTS verification_queue (
    user_id TEXT,
    guild_id TEXT,
    joined_at TEXT,
    verified INTEGER DEFAULT 0,
    method TEXT,
    status TEXT DEFAULT 'pending',
    PRIMARY KEY (user_id, guild_id)
);
"""

CREATE_METRICS_CACHE = """
CREATE TABLE IF NOT EXISTS metrics_cache (
    guild_id TEXT,
    metric_name TEXT,
    value REAL,
    timestamp TEXT,
    PRIMARY KEY (guild_id, metric_name, timestamp)
);
"""

CREATE_DASHBOARD_PREFS = """
CREATE TABLE IF NOT EXISTS dashboard_prefs (
    user_id TEXT,
    theme TEXT DEFAULT 'dark',
    sidebar_collapsed INTEGER DEFAULT 0,
    PRIMARY KEY (user_id)
);
"""

CREATE_ACTION_HISTORY = """
CREATE TABLE IF NOT EXISTS action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id TEXT,
    action TEXT,
    details TEXT,
    timestamp TEXT
);
"""

CREATE_MUSIC_GUILD_CONFIG = """
CREATE TABLE IF NOT EXISTS music_guild_config (
    guild_id TEXT PRIMARY KEY,
    dj_role_id TEXT,
    max_queue_size INTEGER DEFAULT 100,
    auto_disconnect_minutes INTEGER DEFAULT 5,
    dashboard_channel_id TEXT
);
"""

CREATE_MUSIC_PLAYLISTS = """
CREATE TABLE IF NOT EXISTS music_playlists (
    user_id TEXT,
    playlist_name TEXT,
    tracks TEXT,
    PRIMARY KEY (user_id, playlist_name)
);
"""

class DatabaseModels:
    """Helper service managing SQL execution and CRUD model bindings."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def create_tables(self) -> None:
        """Creates all required database tables on startup if they do not exist."""
        logger.info("Initializing bot database tables...")
        statements = [
            CREATE_AUTOROLE_CONFIGS,
            CREATE_REACTION_ROLES,
            CREATE_USER_REACTIONS,
            CREATE_AUDIT_LOGS,
            CREATE_VERIFICATION_QUEUE,
            CREATE_METRICS_CACHE,
            CREATE_DASHBOARD_PREFS,
            CREATE_ACTION_HISTORY,
            CREATE_MUSIC_GUILD_CONFIG,
            CREATE_MUSIC_PLAYLISTS
        ]
        async with self.db.begin_transaction() as conn:
            for statement in statements:
                await conn.execute(statement)

        # Run schema upgrades
        try:
            async with self.db.begin_transaction() as conn:
                await conn.execute("ALTER TABLE music_guild_config ADD COLUMN dashboard_channel_id TEXT;")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Failed to alter music_guild_config table: {e}")
        except Exception as e:
            logger.error(f"Failed to alter music_guild_config table: {e}")

        logger.info("Database table initialization completed.")

    # --- autorole_configs CRUD ---
    async def add_autorole(self, guild_id: str, role_id: str, priority: int) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO autorole_configs (guild_id, role_id, priority)
            VALUES (?, ?, ?)
            """,
            (guild_id, role_id, priority)
        )

    async def remove_autorole(self, guild_id: str, role_id: str) -> int:
        return await self.db.execute(
            "DELETE FROM autorole_configs WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id)
        )

    async def get_autoroles(self, guild_id: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT role_id, priority FROM autorole_configs WHERE guild_id = ? ORDER BY priority ASC",
            (guild_id,)
        )
        return [{"role_id": r["role_id"], "priority": r["priority"]} for r in rows]

    # --- reaction_roles CRUD ---
    async def save_reaction_role(self, message_id: str, channel_id: str, emoji: str, role_id: str, exclusive_group: Optional[str] = None) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO reaction_roles (message_id, channel_id, emoji, role_id, exclusive_group)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, channel_id, emoji, role_id, exclusive_group)
        )

    async def delete_reaction_role(self, message_id: str) -> int:
        return await self.db.execute(
            "DELETE FROM reaction_roles WHERE message_id = ?",
            (message_id,)
        )

    async def get_reaction_roles(self) -> List[Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT message_id, channel_id, emoji, role_id, exclusive_group FROM reaction_roles"
        )
        return [dict(r) for r in rows]

    # --- user_reactions CRUD ---
    async def record_user_reaction(self, user_id: str, message_id: str, role_id: str) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO user_reactions (user_id, message_id, role_id) VALUES (?, ?, ?)",
            (user_id, message_id, role_id)
        )

    async def remove_user_reaction(self, user_id: str, message_id: str, role_id: str) -> int:
        return await self.db.execute(
            "DELETE FROM user_reactions WHERE user_id = ? AND message_id = ? AND role_id = ?",
            (user_id, message_id, role_id)
        )

    # --- audit_logs CRUD ---
    async def log_audit(
        self,
        guild_id: str,
        admin_id: str,
        action: str,
        target_id: str,
        reason: str,
        ip_hash: str,
        consent_flag: int = 1,
        data_category: str = "necessary"
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_logs (guild_id, admin_id, action, target_id, reason, timestamp, ip_hash, consent_flag, data_category)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
            """,
            (guild_id, admin_id, action, target_id, reason, ip_hash, consent_flag, data_category)
        )

    async def get_audit_logs(self, target_id: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT guild_id, admin_id, action, target_id, reason, timestamp, ip_hash, consent_flag, data_category FROM audit_logs WHERE target_id = ?",
            (target_id,)
        )
        return [dict(r) for r in rows]

    # --- verification_queue CRUD ---
    async def add_to_verification(self, user_id: str, guild_id: str, method: str) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO verification_queue (user_id, guild_id, joined_at, verified, method)
            VALUES (?, ?, datetime('now'), 0, ?)
            """,
            (user_id, guild_id, method)
        )

    async def verify_user(self, user_id: str, guild_id: str) -> int:
        return await self.db.execute(
            "UPDATE verification_queue SET verified = 1 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

    # --- metrics_cache CRUD ---
    async def cache_metric(self, guild_id: str, metric_name: str, value: float) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO metrics_cache (guild_id, metric_name, value, timestamp)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (guild_id, metric_name, value)
        )

    # --- dashboard_prefs CRUD ---
    async def save_dashboard_prefs(self, user_id: str, theme: str, sidebar_collapsed: int) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO dashboard_prefs (user_id, theme, sidebar_collapsed)
            VALUES (?, ?, ?)
            """,
            (user_id, theme, sidebar_collapsed)
        )

    async def get_dashboard_prefs(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchone(
            "SELECT theme, sidebar_collapsed FROM dashboard_prefs WHERE user_id = ?",
            (user_id,)
        )
        return dict(row) if row else None

    # --- action_history CRUD ---
    async def log_dashboard_action(self, admin_id: str, action: str, details: str) -> None:
        await self.db.execute(
            """
            INSERT INTO action_history (admin_id, action, details, timestamp)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (admin_id, action, details)
        )

    async def get_dashboard_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT id, admin_id, action, details, timestamp FROM action_history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in rows]

    # --- music CRUD ---
    async def get_music_config(self, guild_id: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetchone(
            "SELECT dj_role_id, max_queue_size, auto_disconnect_minutes, dashboard_channel_id FROM music_guild_config WHERE guild_id = ?",
            (guild_id,)
        )
        return dict(row) if row else None

    async def save_music_config(self, guild_id: str, dj_role_id: Optional[str], max_queue_size: int = 100, auto_disconnect_minutes: int = 5, dashboard_channel_id: Optional[str] = None) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO music_guild_config (guild_id, dj_role_id, max_queue_size, auto_disconnect_minutes, dashboard_channel_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, dj_role_id, max_queue_size, auto_disconnect_minutes, dashboard_channel_id)
        )

    async def save_playlist(self, user_id: str, playlist_name: str, tracks: str) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO music_playlists (user_id, playlist_name, tracks)
            VALUES (?, ?, ?)
            """,
            (user_id, playlist_name, tracks)
        )

    async def get_playlist(self, user_id: str, playlist_name: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT tracks FROM music_playlists WHERE user_id = ? AND playlist_name = ?",
            (user_id, playlist_name)
        )
        return row["tracks"] if row else None
