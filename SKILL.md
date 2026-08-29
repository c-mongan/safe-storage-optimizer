---
name: safe-storage-optimizer
description: Audit and safely reclaim disk space on macOS, Windows, or Linux when the user wants to find large files, remove unused apps or developer data, offload files to cloud storage, or understand disk use versus memory and swap. Do not use for a simple file lookup or a routine single-app uninstall.
---

# Safe Storage Optimizer

Make storage cleanup understandable, recoverable, and evidence-based. Automate read-only discovery and verification. Keep deletion and cloud upload behind exact approval.

## Start with the operating system

Detect the operating system and available storage providers. Read [references/platforms.md](references/platforms.md) only for the detected platform.

For a broad audit, run the bundled read-only scanner:

```bash
python3 scripts/storage_audit.py --output-dir <safe-output-directory>
```

Use `--deep-home` only when the user requests a deep audit. Do not add `--include-cloud` unless the user accepts that scanning cloud placeholders can download files and consume space.

The report contains full local paths and filenames. Treat it as private data and redact it before publishing or sharing.
The scanner also writes `storage-map.mmd` and embeds the same Mermaid graph in `storage-audit.md`.

## Work in evidence gates

### 1. Map

Record baseline free space. Rank large apps, user folders, caches, developer tools, virtual machines, container data, model files, backups, logs, cloud caches, Trash, and swap.

For each important item report:

- exact path and size;
- what created it and what it is for;
- evidence of recent or active use;
- whether it is source data, a cache, a backup, or rebuildable;
- recommendation: `KEEP`, `MOVE`, `REMOVE`, `REBUILD`, or `REVIEW`;
- recovery method and expected space gain.

Expand large folders from largest child to smallest. Continue recursively until the result explains the space or reaches ordinary user files.

For a multi-item audit, include a compact visual map. Read [references/visual-map.md](references/visual-map.md). Show parent-child folder links, measured sizes, and the final `KEEP`, `MOVE`, `REMOVE`, `REBUILD`, or `REVIEW` decision. Do not let the graph replace the exact path table or safety evidence.

### 2. Prove safety

Before recommending removal, inspect cheap evidence such as running processes, modification times, package-manager receipts, launch items, Git status and remotes, app configuration, container metadata, database state, and existing backups.

Protect these by default:

- dirty or unpushed Git work;
- databases, container volumes, virtual disks, local models, and app state;
- credentials, `.env` files, keys, settings, sessions, and recovery data;
- active project folders and cloud placeholders;
- backups that are the only known recovery layer.

Do not infer that an unfamiliar folder is disposable. Do not treat an old modification time as proof of disuse.

### 3. Propose batches

Order candidates by safety and value:

1. expired caches, installers, exact duplicates, and rebuildable environments;
2. unused apps with settings backed up;
3. clean remote-backed projects and reproducible developer data;
4. cloud offload of personal or archival files;
5. databases, virtual machines, container volumes, and unique backups only after export and restore evidence.

Name every destructive or external target. Get explicit approval for deletion, uninstall, cloud upload, emptying Trash, database export to cloud, or changing online-only state. Approval for one batch does not authorize another.

### 4. Execute with checkpoints

Measure before each batch. Back up valuable settings or state. Use exact paths and avoid broad globs, unresolved variables, filesystem roots, or destructive recursive commands over mixed data.

After each batch verify:

- the intended target is gone or reduced;
- protected data remains;
- active services and projects still work when relevant;
- actual free space changed as expected.

Stop if evidence conflicts with the plan.

## Cloud offload rules

Treat a cloud move as an upload of user data, not as ordinary local organization.

1. Choose the destination from the data sensitivity and user preference.
2. Copy before deleting the source.
3. Compare file counts and content checksums.
4. Confirm the provider reports the upload complete and not uploading.
5. Only then remove the source.
6. Make the cloud copy online-only only after upload proof.

Never recursively size a cloud root by default. That can hydrate placeholders and reduce free space. Do not put secrets in a cloud archive unless the user explicitly approves that exact data and destination. Prefer excluding rebuildable environments and secret files from source archives.

## Storage is not memory

If free space behaves unexpectedly, inspect swap, memory pressure, filesystem snapshots, cloud download state, and purgeable storage. Explain that disk cleanup does not increase physical RAM. Never manually delete system swap files.

## Finish with proof

Report:

- space before and after;
- exact removed, moved, and preserved items;
- backup and checksum locations;
- services or projects tested;
- temporary space such as swap that may clear after restart;
- any remaining candidate large enough to matter.

Do not claim reclaimed space from estimated sizes alone. Use the filesystem's current free-space measurement.
