# Platform routes

Read only the section for the detected operating system.

## macOS

Prefer `df`, `du`, `find`, `ps`, `diskutil`, `tmutil`, package-manager receipts, and app bundle metadata for read-only evidence. Useful storage locations include:

- `~/Downloads`, `~/Documents`, `~/Desktop`, `~/Pictures`, `~/Movies`;
- `~/Library/Application Support`, `~/Library/Caches`, `~/Library/Containers`, and `~/Library/Group Containers`;
- `/Applications`, Homebrew casks, developer SDKs, simulator data, Docker or OrbStack data, and local model stores;
- `~/Library/CloudStorage` and `~/Library/Mobile Documents`, without recursive traversal by default.

Use `sysctl vm.swapusage` and `memory_pressure` to separate memory pressure from persistent storage. Check APFS snapshots when deleted files do not appear to release space.

For iCloud, use File Provider state or Finder to confirm `isUploaded = 1` and `isUploading = 0`. Finder's **Remove Download** keeps the cloud file and evicts local content. Confirm the item is uploaded before using it.

Do not treat a remote server or another computer as cloud storage unless the user explicitly chooses it as a backup destination.

## Windows

Prefer PowerShell read-only commands such as `Get-PSDrive`, `Get-ChildItem`, `Get-Process`, `Get-AppxPackage`, `winget list`, and Storage Sense status. Useful locations include:

- `%USERPROFILE%\Downloads`, Desktop, Documents, Pictures, Videos, and Music;
- `%LOCALAPPDATA%\Temp`, package caches, browser caches, application data, WSL virtual disks, Docker Desktop data, and development SDKs;
- `Program Files`, `Program Files (x86)`, Windows optional features, and restore points;
- OneDrive, Dropbox, and Google Drive roots, without recursive traversal by default.

Use provider-supported **Free up space** or online-only controls only after sync completion. Do not delete `pagefile.sys`, `hiberfil.sys`, Windows component-store files, restore data, or WSL virtual disks manually. Use supported system settings or product commands.

Check whether a large environment is reproducible before removing `.venv`, `node_modules`, NuGet, npm, Cargo, or package-manager caches. Keep lockfiles and source.

## Linux

Prefer `df`, `du`, `find`, `ps`, package-manager queries, `systemctl`, and container tooling. Useful locations include:

- `~/Downloads`, `~/Documents`, media folders, `~/.cache`, `~/.local/share`, and package caches;
- `/var/cache`, `/var/log`, `/var/lib`, Flatpak, Snap, container images and volumes, virtual-machine images, and local model stores;
- mounted sync folders and network filesystems, without recursive traversal by default.

Use `free`, `/proc/meminfo`, and swap tooling to explain memory pressure. Do not delete active logs, package databases, container volumes, swap files, or system directories directly. Use supported rotation, package, container, or service commands after confirming ownership and recovery.

## Common developer evidence

For a project folder, check:

- Git working-tree status, branch, HEAD, remotes, and untracked files;
- lockfiles and environment manifests;
- whether generated folders are ignored;
- whether copied runtimes or evaluation artifacts are reproducible;
- whether a database or container volume has a tested export.

A remote URL does not prove all local work is backed up. A clean status does not prove the remote contains the current commit. Verify both when deletion depends on them.
