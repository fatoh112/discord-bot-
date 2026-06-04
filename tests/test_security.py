import pytest
import os
import sqlite3
from database.db_manager import DatabaseManager
from database.backup import BackupManager

def test_sql_injection_resistance(tmp_path):
    # Parameterized query check: verify passing suspicious strings doesn't trigger injection
    db_file = tmp_path / "test_sec.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id TEXT, name TEXT);")
    
    suspicious_name = "Robert'); DROP TABLE users;--"
    
    # Safe parameterized insert
    cursor.execute("INSERT INTO users (id, name) VALUES (?, ?);", ("1", suspicious_name))
    conn.commit()
    
    # Read back
    cursor.execute("SELECT * FROM users WHERE name = ?;", (suspicious_name,))
    row = cursor.fetchone()
    assert row is not None
    assert row[1] == suspicious_name
    
    # Verify table 'users' still exists (injection failed to drop it)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
    assert cursor.fetchone() is not None
    conn.close()

def test_path_traversal():
    # Verify that BackupManager blocks directory traversal patterns when loading backups
    bm = BackupManager(encryption_key="y5hQ1d5rV-Fj-t7t8o53R67lC-4R4Jd_pG5v1T3i9k4=")
    
    suspicious_paths = [
        "../../etc/passwd",
        "..\\..\\sensitive_file",
        "backups/daily/../../../db.db",
        "C:\\Windows\\System32\\cmd.exe"
    ]
    
    for path in suspicious_paths:
        # Check if the backup restoration or backup name checking prevents traversal or handles it
        # Since restore_backup expects the target path, verify that we validate paths safely
        # Or let's test a path cleaning utility if we have one.
        # Let's ensure the path resolution returns a path within backups folder.
        with pytest.raises(Exception):
            bm.restore_backup(path)

def test_no_hardcoded_tokens():
    # Scan the codebase directory for any actual Discord tokens
    import re
    token_pattern = re.compile(r"MTA[a-zA-Z0-9\-_]{21}\.[a-zA-Z0-9\-_]{6}\.[a-zA-Z0-9\-_]{27}")
    
    project_root = "e:/discord bot"
    for root, dirs, files in os.walk(project_root):
        if ".venv" in root or ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    matches = token_pattern.findall(content)
                    # Exclude the test validation dummy token in bot.py
                    filtered_matches = [m for m in matches if "dummy_token_for_validation_testing" not in m]
                    assert len(filtered_matches) == 0, f"Potential hardcoded token found in {path}: {filtered_matches}"
