# Safe Storage Optimizer

A Codex skill for finding and reclaiming disk space without deleting valuable data.

It supports macOS, Windows, and Linux. The workflow audits first, explains every large item, protects active projects and databases, verifies cloud uploads, requests exact approval for destructive actions, and measures the real result.

## Install

Copy the `safe-storage-optimizer` folder into your Codex skills directory:

```text
~/.codex/skills/safe-storage-optimizer
```

Then ask:

```text
Use $safe-storage-optimizer to audit this computer and rank the biggest safe storage wins.
```

## Read-only scanner

The bundled Python scanner works without third-party packages:

```bash
python3 scripts/storage_audit.py --output-dir ./audit-output
```

Use `--deep-home` for a deeper local scan. Cloud roots are skipped by default because recursive scans can download placeholder files and consume space.

Audit reports contain full local paths and filenames. Review and redact them before sharing.

## Safety model

- Audit before deletion.
- Back up unique data and settings.
- Preserve dirty Git work, databases, volumes, credentials, and active app state.
- Require exact approval for deletion, uninstall, uploads, and online-only changes.
- Verify checksums and completed cloud sync before removing local files.
- Separate disk storage from RAM and swap pressure.

## License

MIT
