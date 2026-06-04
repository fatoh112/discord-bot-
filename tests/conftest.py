import sys
from unittest.mock import MagicMock
sys.modules['audioop'] = MagicMock()

import pytest
import asyncio
import aiosqlite
from pathlib import Path

@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_connection():
    conn = await aiosqlite.connect(":memory:")
    yield conn
    await conn.close()

@pytest.fixture
def test_config():
    return {
        "autorole": {
            "enabled": True,
            "delay_seconds": 1,
            "roles": [],
            "exclude_bots": True,
            "require_verification": True,
            "log_channel_id": None
        },
        "welcome": {
            "enabled": False,
            "channel_id": None,
            "template": "Welcome to {server}, {user}! You are member #{member_count}.",
            "dm_welcome": False,
            "send_dm": False,
            "enable_verification_button": True
        },
        "verification": {
            "method": "button",
            "timeout_hours": 24,
            "auto_kick": True,
            "verified_role_id": None,
            "unverified_role_id": None
        },
        "raid_protection": {
            "enabled": False,
            "join_velocity_threshold": 10,
            "account_age_hours": 24
        },
        "permissions": {
            "admin_role_id": None,
            "moderator_role_id": None
        }
    }

@pytest.fixture
def mock_discord_member():
    class MockMember:
        id = 123456789
        name = "TestUser"
        display_name = "TestUser"
        bot = False
        roles = []
        async def add_roles(self, *roles, reason=None):
            pass
        async def remove_roles(self, *roles, reason=None):
            pass
        async def send(self, content=None, *, file=None):
            pass
    return MockMember()

@pytest.fixture
def mock_discord_guild():
    class MockGuild:
        id = 987654321
        name = "Test Server"
        member_count = 100
        me = None
        def get_member(self, user_id):
            return None
        def get_channel(self, channel_id):
            return None
        def get_role(self, role_id):
            return None
    return MockGuild()
