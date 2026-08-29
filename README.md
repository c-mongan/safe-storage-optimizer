# Safe Storage Optimizer

[![Test](https://github.com/c-mongan/safe-storage-optimizer/actions/workflows/test.yml/badge.svg)](https://github.com/c-mongan/safe-storage-optimizer/actions/workflows/test.yml)

A Codex skill for finding and reclaiming disk space without deleting valuable data.

It supports macOS, Windows, and Linux. The workflow audits first, explains every large item, draws a folder-size graph, creates a review-only cleanup plan, protects active projects and databases, verifies cloud uploads, requests exact approval for destructive actions, and measures the real result.

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

The scanner creates:

- `storage-audit.md`: readable report with an embedded Mermaid graph;
- `storage-audit.json`: structured data for other tools;
- `storage-map.mmd`: a portable graph that GitHub and Mermaid tools can render.
- `storage-dashboard.html`: a standalone visual dashboard;
- `cleanup-plan.json`: review-only candidates with no deletion approval;
- `storage-comparison.md` and `.json`: created on later runs to prove the before/after change.

Run the same command again in the same output folder for an automatic comparison. Or choose a saved report:

```bash
python3 scripts/storage_audit.py --output-dir ./audit-output --baseline ./before/storage-audit.json
```

The activity dates show the newest content modification found during the scan. They do not prove that an app or folder is unused.

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
