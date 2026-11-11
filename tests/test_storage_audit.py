import importlib.util
import json
import os
import subprocess
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

    def test_named_onedrive_paths_are_skipped_by_default(self) -> None:
        for name in ("OneDrive - Personal", "OneDrive - Company"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                home = Path(temp)
                cloud = home / name
                cloud.mkdir()
                (home / "local.bin").write_bytes(b"a" * 10)
                (cloud / "cloud.bin").write_bytes(b"b" * 20)
                scanner = storage_audit.Scanner(10, 20, include_cloud=False)

                self.assertEqual(scanner.scan(home), 10)
                self.assertEqual(scanner.files, 1)
                self.assertEqual(scanner.cloud_skips, [str(cloud)])

    def test_onedrive_path_detection_is_case_insensitive(self) -> None:
        for name in ("oNeDrIvE", "oNeDrIvE - pErSoNaL", "oNeDrIvE - cOmPaNy"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                cloud = Path(temp) / name
                nested = cloud / "private"
                nested.mkdir(parents=True)
                (nested / "cloud.bin").write_bytes(b"b" * 20)
                scanner = storage_audit.Scanner(10, 20, include_cloud=False)

                self.assertEqual(scanner.scan(nested), 0)
                self.assertEqual(scanner.files, 0)
                self.assertEqual(scanner.cloud_skips, [str(nested)])

    def test_onedrive_paths_can_be_included_explicitly(self) -> None:
        for name in ("OneDrive", "OneDrive - Personal", "OneDrive - Company"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                home = Path(temp)
                cloud = home / name
                cloud.mkdir()
                (cloud / "cloud.bin").write_bytes(b"b" * 20)
                scanner = storage_audit.Scanner(10, 20, include_cloud=True)

                self.assertEqual(scanner.scan(home), 20)
                self.assertEqual(scanner.files, 1)
                self.assertEqual(scanner.cloud_skips, [])

    def test_similarly_named_local_folders_are_scanned(self) -> None:
        for name in ("OneDriveBackup", "My OneDrive", "OneDrive- Company", "OneDrive -"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                home = Path(temp)
                local = home / name
                local.mkdir()
                (local / "local.bin").write_bytes(b"a" * 10)
                scanner = storage_audit.Scanner(10, 20, include_cloud=False)

                self.assertEqual(scanner.scan(home), 10)
                self.assertEqual(scanner.files, 1)
                self.assertEqual(scanner.cloud_skips, [])

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
