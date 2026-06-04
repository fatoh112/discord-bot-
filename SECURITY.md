# Security Guidelines & Architecture Model

## Secret Management
- **No Hardcoded Tokens**: Environmental secrets (`DISCORD_TOKEN`, `ENCRYPTION_KEY`, `DASHBOARD_PASSWORD_HASH`, `DISCORD_AUDIT_WEBHOOK_URL`) are loaded from `.env`.
- **Key Cryptography**: Encrypted database backups use AES-256 (via Fernet). Keys can be reconstructed using Shamir's Secret Sharing threshold (2-of-3 split).
- **Session Authentication**: Flask dashboard session tokens are cryptographically signed with 30-minute expiry windows and `HttpOnly` / `SameSite=Strict` restrictions.

## Permission Model & RBAC
- **Owner Override**: Whitelisted users inside `ADMIN_USER_IDS` bypass command rate limits and permission restrictions.
- **Administrator Role Clearance**: Only users with Discord `Administrator` permission are allowed to invoke `/admin` and `/gdpr` commands.
- **Bot Hierarchy Check**: The bot will reject managing or assigning roles positioned equal to or higher than the bot's own highest role in the server hierarchy.

## Audit Logging
- Every administrative action is automatically logged to the `audit_logs` database table.
- Logs include: timestamp, actor (admin ID), operation type, target ID, reason, and hashed display name IP fallback keys.
- Legal holds can be enforced on database entries by setting `legal_hold = 1`.

## Incident Response
If a token leakage is detected:
1. Revoke the token immediately via the Discord Developer Portal.
2. Regenerate keys using Shamir key scripts.
3. Review audit logs (`/admin audit search`) and Flask access details.
