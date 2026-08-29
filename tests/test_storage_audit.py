import importlib.util
import json
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

    def test_command_writes_all_three_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            output = Path(temp) / "output"
            downloads = home / "Downloads"
            downloads.mkdir(parents=True)
            (downloads / "large.bin").write_bytes(b"x" * 1024)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--home",
                    str(home),
                    "--output-dir",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue((output / "storage-audit.json").is_file())
            self.assertTrue((output / "storage-audit.md").is_file())
            self.assertTrue((output / "storage-map.mmd").is_file())
            self.assertIn("```mermaid", (output / "storage-audit.md").read_text())


if __name__ == "__main__":
    unittest.main()
