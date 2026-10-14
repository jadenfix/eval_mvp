import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import e2e_receipt


class DemoReceiptTests(unittest.TestCase):
    def test_current_benchmark_hash_matches_retained_main_run(self):
        self.assertEqual(
            e2e_receipt.current_source_hash(),
            "4f2dcd5c41b2e44170c008e454672070713280439dfa234eaed36d2bd1fd7912",
        )

    def test_artifact_member_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../summary.json", "{}")
            with zipfile.ZipFile(path) as archive:
                with self.assertRaisesRegex(ValueError, "unsafe artifact member"):
                    e2e_receipt._safe_members(archive)


if __name__ == "__main__":
    unittest.main()
