import importlib.util
import json
import os
import subprocess
import stat
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "storage_audit.py"
SPEC = importlib.util.spec_from_file_location("storage_audit", SCRIPT)
assert SPEC and SPEC.loader
storage_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage_audit)


class StorageAuditTests(unittest.TestCase):
    def run_fixture_audit(self, home: Path, output: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--home", str(home), "--output-dir", str(output)],
            capture_output=True, text=True,
        )

    @unittest.skipUnless(os.name == "posix", "POSIX symlinks")
    def test_report_symlinks_are_refused_before_any_outputs_change(self) -> None:
        names = (
            "storage-audit.json", "storage-audit.md", "storage-map.mmd",
            "storage-dashboard.html", "cleanup-plan.json",
            "storage-comparison.json", "storage-comparison.md",
        )
        for name in names:
            for dangling in (False, True):
                with self.subTest(name=name, dangling=dangling), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    home = root / "home"
                    home.mkdir()
                    output = root / "output"
                    self.assertEqual(self.run_fixture_audit(home, output).returncode, 0)
                    target = root / "unrelated.txt"
                    report = output / name
                    contents = report.read_bytes() if report.exists() else b"Synthetic unrelated data."
                    if not dangling:
                        target.write_bytes(contents)
                    report.unlink(missing_ok=True)
                    report.symlink_to(target)
                    originals = {p.name: p.read_bytes() for p in output.iterdir() if not p.is_symlink()}

                    result = self.run_fixture_audit(home, output)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("report destination", result.stderr)
                    self.assertTrue(report.is_symlink())
                    self.assertEqual({p.name: p.read_bytes() for p in output.iterdir() if not p.is_symlink()}, originals)
                    if dangling:
                        self.assertFalse(target.exists())
                    else:
                        self.assertEqual(target.read_bytes(), contents)

    def test_report_directory_is_refused_before_any_outputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            output = root / "output"
            self.assertEqual(self.run_fixture_audit(home, output).returncode, 0)
            report = output / "cleanup-plan.json"
            report.unlink()
            report.mkdir()
            originals = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}

            result = self.run_fixture_audit(home, output)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("report destination", result.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}, originals)

    @unittest.skipUnless(os.name == "posix", "POSIX hard links")
    def test_report_replacement_preserves_unrelated_hard_link_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            output = root / "output"
            self.assertEqual(self.run_fixture_audit(home, output).returncode, 0)
            target = root / "unrelated.txt"
            target.write_text("Synthetic unrelated data.")
            report = output / "cleanup-plan.json"
            report.unlink()
            os.link(target, report)

            result = self.run_fixture_audit(home, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(), "Synthetic unrelated data.")
            self.assertEqual(json.loads(report.read_text())["state"], "DRAFT_REVIEW_ONLY")
            self.assertNotEqual(report.stat().st_ino, target.stat().st_ino)

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions")
    def test_new_report_directory_and_reports_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            output = root / "output"
            previous = os.umask(0o022)
            try:
                for _ in range(2):
                    result = self.run_fixture_audit(home, output)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
                    for report in output.iterdir():
                        self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            finally:
                os.umask(previous)

            self.assertEqual(len(list(output.iterdir())), 7)

    def test_human_size(self) -> None:
        self.assertEqual(storage_audit.human_size(1024), "1.0 KiB")
        self.assertEqual(storage_audit.human_size(1024**3), "1.0 GiB")

    def test_cloud_paths_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            local = home / "Downloads"
            cloud = home / "OneDrive" / "private"
            local.mkdir()
            cloud.mkdir(parents=True)
            (local / "local.bin").write_bytes(b"a" * 10)
            (cloud / "cloud.bin").write_bytes(b"b" * 20)

            scanner = storage_audit.Scanner(10, 20, include_cloud=False)
            size = scanner.scan(home)

            self.assertEqual(size, 10)
            self.assertEqual(scanner.files, 1)
            self.assertIn(str(home / "OneDrive"), scanner.cloud_skips)

    def test_output_directory_can_be_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            output = home / "audit-output"
            output.mkdir()
            (output / "old-report.json").write_text(json.dumps({"old": True}))

            scanner = storage_audit.Scanner(
                10,
                20,
                include_cloud=False,
                ignored_paths={output},
            )

            self.assertEqual(scanner.scan(home), 0)
            self.assertEqual(scanner.files, 0)

    def test_mermaid_map_is_hierarchical_and_escapes_labels(self) -> None:
        report = {
            "home": "/Users/test",
            "disk": {"used_human": "70.0 GiB", "free_human": "30.0 GiB"},
            "roots": [
                {"path": "/Users/test/Downloads", "bytes": 30, "size": "30.0 B"},
            ],
            "largest_directories": [
                {"path": "/Users/test/Downloads/A&B", "bytes": 20, "size": "20.0 B"},
            ],
        }

        graph = storage_audit.render_mermaid(report)

        self.assertIn("flowchart LR", graph)
        self.assertIn("Downloads/AandB", graph)
        self.assertIn("n1 --> n2", graph)
        self.assertIn("classDef storage", graph)

    def test_command_writes_dashboard_plan_and_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            output = Path(temp) / "output"
            downloads = home / "Downloads"
            downloads.mkdir(parents=True)
            (downloads / "large.bin").write_bytes(b"x" * 1024)

            command = [
                sys.executable,
                str(SCRIPT),
                "--home",
                str(home),
                "--output-dir",
                str(output),
            ]
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue((output / "storage-audit.json").is_file())
            self.assertTrue((output / "storage-audit.md").is_file())
            self.assertTrue((output / "storage-map.mmd").is_file())
            self.assertTrue((output / "storage-dashboard.html").is_file())
            self.assertTrue((output / "cleanup-plan.json").is_file())
            self.assertIn("```mermaid", (output / "storage-audit.md").read_text())
            plan = json.loads((output / "cleanup-plan.json").read_text())
            self.assertEqual(plan["state"], "DRAFT_REVIEW_ONLY")
            self.assertFalse(plan["destructive_actions_authorized"])
            self.assertTrue(all(not item["approved"] for item in plan["candidates"]))

            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertTrue((output / "storage-comparison.md").is_file())
            comparison = json.loads((output / "storage-comparison.json").read_text())
            self.assertIsInstance(comparison["free_change_bytes"], int)
            self.assertTrue(comparison["same_roots"])

    def test_activity_evidence_uses_newest_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            older = root / "older.bin"
            newer = root / "newer.bin"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            older_time = 1_600_000_000
            newer_time = 1_700_000_000
            os.utime(older, (older_time, older_time))
            os.utime(newer, (newer_time, newer_time))
            scanner = storage_audit.Scanner(10, 20, include_cloud=False)

            scanner.scan(root)

            self.assertEqual(scanner.modified_times[str(root)], newer_time)

    def test_comparison_rejects_a_different_home(self) -> None:
        baseline = {"home": "/one"}
        current = {"home": "/two"}

        with self.assertRaisesRegex(ValueError, "different home"):
            storage_audit.build_comparison(baseline, current)

    def test_dashboard_escapes_private_path_markup(self) -> None:
        report = {
            "generated_at": "now",
            "platform": "test",
            "disk": {
                "total": 100,
                "used": 50,
                "free": 50,
                "total_human": "100.0 B",
                "free_human": "50.0 B",
            },
            "largest_directories": [
                {
                    "path": "/tmp/<script>alert(1)</script>",
                    "bytes": 10,
                    "size": "10.0 B",
                    "days_since_modified": 1,
                }
            ],
            "largest_files": [],
        }
        plan = storage_audit.build_cleanup_plan(report)

        dashboard = storage_audit.render_html(report, plan)

        self.assertNotIn("<script>alert(1)</script>", dashboard)
        self.assertIn("&lt;script&gt;", dashboard)


if __name__ == "__main__":
    unittest.main()
