#!/usr/bin/env python3
"""Read-only, cross-platform storage audit for Safe Storage Optimizer."""

from __future__ import annotations

import argparse
import datetime as dt
import heapq
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any


CLOUD_MARKERS = {
    "cloudstorage",
    "mobile documents",
    "onedrive",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud drive",
}


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def is_cloud_path(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return any(marker in lowered for marker in CLOUD_MARKERS)


def candidate_roots(home: Path, system: str, deep_home: bool) -> list[Path]:
    if deep_home:
        return [home]

    common = [
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
        home / "Pictures",
        home / "Movies",
        home / "Videos",
        home / "Music",
        home / ".cache",
        home / ".npm",
        home / ".codex",
    ]
    if system == "Darwin":
        common.extend(
            [
                home / "Library" / "Caches",
                home / "Library" / "Application Support",
                home / "Library" / "Containers",
                home / "Library" / "Group Containers",
            ]
        )
    elif system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        common.extend([local / "Temp", local, roaming])
    else:
        common.extend([home / ".local" / "share", home / "snap"])

    existing: list[Path] = []
    seen: set[str] = set()
    for item in common:
        item = item.resolve()
        key = str(item)
        if key not in seen and item.exists():
            seen.add(key)
            existing.append(item)

    unique: list[Path] = []
    for item in sorted(existing, key=lambda path: len(path.parts)):
        if not any(item == parent or item.is_relative_to(parent) for parent in unique):
            unique.append(item)
    return unique


class Scanner:
    def __init__(
        self,
        top: int,
        max_depth: int,
        include_cloud: bool,
        ignored_paths: set[Path] | None = None,
    ) -> None:
        self.top = top
        self.max_depth = max_depth
        self.include_cloud = include_cloud
        self.dir_heap: list[tuple[int, str]] = []
        self.file_heap: list[tuple[int, str]] = []
        self.errors: list[str] = []
        self.error_count = 0
        self.files = 0
        self.directories = 0
        self.cloud_skips: list[str] = []
        self.ignored_paths = {path.resolve() for path in (ignored_paths or set())}

    def remember(self, heap: list[tuple[int, str]], size: int, path: Path) -> None:
        item = (size, str(path))
        if len(heap) < self.top:
            heapq.heappush(heap, item)
        elif size > heap[0][0]:
            heapq.heapreplace(heap, item)

    def scan(self, path: Path, depth: int = 0) -> int:
        if path.resolve() in self.ignored_paths:
            return 0
        if not self.include_cloud and is_cloud_path(path):
            self.cloud_skips.append(str(path))
            return 0
        if depth > self.max_depth:
            return 0

        total = 0
        self.directories += 1
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        entry_path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            total += self.scan(entry_path, depth + 1)
                        elif entry.is_file(follow_symlinks=False):
                            size = entry.stat(follow_symlinks=False).st_size
                            total += size
                            self.files += 1
                            self.remember(self.file_heap, size, entry_path)
                    except (OSError, PermissionError) as exc:
                        self.error_count += 1
                        if len(self.errors) < 100:
                            self.errors.append(f"{entry.path}: {exc}")
        except (OSError, PermissionError) as exc:
            self.error_count += 1
            if len(self.errors) < 100:
                self.errors.append(f"{path}: {exc}")

        self.remember(self.dir_heap, total, path)
        return total


def ordered(heap: list[tuple[int, str]]) -> list[dict[str, Any]]:
    return [
        {"path": path, "bytes": size, "size": human_size(size)}
        for size, path in sorted(heap, reverse=True)
    ]


def mermaid_text(value: str) -> str:
    """Keep a label readable without allowing Mermaid syntax injection."""
    return (
        value.replace("&", "and")
        .replace('"', "'")
        .replace("<", "(")
        .replace(">", ")")
        .replace("\n", " ")
    )


def render_mermaid(report: dict[str, Any], max_nodes: int = 24) -> str:
    """Render a compact hierarchy of the largest scanned directories."""
    home = Path(report["home"])
    candidates: dict[Path, dict[str, Any]] = {}
    for item in report["roots"] + report["largest_directories"]:
        path = Path(item["path"])
        if path == home:
            continue
        current = candidates.get(path)
        if current is None or item["bytes"] > current["bytes"]:
            candidates[path] = item

    roots = [Path(item["path"]) for item in report["roots"] if Path(item["path"]) != home]
    ranked = sorted(candidates, key=lambda path: candidates[path]["bytes"], reverse=True)
    selected: list[Path] = []
    for path in roots + ranked:
        if path not in selected:
            selected.append(path)
        if len(selected) >= max(1, max_nodes - 1):
            break

    node_ids = {path: f"n{index + 1}" for index, path in enumerate(selected)}
    used = report["disk"]["used_human"]
    free = report["disk"]["free_human"]
    lines = [
        "flowchart LR",
        f'  n0["This computer<br/>Used {used} · Free {free}"]',
    ]
    for path in selected:
        item = candidates[path]
        try:
            relative = path.relative_to(home)
            label = str(relative) if len(relative.parts) <= 2 else path.name
        except ValueError:
            label = path.name or str(path)
        lines.append(
            f'  {node_ids[path]}["{mermaid_text(label)}<br/>{item["size"]}"]'
        )

    selected_set = set(selected)
    for path in selected:
        ancestors = [
            candidate
            for candidate in selected_set
            if candidate != path and path.is_relative_to(candidate)
        ]
        parent = max(ancestors, key=lambda candidate: len(candidate.parts), default=None)
        parent_id = node_ids[parent] if parent else "n0"
        lines.append(f"  {parent_id} --> {node_ids[path]}")

    lines.extend(
        [
            "  classDef computer fill:#111827,color:#ffffff,stroke:#111827,stroke-width:2px;",
            "  classDef storage fill:#dbeafe,color:#172554,stroke:#2563eb;",
            "  class n0 computer;",
        ]
    )
    if selected:
        lines.append(f"  class {','.join(node_ids.values())} storage;")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict[str, Any], mermaid: str | None = None) -> str:
    disk = report["disk"]
    lines = [
        "# Safe Storage Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Platform: {report['platform']}",
        f"Home: `{report['home']}`",
        "",
        "## Disk",
        "",
        f"- Total: {disk['total_human']}",
        f"- Used: {disk['used_human']}",
        f"- Free: {disk['free_human']}",
        "",
        "## Scanned roots",
        "",
    ]
    for root in report["roots"]:
        lines.append(f"- {root['size']}: `{root['path']}`")

    if mermaid:
        lines.extend(
            [
                "",
                "## Storage map",
                "",
                "This map shows the largest scanned folders. It is evidence for review, not permission to delete.",
                "",
                "```mermaid",
                mermaid.rstrip(),
                "```",
            ]
        )

    lines.extend(["", "## Largest directories", ""])
    for item in report["largest_directories"]:
        lines.append(f"- {item['size']}: `{item['path']}`")

    lines.extend(["", "## Largest files", ""])
    for item in report["largest_files"]:
        lines.append(f"- {item['size']}: `{item['path']}`")

    lines.extend(
        [
            "",
            "## Safety notes",
            "",
            "- This audit is read-only.",
            "- Sizes are logical file sizes and can differ from physical disk use.",
            "- Cloud roots are skipped unless `--include-cloud` is set.",
            "- Verify ownership, use, backup, and recovery before deleting anything.",
        ]
    )
    if report["cloud_skips"]:
        lines.extend(["", "Skipped cloud paths:"])
        lines.extend(f"- `{item}`" for item in report["cloud_skips"])
    if report["error_count"]:
        lines.extend(
            [
                "",
                f"Unreadable entries: {report['error_count']} (see JSON for samples).",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=30)
    parser.add_argument("--deep-home", action="store_true")
    parser.add_argument("--include-cloud", action="store_true")
    args = parser.parse_args()

    home = args.home.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system()
    roots = candidate_roots(home, system, args.deep_home)
    scanner = Scanner(
        max(5, args.top),
        max(1, args.max_depth),
        args.include_cloud,
        ignored_paths={output_dir},
    )
    root_results = []
    for root in roots:
        size = scanner.scan(root)
        root_results.append({"path": str(root), "bytes": size, "size": human_size(size)})

    usage = shutil.disk_usage(home)
    report: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": f"{system} {platform.release()}",
        "home": str(home),
        "disk": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "total_human": human_size(usage.total),
            "used_human": human_size(usage.used),
            "free_human": human_size(usage.free),
        },
        "roots": sorted(root_results, key=lambda item: item["bytes"], reverse=True),
        "largest_directories": ordered(scanner.dir_heap),
        "largest_files": ordered(scanner.file_heap),
        "files_scanned": scanner.files,
        "directories_scanned": scanner.directories,
        "cloud_skips": sorted(set(scanner.cloud_skips)),
        "error_count": scanner.error_count,
        "error_samples": scanner.errors,
    }

    json_path = output_dir / "storage-audit.json"
    markdown_path = output_dir / "storage-audit.md"
    mermaid_path = output_dir / "storage-map.mmd"
    mermaid = render_mermaid(report)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report, mermaid), encoding="utf-8")
    mermaid_path.write_text(mermaid, encoding="utf-8")
    print(markdown_path)
    print(json_path)
    print(mermaid_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
