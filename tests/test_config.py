import pytest
import os
from pydantic import ValidationError
from config_schema import BotConfig, load_config

def test_valid_config(test_config):
    config = BotConfig(**test_config)
    assert config.guilds["987654321"].autorole.enabled is True

def test_invalid_config_missing_fields():
    # pydantic v2 will initialize default fields for BotConfig if empty dict is supplied
    # but let's supply invalid values (like wrong types) to trigger ValidationError
    invalid = {"guilds": {"123": {"autorole": {"enabled": "not-a-bool"}}}}
    with pytest.raises(ValidationError):
        BotConfig(**invalid)

def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_TOKEN", "env_override_token")
    monkeypatch.setenv("ADMIN_USER_IDS", "12345,67890")
    monkeypatch.setenv("ENCRYPTION_KEY", "env_key")
    
    # Create a temporary config file
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")
    
    config = load_config(str(cfg_file))
    assert config.discord_token == "env_override_token"
    assert config.admin_user_ids == [12345, 67890]
    assert config.encryption_key == "env_key"
