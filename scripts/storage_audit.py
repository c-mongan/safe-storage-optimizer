#!/usr/bin/env python3
"""Read-only, cross-platform storage audit for Safe Storage Optimizer."""

from __future__ import annotations

import argparse
import datetime as dt
import heapq
import html
import json
import os
import platform
import shutil
import tempfile
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


def signed_size(value: int) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{human_size(abs(value))}"


def activity_fields(timestamp: float | None) -> dict[str, Any]:
    if timestamp is None:
        return {"newest_content_modified_at": None, "days_since_modified": None}
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    return {
        "newest_content_modified_at": dt.datetime.fromtimestamp(
            timestamp, dt.timezone.utc
        ).isoformat(),
        "days_since_modified": max(0, int((now - timestamp) // 86400)),
    }


def activity_label(item: dict[str, Any]) -> str:
    days = item.get("days_since_modified")
    return "unknown" if days is None else f"{days} days ago"


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
        self.modified_times: dict[str, float | None] = {}

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
        newest: float | None = None
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
                            child_time = self.modified_times.get(str(entry_path))
                            if child_time is not None:
                                newest = max(newest or child_time, child_time)
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            size = stat.st_size
                            total += size
                            self.files += 1
                            self.remember(self.file_heap, size, entry_path)
                            self.modified_times[str(entry_path)] = stat.st_mtime
                            newest = max(newest or stat.st_mtime, stat.st_mtime)
                    except (OSError, PermissionError) as exc:
                        self.error_count += 1
                        if len(self.errors) < 100:
                            self.errors.append(f"{entry.path}: {exc}")
        except (OSError, PermissionError) as exc:
            self.error_count += 1
            if len(self.errors) < 100:
                self.errors.append(f"{path}: {exc}")

        if newest is None:
            try:
                newest = path.stat().st_mtime
            except (OSError, PermissionError):
                newest = None
        self.modified_times[str(path)] = newest
        self.remember(self.dir_heap, total, path)
        return total


def ordered(
    heap: list[tuple[int, str]], modified_times: dict[str, float | None] | None = None
) -> list[dict[str, Any]]:
    modified_times = modified_times or {}
    return [
        {
            "path": path,
            "bytes": size,
            "size": human_size(size),
            **activity_fields(modified_times.get(path)),
        }
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
        f'  n0["This computer<br/>Used {used} | Free {free}"]',
    ]
    for path in selected:
        item = candidates[path]
        try:
            relative = path.relative_to(home)
            label = relative.as_posix() if len(relative.parts) <= 2 else path.name
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


def build_comparison(
    baseline: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    if baseline.get("home") != current.get("home"):
        raise ValueError("baseline and current audit use different home folders")

    before_roots = {item["path"]: item for item in baseline.get("roots", [])}
    after_roots = {item["path"]: item for item in current.get("roots", [])}
    root_changes = []
    for path in sorted(before_roots.keys() | after_roots.keys()):
        before = before_roots.get(path, {}).get("bytes", 0)
        after = after_roots.get(path, {}).get("bytes", 0)
        root_changes.append(
            {
                "path": path,
                "before_bytes": before,
                "after_bytes": after,
                "change_bytes": after - before,
                "change": signed_size(after - before),
            }
        )
    root_changes.sort(key=lambda item: abs(item["change_bytes"]), reverse=True)

    free_change = current["disk"]["free"] - baseline["disk"]["free"]
    return {
        "baseline_generated_at": baseline.get("generated_at"),
        "current_generated_at": current.get("generated_at"),
        "free_before_bytes": baseline["disk"]["free"],
        "free_after_bytes": current["disk"]["free"],
        "free_change_bytes": free_change,
        "free_change": signed_size(free_change),
        "same_roots": set(before_roots) == set(after_roots),
        "root_changes": root_changes,
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Storage Audit Comparison",
        "",
        f"Baseline: {comparison['baseline_generated_at']}",
        f"Current: {comparison['current_generated_at']}",
        "",
        "## Result",
        "",
        f"- Free space before: {human_size(comparison['free_before_bytes'])}",
        f"- Free space after: {human_size(comparison['free_after_bytes'])}",
        f"- Free-space change: {comparison['free_change']}",
        f"- Same scanned roots: {'yes' if comparison['same_roots'] else 'no'}",
        "",
        "## Largest scanned-root changes",
        "",
    ]
    for item in comparison["root_changes"]:
        lines.append(f"- {item['change']}: `{item['path']}`")
    lines.extend(
        [
            "",
            "Measured folder changes can overlap. Use the filesystem free-space change as the final proof.",
            "",
        ]
    )
    return "\n".join(lines)


def build_cleanup_plan(report: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    candidates = []
    items = [
        ("directory", item) for item in report["largest_directories"]
    ] + [("file", item) for item in report["largest_files"]]
    items.sort(key=lambda pair: pair[1]["bytes"], reverse=True)
    for index, (kind, item) in enumerate(items[:limit], start=1):
        candidates.append(
            {
                "id": f"C{index:03d}",
                "target": item["path"],
                "kind": kind,
                "measured_bytes": item["bytes"],
                "measured_size": item["size"],
                "activity_evidence": {
                    "newest_content_modified_at": item.get(
                        "newest_content_modified_at"
                    ),
                    "days_since_modified": item.get("days_since_modified"),
                    "warning": "Modification time is evidence, not proof of use or disuse.",
                },
                "decision": "REVIEW",
                "approved": False,
                "reason": "",
                "recovery_method": "",
                "expected_gain_bytes": None,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": report["generated_at"],
        "state": "DRAFT_REVIEW_ONLY",
        "destructive_actions_authorized": False,
        "warning": "Candidates can overlap. This file never grants deletion approval.",
        "allowed_decisions": ["KEEP", "MOVE", "REMOVE", "REBUILD", "REVIEW"],
        "candidates": candidates,
    }


def render_html(
    report: dict[str, Any],
    cleanup_plan: dict[str, Any],
    comparison: dict[str, Any] | None = None,
) -> str:
    def safe(value: Any) -> str:
        return html.escape(str(value), quote=True)

    largest = report["largest_directories"][:15]
    maximum = max((item["bytes"] for item in largest), default=1)
    bars = []
    for item in largest:
        width = max(1, round(item["bytes"] / maximum * 100))
        days = item.get("days_since_modified")
        activity = "unknown" if days is None else f"{days} days ago"
        bars.append(
            '<div class="row"><div class="label">'
            f"<strong>{safe(item['size'])}</strong> {safe(item['path'])}"
            f'<small>Newest content change: {safe(activity)}</small></div>'
            f'<div class="track"><span style="width:{width}%"></span></div></div>'
        )

    comparison_html = (
        '<p class="empty">Run the audit again into this output folder to compare free space.</p>'
    )
    if comparison:
        direction = "more" if comparison["free_change_bytes"] >= 0 else "less"
        comparison_html = (
            f'<div class="metric"><strong>{safe(comparison["free_change"])}</strong>'
            f"<span>{direction} free space</span></div>"
            f'<p>Same scanned roots: {"yes" if comparison["same_roots"] else "no"}</p>'
        )

    rows = []
    for item in cleanup_plan["candidates"]:
        days = item["activity_evidence"]["days_since_modified"]
        activity = "unknown" if days is None else f"{days} days"
        rows.append(
            "<tr>"
            f"<td>{safe(item['id'])}</td><td>{safe(item['measured_size'])}</td>"
            f"<td>{safe(item['kind'])}</td><td>{safe(item['target'])}</td>"
            f"<td>{safe(activity)}</td><td><span class=\"review\">REVIEW</span></td>"
            "</tr>"
        )

    disk = report["disk"]
    used_percent = round(disk["used"] / disk["total"] * 100) if disk["total"] else 0
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Safe Storage Audit</title>
<style>
:root{{--ink:#172033;--muted:#60708a;--blue:#2563eb;--line:#dbe3ef;--paper:#f6f8fc;--amber:#d97706}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:32px 20px 60px}} h1{{font-size:32px;margin:0 0 6px}} h2{{margin-top:0}}
.sub,small{{color:var(--muted)}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:24px 0}}
.card{{background:white;border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 8px 24px #1831530b}}
.metric strong{{display:block;font-size:30px}} .metric span{{color:var(--muted)}} .disk{{height:14px;background:#e8eef8;border-radius:9px;overflow:hidden;margin-top:14px}}
.disk span,.track span{{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#60a5fa);border-radius:9px}}
.row{{display:grid;grid-template-columns:minmax(260px,2fr) 3fr;gap:18px;align-items:center;padding:9px 0}} .label{{overflow-wrap:anywhere}} small{{display:block;margin-top:3px}}
.track{{height:12px;background:#edf2f8;border-radius:8px;overflow:hidden}} table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}} td:nth-child(4){{overflow-wrap:anywhere;max-width:430px}}
.review{{color:#78350f;background:#fef3c7;border-radius:999px;padding:3px 8px;font-weight:700}} .notice{{border-left:4px solid var(--amber)}} .scroll{{overflow:auto}}
@media(max-width:650px){{.row{{grid-template-columns:1fr}} h1{{font-size:27px}}}}
</style></head><body><main>
<h1>Safe Storage Audit</h1><p class="sub">Generated {safe(report['generated_at'])} · {safe(report['platform'])}</p>
<section class="grid"><div class="card"><h2>Disk</h2><div class="metric"><strong>{safe(disk['free_human'])}</strong><span>free of {safe(disk['total_human'])}</span></div><div class="disk"><span style="width:{used_percent}%"></span></div><p>{used_percent}% used</p></div>
<div class="card"><h2>Since last audit</h2>{comparison_html}</div>
<div class="card notice"><h2>Safety state</h2><div class="metric"><strong>Review only</strong><span>No deletion is approved by this report.</span></div></div></section>
<section class="card"><h2>Largest folders</h2>{''.join(bars) or '<p class="empty">No folders found.</p>'}</section>
<section class="card" style="margin-top:16px"><h2>Cleanup candidates</h2><p class="sub">Sizes can overlap. Activity dates are clues, not proof that an item is unused.</p><div class="scroll"><table><thead><tr><th>ID</th><th>Size</th><th>Type</th><th>Target</th><th>Newest change</th><th>Decision</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
</main></body></html>"""


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
        lines.append(
            f"- {item['size']}: `{item['path']}` (newest content change: {activity_label(item)})"
        )

    lines.extend(["", "## Largest files", ""])
    for item in report["largest_files"]:
        lines.append(
            f"- {item['size']}: `{item['path']}` (modified: {activity_label(item)})"
        )

    lines.extend(
        [
            "",
            "## Safety notes",
            "",
            "- This audit is read-only.",
            "- Sizes are logical file sizes and can differ from physical disk use.",
            "- Cloud roots are skipped unless `--include-cloud` is set.",
            "- Modification dates are clues, not proof that an item is used or unused.",
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


def write_report(path: Path, contents: str) -> None:
    """Replace a report privately without writing through an existing link."""
    descriptor, temporary = tempfile.mkstemp(prefix=".storage-audit-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=30)
    parser.add_argument("--deep-home", action="store_true")
    parser.add_argument("--include-cloud", action="store_true")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="previous storage-audit.json to compare; defaults to the existing report in the output folder",
    )
    args = parser.parse_args()

    home = args.home.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    json_path = output_dir / "storage-audit.json"
    markdown_path = output_dir / "storage-audit.md"
    mermaid_path = output_dir / "storage-map.mmd"
    dashboard_path = output_dir / "storage-dashboard.html"
    cleanup_plan_path = output_dir / "cleanup-plan.json"
    comparison_json_path = output_dir / "storage-comparison.json"
    comparison_markdown_path = output_dir / "storage-comparison.md"
    for path in (
        json_path, markdown_path, mermaid_path, dashboard_path, cleanup_plan_path,
        comparison_json_path, comparison_markdown_path,
    ):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            parser.error(f"report destination must be a regular file, not a symlink: {path}")

    baseline_path = (
        args.baseline.expanduser().resolve()
        if args.baseline
        else output_dir / "storage-audit.json"
    )
    baseline: dict[str, Any] | None = None
    if args.baseline and not baseline_path.is_file():
        parser.error(f"baseline does not exist: {baseline_path}")
    if baseline_path.is_file():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"cannot read baseline {baseline_path}: {exc}")

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
        root_results.append(
            {
                "path": str(root),
                "bytes": size,
                "size": human_size(size),
                **activity_fields(scanner.modified_times.get(str(root))),
            }
        )

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
        "largest_directories": ordered(scanner.dir_heap, scanner.modified_times),
        "largest_files": ordered(scanner.file_heap, scanner.modified_times),
        "files_scanned": scanner.files,
        "directories_scanned": scanner.directories,
        "cloud_skips": sorted(set(scanner.cloud_skips)),
        "error_count": scanner.error_count,
        "error_samples": scanner.errors,
    }

    mermaid = render_mermaid(report)
    cleanup_plan = build_cleanup_plan(report)
    comparison: dict[str, Any] | None = None
    if baseline:
        try:
            comparison = build_comparison(baseline, report)
        except (KeyError, TypeError, ValueError) as exc:
            parser.error(f"invalid baseline {baseline_path}: {exc}")
    write_report(json_path, json.dumps(report, indent=2))
    write_report(markdown_path, render_markdown(report, mermaid))
    write_report(mermaid_path, mermaid)
    write_report(cleanup_plan_path, json.dumps(cleanup_plan, indent=2))
    write_report(dashboard_path, render_html(report, cleanup_plan, comparison))
    if comparison:
        write_report(comparison_json_path, json.dumps(comparison, indent=2))
        write_report(comparison_markdown_path, render_comparison_markdown(comparison))
    print(markdown_path)
    print(json_path)
    print(mermaid_path)
    print(dashboard_path)
    print(cleanup_plan_path)
    if comparison:
        print(comparison_markdown_path)
        print(comparison_json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
