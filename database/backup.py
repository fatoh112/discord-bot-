import os
import shutil
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from loguru import logger

class BackupManager:
    """Manages secure encrypted database backup creations, integrity checks, and retentions."""

    def __init__(
        self,
        encryption_key: str,
        base_backup_dir: str = "backups",
        db_path: str = "database.db",
        config_path: str = "config.json"
    ):
        """Initializes the BackupManager with a encryption key and target directories.

        Args:
            encryption_key: The base64 URL-safe 32-byte Fernet key.
            base_backup_dir: Root directory folder where backups are saved.
            db_path: Filepath of the target database file to backup.
            config_path: Filepath of config.json to include in backup cycles.
        """
        self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        self.base_backup_dir = base_backup_dir
        self.db_path = db_path
        self.config_path = config_path

        # Setup standard subdirs
        self.daily_dir = os.path.join(base_backup_dir, "daily")
        self.weekly_dir = os.path.join(base_backup_dir, "weekly")
        self.monthly_dir = os.path.join(base_backup_dir, "monthly")
        self.checksums_dir = os.path.join(base_backup_dir, "checksums")

        for d in [self.daily_dir, self.weekly_dir, self.monthly_dir, self.checksums_dir]:
            os.makedirs(d, exist_ok=True)

    def _encrypt_and_save(self, src_path: str, dest_path: str) -> str:
        """Encrypts a target file and saves it, returning the SHA256 of the ciphertext."""
        with open(src_path, "rb") as f:
            data = f.read()

        encrypted = self.fernet.encrypt(data)

        with open(dest_path, "wb") as f:
            f.write(encrypted)

        # Generate checksum of the ENCRYPTED file (ciphertext)
        sha256 = hashlib.sha256(encrypted).hexdigest()
        return sha256

    def _decrypt_and_restore(self, src_path: str, dest_path: str) -> None:
        """Decrypts a backup file and saves it back to the destination path."""
        with open(src_path, "rb") as f:
            encrypted_data = f.read()

        decrypted = self.fernet.decrypt(encrypted_data)

        # Ensure target folder is present
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(decrypted)

    def create_backup(self, backup_type: str = "daily") -> Tuple[str, str]:
        """Creates encrypted backups of the database.db and config.json.

        Args:
            backup_type: "daily", "weekly", or "monthly".

        Returns:
            Tuple of (timestamp, backup_filename).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = {
            "daily": self.daily_dir,
            "weekly": self.weekly_dir,
            "monthly": self.monthly_dir
        }.get(backup_type, self.daily_dir)

        # Naming requirement: backup_YYYYMMDD_HHMMSS.enc.db
        backup_filename = f"backup_{timestamp}.enc.db"
        dest_db_path = os.path.join(target_dir, backup_filename)

        if not os.path.exists(self.db_path):
            # Create a placeholder empty database file to backup if missing
            with open(self.db_path, "w") as f:
                f.write("")

        # Encrypt and save DB
        checksum = self._encrypt_and_save(self.db_path, dest_db_path)

        # Store SHA256 checksum in backups/checksums/
        checksum_file_path = os.path.join(self.checksums_dir, f"backup_{timestamp}.sha256")
        with open(checksum_file_path, "w", encoding="utf-8") as f:
            f.write(checksum)

        logger.info(f"Encrypted {backup_type} backup successfully created: {dest_db_path}")
        self.prune_old_backups()
        return timestamp, backup_filename

    def verify_checksum(self, backup_filepath: str) -> bool:
        """Verifies the integrity of a backup file by checking its SHA256 checksum."""
        if not os.path.exists(backup_filepath):
            logger.error(f"Backup file not found for verification: {backup_filepath}")
            return False

        # Read the file data
        with open(backup_filepath, "rb") as f:
            data = f.read()

        current_checksum = hashlib.sha256(data).hexdigest()

        # Resolve expected checksum file name from path
        filename = os.path.basename(backup_filepath)
        # Extract timestamp parts e.g. backup_20260603_220000.enc.db
        timestamp_part = filename.replace("backup_", "").replace(".enc.db", "")
        expected_checksum_path = os.path.join(self.checksums_dir, f"backup_{timestamp_part}.sha256")

        if not os.path.exists(expected_checksum_path):
            logger.error(f"Checksum definition file not found: {expected_checksum_path}")
            return False

        with open(expected_checksum_path, "r", encoding="utf-8") as f:
            expected_checksum = f.read().strip()

        is_valid = current_checksum == expected_checksum
        if not is_valid:
            logger.error(f"Backup integrity check failed for: {backup_filepath}")
        return is_valid

    def restore_backup(self, backup_filepath: str) -> None:
        """Decrypts and restores the database from a backup file path.

        Args:
            backup_filepath: Path to the encrypted backup file.
        """
        if not self.verify_checksum(backup_filepath):
            raise ValueError(f"Integrity check failed. Backup file is corrupted or untrusted: {backup_filepath}")

        # Safety rollback copy of active DB if present
        if os.path.exists(self.db_path):
            shutil.copy2(self.db_path, f"{self.db_path}.bak")

        try:
            self._decrypt_and_restore(backup_filepath, self.db_path)
            if os.path.exists(f"{self.db_path}.bak"):
                os.remove(f"{self.db_path}.bak")
            logger.info(f"Database successfully restored from: {backup_filepath}")
        except Exception as e:
            logger.error(f"Failed to restore database from backup. Reverting rollback: {e}")
            if os.path.exists(f"{self.db_path}.bak"):
                shutil.move(f"{self.db_path}.bak", self.db_path)
            raise e

    def prune_old_backups(self) -> None:
        """Prunes historical backups based on retention policies (7 daily, 4 weekly, 12 monthly)."""
        now = datetime.now()

        def parse_timestamp(filename: str) -> Optional[datetime]:
            if not filename.startswith("backup_") or not filename.endswith(".enc.db"):
                return None
            ts_str = filename.replace("backup_", "").replace(".enc.db", "")
            try:
                return datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            except ValueError:
                return None

        # Clean daily (keep 7 days)
        for item in os.listdir(self.daily_dir):
            t = parse_timestamp(item)
            if t and (now - t) > timedelta(days=7):
                path = os.path.join(self.daily_dir, item)
                os.remove(path)
                logger.info(f"Pruned old daily backup: {item}")

        # Clean weekly (keep 4 weeks)
        for item in os.listdir(self.weekly_dir):
            t = parse_timestamp(item)
            if t and (now - t) > timedelta(weeks=4):
                path = os.path.join(self.weekly_dir, item)
                os.remove(path)
                logger.info(f"Pruned old weekly backup: {item}")

        # Clean monthly (keep 12 months / 365 days)
        for item in os.listdir(self.monthly_dir):
            t = parse_timestamp(item)
            if t and (now - t) > timedelta(days=365):
                path = os.path.join(self.monthly_dir, item)
                os.remove(path)
                logger.info(f"Pruned old monthly backup: {item}")
