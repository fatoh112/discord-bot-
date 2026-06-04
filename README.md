# Discord Bot - Production-Grade Server Management

A secure, high-concurrency, modular Discord bot framework built on `discord.py` and `Flask` featuring role-based access control, health monitoring, and GDPR compliance pipelines.

## Features
- **Auto-Role Assignment**: Robust joining queue with exponential retry backoff, concurrency locks, and database persistence.
- **Raid Protection & Verification**: Join velocity monitoring thresholds, account age checking gates, and Math Captcha challenges.
- **Reaction Roles**: Self-assignable button or emoji panels supporting exclusive groupings.
- **Flask Monitoring Dashboard**: Real-time status checks, health telemetry `/health`, error rates, and Prometheus metrics.
- **GDPR Compliance Pipelines**: Exporting client logs `/gdpr export`, consent controls, and automated daily data retention workers.
- **Disaster Recovery**: Encrypted database backups with Shamir's Secret Sharing key shards (2-of-3 threshold).

## Quick Start
1. **Configure Environment Secrets**: Copy `.env.example` to `.env` and fill out credentials.
2. **Execute Deployment Scripts**: Run `start.bat` on the host to initialize virtual environments, download prerequisites, apply migrations, and launch bot loops.
3. **Invite Application**: Invite the bot using permissions value `8` (Administrator) from the developer portal.
4. **Access Flask Dashboard**: Navigate to `http://localhost:8080/status` to view metrics and telemetry.

## Prerequisites
- Python 3.11+ (Mocks registered to fully support Python 3.13/3.14+)
- Windows 10/11 or Windows Server environment
- Discord Bot Token with Server Members and Message Content Gateway Intents enabled.

## Documentation
- See [OPERATIONS.md](file:///e:/discord%20bot/OPERATIONS.md) for Windows Host Deployment, exclusions, task schedules, and recovery test procedures.
- See [SECURITY.md](file:///e:/discord%20bot/SECURITY.md) for permission hierarchies, secret management, and vulnerability response guidelines.

## Commands Not Showing?

1. Run: `python debug_commands.py` to check registered commands
2. If empty: Restart bot (commands sync on startup)
3. If still empty: Kick and re-invite bot to server
4. Wait up to 1 hour for Discord to cache global commands
