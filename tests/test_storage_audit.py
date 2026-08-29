import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()
