# Usage evidence

Read only the section for the detected operating system. Use several signals before deciding that an app, tool, or folder is unused. Modification and access times can be changed by updates, backups, indexing, copying, or disabled access-time tracking.

## macOS

- Check whether the app or related service is running with `ps` or Activity Monitor.
- Inspect `kMDItemLastUsedDate` and `kMDItemUseCount` with `mdls` when Spotlight provides them. A missing value is not proof of no use.
- Inspect app bundle metadata and package-manager records to identify the owner and install method. Bundle modification time usually shows an update, not a launch.
- Check Login Items, LaunchAgents, LaunchDaemons, menu-bar helpers, and background-item settings before removing support data.
- For developer tools, check shell history only with the user's permission because it can contain private commands. Prefer project manifests, running processes, and recent project changes.

## Windows

- Check running processes and services with Task Manager or `Get-Process` and `Get-Service`.
- Use installed-app records, `winget list`, Appx package data, and application settings to identify ownership and uninstall support.
- Check Startup Apps, scheduled tasks, services, WSL distributions, Docker state, and virtual disks before removing support data.
- Windows Prefetch, event logs, and privacy-controlled activity history can be absent or incomplete. Treat them as supporting evidence only.
- Do not infer use from an installer or executable modification date. Updates can change it without a launch.

## Linux

- Check running processes and services with `ps` and `systemctl`.
- Use the owning package manager, desktop-file metadata, Flatpak or Snap state, and container tooling to identify the install and supported removal path.
- Check user services, autostart entries, scheduled jobs, containers, mounts, and virtual machines before removing support data.
- Journal records and shell history can help only when available and appropriate. They can be incomplete or private.
- Package timestamps and access times do not prove interactive use.

## Decision rule

Prefer `REVIEW` unless at least two independent signals support the recommendation. Recent active processes, unique data, dirty source work, a sole backup, or an unknown recovery path override weak evidence of disuse.
