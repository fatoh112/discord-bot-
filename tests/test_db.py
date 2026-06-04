import pytest
import os
import aiosqlite
from database.db_manager import DatabaseManager
from database.models import DatabaseModels

@pytest.mark.asyncio
async def test_connection_pool(tmp_path):
    db_file = tmp_path / "test_db.db"
    db = DatabaseManager(str(db_file), max_connections=2)
    await db.connect()
    assert db._connected is True
    assert db.pool.qsize() == 2
    await db.disconnect()
    assert db._connected is False

@pytest.mark.asyncio
async def test_transaction_integrity(tmp_path):
    db_file = tmp_path / "test_tx.db"
    db = DatabaseManager(str(db_file), max_connections=2)
    await db.connect()
    
    # Create a test table
    await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT);")
    
    # Successful transaction
    async with db.begin_transaction() as conn:
        await conn.execute("INSERT INTO test (val) VALUES ('ok');")
        
    row = await db.fetchone("SELECT * FROM test;")
    assert row["val"] == "ok"
    
    # Failing transaction should rollback
    try:
        async with db.begin_transaction() as conn:
            await conn.execute("INSERT INTO test (val) VALUES ('fail');")
            raise ValueError("Forced error to test rollback")
    except ValueError:
        pass
        
    rows = await db.fetchall("SELECT * FROM test WHERE val = 'fail';")
    assert len(rows) == 0
    
    await db.disconnect()

@pytest.mark.asyncio
async def test_gdpr_anonymization(tmp_path):
    db_file = tmp_path / "test_gdpr.db"
    db = DatabaseManager(str(db_file), max_connections=2)
    await db.connect()
    
    models = DatabaseModels(db)
    await models.create_tables()
    
    # Add a user audit log, reaction, and verification queue entry
    user_id = "123456"
    await models.log_audit("guild_123", "admin_123", "GRANT", user_id, "test reason", "hash_123")
    await models.record_user_reaction(user_id, "msg_123", "role_123")
    await models.add_to_verification(user_id, "guild_123", "button")
    
    # Verify entries exist
    logs = await models.get_audit_logs(user_id)
    assert len(logs) == 1
    
    # Anonymize: update references to DELETED_USER
    await db.execute("UPDATE audit_logs SET target_id = 'DELETED_USER' WHERE target_id = ?;", (user_id,))
    await db.execute("UPDATE user_reactions SET user_id = 'DELETED_USER' WHERE user_id = ?;", (user_id,))
    await db.execute("UPDATE verification_queue SET user_id = 'DELETED_USER' WHERE user_id = ?;", (user_id,))
    
    # Verify data is anonymized
    old_logs = await models.get_audit_logs(user_id)
    assert len(old_logs) == 0
    
    deleted_logs = await models.get_audit_logs("DELETED_USER")
    assert len(deleted_logs) == 1
    
    await db.disconnect()
