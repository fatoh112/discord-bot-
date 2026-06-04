# Operations Manual: Windows Deployment & DB Administration

## Windows Deployment Checklist
To ensure 24/7 service uptime on a Windows host machine, complete the following items:

- [ ] **Windows Task Scheduler Configuration**:
  - Open `taskschd.msc`.
  - Action -> "Import Task..." and select `task.xml`.
  - Ensure **"Run with highest privileges"** is checked.
  - In Settings tab, check **"Allow task to be run on demand"** and set "Stop the task if it runs longer than" to **Disabled**.
- [ ] **Antivirus Exceptions (Windows Defender)**:
  - Add folder exclusion for `e:\discord bot\`.
  - Add file exclusion for `.venv\Scripts\python.exe` in this workspace.
- [ ] **Power & Hibernation Profiles**:
  - Configure Host PC power plans to **"Never Sleep"** and disable hybrid sleep states.
- [ ] **User Account Security**:
  - Configure automatic logon settings if system restarts, and ensure the deployment account does not auto-logoff.

---

## Monthly Backup Restore Test
Every month, the disaster recovery mechanisms must be manually verified. Perform the following steps:

1. **Stop Bot Instance**:
   Run `stop.bat` to gracefully disconnect the gateway socket and dump the active memory queues.
2. **Safeguard Database**:
   Rename current active database file:
   ```cmd
   ren database.db database.db.old
   ```
3. **Trigger Restore Script**:
   Locate your latest encrypted backup in `backups/daily/` (or `weekly/`/`monthly/`) and execute the verification utility:
   ```cmd
   .venv\Scripts\python.exe scripts/verify_backup.py --restore latest
   ```
4. **Re-initialize Bot Loop**:
   Run `start.bat` to start the bot.
5. **Verify Bot Status**:
   Confirm client reconnects, query `/health` on the Flask dashboard, and inspect logs.
6. **Final Cleanup**:
   If validation passes, safely delete `database.db.old`. If it fails, restore `database.db.old` back to `database.db` and report the anomaly.
