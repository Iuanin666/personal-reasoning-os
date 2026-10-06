# Public release denylist

The public repository must never contain or depend on:

- Any real Personal OS vault, Profile, Profile History, Experience, Decision, Outcome, Model, Project, Knowledge note, or Source Evidence.
- Managed-source binaries or extracted source documents from a real vault.
- SQLite databases, FTS tables, embeddings, vectors, chunks, caches, or model weights.
- Conversation exports, Codex logs, debug output, screenshots, conflict artifacts, migration backups, or temporary files.
- Internal Golden Sets, evaluation answers, snapshots, reports, or queries derived from a real person's history.
- Secrets, credentials, private email addresses or phone numbers, real organization/customer/project names, or machine-specific user paths.
- Installed `runtime.json` files, local virtual environments, `node_modules`, generated work vaults, or generated reports containing runtime paths.

Only the fictional demo vault and synthetic evaluation cases under this repository are approved fixtures. `scripts/privacy_scan.py`, `scripts/public_validate.py`, `.gitignore`, and the Windows CI workflow enforce the machine-checkable portion of this policy.
